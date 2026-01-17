from __future__ import annotations
from dataclasses import dataclass
import json
import re
from typing import Optional

from .browser import BrowserManager, HTTPArgs
from .http import StreamSession, ensure_ok
from .utils import log, log_exc


DEFAULT_NEXT_ACTIONS: dict[str, str] = {
    # placeholders; updated dynamically by scanning _next js chunk
    "generateUploadUrl": "",
    "getSignedUrl": "",
}


def _derive_models_from_list(model_list: list[dict]) -> tuple[dict[str, str], dict[str, str], list[str], list[str], str]:
    text_models = {
        m["publicName"]: m["id"]
        for m in model_list
        if "text" in m.get("capabilities", {}).get("outputCapabilities", {})
    }
    image_models = {
        m["publicName"]: m["id"]
        for m in model_list
        if "image" in m.get("capabilities", {}).get("outputCapabilities", {})
    }
    vision_models = sorted([
        m["publicName"]
        for m in model_list
        if "image" in m.get("capabilities", {}).get("inputCapabilities", {})
    ])
    all_models = sorted(set(text_models) | set(image_models))
    default_model = sorted(text_models.keys())[0] if text_models else (all_models[0] if all_models else "")
    return text_models, image_models, vision_models, all_models, default_model


@dataclass
class DiscoveryState:
    text_models: dict[str, str]
    image_models: dict[str, str]
    vision_models: list[str]
    models: list[str]
    default_model: str
    next_actions: dict[str, str]


class Discovery:
    """
    Loads:
    - models list from HTML initialModels
    - Next.js server action IDs needed for image upload
    """

    def __init__(self, browser: BrowserManager, origin: str) -> None:
        self._browser = browser
        self._origin = origin.rstrip("/")

        self._loaded_models = False
        self._loaded_actions = False

        self._state = DiscoveryState(
            text_models={},
            image_models={},
            vision_models=[],
            models=[],
            default_model="",
            next_actions=dict(DEFAULT_NEXT_ACTIONS),
        )

    @property
    def state(self) -> DiscoveryState:
        return self._state

    async def ensure_loaded(self) -> None:
        if self._loaded_models and self._loaded_actions:
            return

        await self._browser.ensure_ready()

        html = ""
        try:
            html = await self._browser.get_page_html()
        except Exception as e:
            log_exc("discovery:get_page_html", e)

        if not html:
            return

        http_args = await self._browser.get_http_args()

        # parse models and actions best-effort
        try:
            self._parse_models_from_html(html)
        except Exception as e:
            log_exc("discovery:parse_models", e)

        try:
            await self._parse_actions_from_html(html, http_args)
        except Exception as e:
            log_exc("discovery:parse_actions", e)

        self._loaded_models = bool(self._state.models)
        self._loaded_actions = bool(self._state.next_actions.get("generateUploadUrl")) and bool(self._state.next_actions.get("getSignedUrl"))

    def _parse_models_from_html(self, html: str) -> None:
        """
        Parse Next.js HTML payload scripts that push `self.__next_f.push([...])`,
        and search for objects containing `initialModels`.
        """
        line_pattern = re.compile(r"^([0-9a-fA-F]+):(.*)")
        pattern = r"self\.__next_f\.push\((\[[\s\S]*?\])\)(?=<\/script>)"
        matches = re.findall(pattern, html)

        def pars_children(data: dict) -> None:
            children = data.get("children")
            if not isinstance(children, list) or len(children) < 4:
                return
            if children[1] in ["div", "defs", "style", "script"]:
                return
            if children[0] == "$":
                pars_data(children[3])
            else:
                for child in children:
                    if isinstance(child, list) and len(child) >= 4:
                        pars_data(child[3])

        def pars_data(data) -> None:
            if not isinstance(data, (list, dict)):
                return
            if isinstance(data, dict):
                json_data = data
            elif data and isinstance(data, list) and data[0] == "$":
                if data[1] in ["div", "defs", "style", "script"]:
                    return
                json_data = data[3]
            else:
                return

            if not json_data:
                return

            if "initialModels" in json_data:
                model_list = json_data["initialModels"]
                (
                    self._state.text_models,
                    self._state.image_models,
                    self._state.vision_models,
                    self._state.models,
                    self._state.default_model,
                ) = _derive_models_from_list(model_list)
                log(f"[lmarena-client] Loaded {len(self._state.models)} models from initialModels.")
            elif "children" in json_data:
                pars_children(json_data)

        for match in matches:
            data = json.loads(match)
            if not (isinstance(data, list) and len(data) >= 2 and isinstance(data[1], str)):
                continue
            for chunk in data[1].split("\n"):
                m = line_pattern.match(chunk)
                if not m:
                    continue
                _, chunk_data = m.groups()
                if chunk_data.startswith(("[", "{")):
                    try:
                        obj = json.loads(chunk_data)
                    except Exception:
                        continue
                    pars_data(obj)

    async def _parse_actions_from_html(self, html: str, http_args: HTTPArgs) -> None:
        """
        Locate the Evaluation _next js chunk via the dynamic import mapping inside the HTML,
        fetch it, and scan for action IDs.
        """
        line_pattern = re.compile(r"^([0-9a-fA-F]+):(.*)")
        pattern = r"self\.__next_f\.push\((\[[\s\S]*?\])\)(?=<\/script>)"
        matches = re.findall(pattern, html)

        for match in matches:
            data = json.loads(match)
            if not (isinstance(data, list) and len(data) >= 2 and isinstance(data[1], str)):
                continue

            for chunk in data[1].split("\n"):
                m = line_pattern.match(chunk)
                if not m:
                    continue
                _, chunk_data = m.groups()

                # "I[...]" indicates a dynamic import mapping (used to locate _next js chunk)
                if not chunk_data.startswith("I["):
                    continue

                try:
                    import_data = json.loads(chunk_data[1:])
                except Exception:
                    continue

                # heuristic from extracted provider:
                # import_data[2] == "Evaluation" suggests this mapping contains the right chunk(s)
                if not (isinstance(import_data, list) and len(import_data) >= 3 and import_data[2] == "Evaluation"):
                    continue

                js_files = dict(zip(import_data[1][::2], import_data[1][1::2]))
                if not js_files:
                    continue

                # try last chunks first (often the most specific)
                for _, js_path in list(js_files.items())[::-1]:
                    js_url = f"{self._origin}/_next/{js_path}"
                    try:
                        async with StreamSession(headers=http_args.headers, cookies=http_args.cookies, timeout=60) as session:
                            async with session.get(js_url) as js_resp:
                                await ensure_ok(js_resp, context=f"fetch_js:{js_url}")
                                js_text = await js_resp.text()
                    except Exception as e:
                        log_exc("discovery:fetch_js", e)
                        continue

                    if "generateUploadUrl" not in js_text:
                        continue

                    found = re.findall(r'\("([a-f0-9]{40,})".*?"(\w+)"\)', js_text)
                    if not found:
                        continue

                    for action_id, action_name in found:
                        if action_name in self._state.next_actions or action_name in ("generateUploadUrl", "getSignedUrl"):
                            self._state.next_actions[action_name] = action_id

                    if self._state.next_actions.get("generateUploadUrl") and self._state.next_actions.get("getSignedUrl"):
                        self._loaded_actions = True
                        log("[lmarena-client] Updated Next.js action IDs.")
                        return

    def resolve_model_id(self, model_name: str) -> Optional[str]:
        if model_name in self._state.text_models:
            return self._state.text_models[model_name]
        if model_name in self._state.image_models:
            return self._state.image_models[model_name]
        return None

    def is_image_output_model(self, model_name: str) -> bool:
        return model_name in self._state.image_models

    def supports_vision_input(self, model_name: str) -> bool:
        return model_name in self._state.vision_models
