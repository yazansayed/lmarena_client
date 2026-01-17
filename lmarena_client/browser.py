from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional, Any

from .config import ClientConfig
from .errors import MissingRequirementsError
from .utils import log, log_exc

try:
    import nodriver
    from nodriver import cdp

    _HAS_NODRIVER = True
except ImportError:
    nodriver = None
    cdp = None
    _HAS_NODRIVER = False


BASE_HEADERS_TEMPLATE: dict[str, str] = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate",
    "accept-language": "en-US",
    "referer": "",
    "origin": "",
    "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    # user-agent filled from live browser
}


@dataclass(frozen=True)
class HTTPArgs:
    headers: dict[str, str]
    cookies: dict[str, str]


async def _click_turnstile(page, element_js: str = 'document.getElementById("cf-turnstile")') -> None:
    """
    Best-effort click assist for Turnstile element. Kept close to extracted provider.
    """
    for _ in range(3):
        size = None
        for idx in range(15):
            try:
                size = await page.js_dumps(f"{element_js}?.getBoundingClientRect()||{{}}")
                log("[lmarena-client] Turnstile size:", size)
            except Exception as e:
                log_exc("turnstile:size", e)
                break

            if "x" not in (size or {}):
                break

            try:
                await page.flash_point(size.get("x") + idx * 3, size.get("y") + idx * 3)
                await page.mouse_click(size.get("x") + idx * 3, size.get("y") + idx * 3)
            except Exception as e:
                log_exc("turnstile:click", e)
                break

            await asyncio.sleep(2)

        if "x" not in (size or {}):
            break

    log("[lmarena-client] Finished clicking turnstile.")


class BrowserManager:
    """
    Persistent in-process browser manager.

    Owns:
    - dedicated background thread + event loop for nodriver operations
    - nodriver browser lifecycle
    - bootstrapping (navigate, accept cookies, assist turnstile, wait for auth cookie, wait for grecaptcha)
    - snapshot cookies + browser-like headers
    - generate grecaptcha token via page JS
    """

    def __init__(self, config: ClientConfig) -> None:
        self._config = config

        # thread + loop
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread_lock = threading.Lock()
        self._inloop_lock: Optional[asyncio.Lock] = None

        # in-loop state
        self._browser = None
        self._tab = None
        self._user_agent: Optional[str] = None
        self._language: Optional[str] = None
        self._bootstrapped: bool = False

    # ---------------------------------------------------------------------
    # thread / loop
    # ---------------------------------------------------------------------

    def _ensure_thread(self) -> None:
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return

            if not _HAS_NODRIVER:
                raise MissingRequirementsError('Install "nodriver" to use lmarena-client.')

            ready = threading.Event()
            loop_holder: list[asyncio.AbstractEventLoop] = []

            def _run() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop_holder.append(loop)
                ready.set()
                loop.run_forever()

            self._thread = threading.Thread(
                target=_run,
                name="LMArenaBrowserLoop",
                daemon=True,
            )
            self._thread.start()

            ready.wait(timeout=10)
            if not loop_holder:
                raise RuntimeError("Failed to start browser loop thread")

            self._loop = loop_holder[0]
            log("[lmarena-client] Browser thread started.")

    async def _run_on_loop(self, coro):
        self._ensure_thread()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wrap_future(fut)

    # ---------------------------------------------------------------------
    # in-loop helpers
    # ---------------------------------------------------------------------

    async def _ensure_inloop_lock(self) -> None:
        if self._inloop_lock is None:
            self._inloop_lock = asyncio.Lock()

    def _boot_url(self) -> str:
        return self._config.origin + self._config.boot_path

    async def _tab_eval_ok_in_loop(self) -> bool:
        try:
            if self._tab is None:
                return False
            v = await self._tab.evaluate("1", return_by_value=True)
            return v == 1
        except Exception:
            return False

    async def _ensure_on_origin_in_loop(self) -> None:
        if self._tab is None:
            return
        try:
            href = await self._tab.evaluate("window.location.href", return_by_value=True)
        except Exception:
            href = None
        if not isinstance(href, str) or "lmarena.ai" not in href:
            log("[lmarena-client] Navigating to:", self._boot_url())
            await self._tab.get(self._boot_url())

    async def _start_browser_in_loop(self) -> None:
        cfg = self._config.browser

        browser_args: list[str] = ["--disable-gpu", "--no-sandbox"]
        if cfg.incognito:
            browser_args.append("--incognito")
        if cfg.headless:
            # modern headless; nodriver passes through args to chromium
            browser_args.append("--headless=new")

        # persistent profile behavior
        using_profile = bool(cfg.user_data_dir or cfg.profile_directory)
        user_data_dir = cfg.user_data_dir or (os.path.abspath("lmarena_nodriver") if using_profile else os.path.abspath("lmarena_nodriver_guest"))

        if not using_profile:
            browser_args.insert(0, "--guest")
        if cfg.profile_directory:
            browser_args.append(f"--profile-directory={cfg.profile_directory}")

        executable = cfg.executable_path
        if executable and not os.path.exists(executable):
            log("[lmarena-client] WARNING: browser executable does not exist:", executable)
            executable = None

        log("[lmarena-client] Starting nodriver...")
        log("[lmarena-client]  headless:", cfg.headless)
        log("[lmarena-client]  user_data_dir:", user_data_dir)
        log("[lmarena-client]  browser_args:", browser_args)
        log("[lmarena-client]  executable:", executable or "<auto>")

        self._browser = await nodriver.start(
            user_data_dir=user_data_dir,
            browser_args=browser_args,
            browser_executable_path=executable,
        )
        self._tab = await self._browser.get(self._boot_url())
        self._bootstrapped = False
        self._user_agent = None
        self._language = None

    async def _restart_browser_in_loop(self) -> None:
        log("[lmarena-client] Restarting browser...")
        try:
            if self._browser and getattr(self._browser, "connection", None):
                try:
                    self._browser.stop()
                except Exception:
                    pass
        except Exception:
            pass

        self._browser = None
        self._tab = None
        self._user_agent = None
        self._language = None
        self._bootstrapped = False

        await self._start_browser_in_loop()

    async def _wait_for_js_in_loop(self, expression: str, *, timeout: int, label: str) -> None:
        start = time.time()
        while True:
            try:
                ok = await self._tab.evaluate(f"Boolean({expression})", return_by_value=True)
                if ok:
                    return
            except Exception:
                pass

            if time.time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for {label} ({timeout}s)")
            await asyncio.sleep(1)

    async def _get_cookies_in_loop(self) -> dict[str, str]:
        if self._tab is None:
            return {}
        cookies: dict[str, str] = {}
        try:
            for c in await self._tab.send(cdp.network.get_cookies([self._config.origin])):
                cookies[c.name] = c.value
        except Exception as e:
            log_exc("get_cookies", e)
        return cookies

    async def _has_arena_auth_cookie_in_loop(self) -> bool:
        cookies = await self._get_cookies_in_loop()
        return any("arena-auth-prod" in name for name in cookies.keys())

    async def _wait_for_cookie_in_loop(self, *, timeout: int = 300) -> None:
        start = time.time()
        while True:
            try:
                if await self._has_arena_auth_cookie_in_loop():
                    return
            except Exception:
                pass
            if time.time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for arena-auth cookie ({timeout}s)")
            await asyncio.sleep(1)

    async def _bootstrap_in_loop(self) -> None:
        if self._tab is None:
            raise RuntimeError("No tab for bootstrap")

        log("[lmarena-client] Bootstrapping lmarena page...")

        await self._wait_for_js_in_loop('document.querySelector("body:not(.no-js)")', timeout=180, label="body:not(.no-js)")

        # accept cookies (best-effort)
        try:
            button = await self._tab.find("Accept Cookies")
            if button:
                log("[lmarena-client] Clicking 'Accept Cookies'")
                await button.click()
        except Exception as e:
            log_exc("accept-cookies", e)

        await asyncio.sleep(1)

        # trigger textarea (best-effort)
        try:
            textarea = await self._tab.select('textarea[name="message"]')
            if textarea:
                await textarea.send_keys("Hello")
        except Exception as e:
            log_exc("trigger-textarea", e)

        await asyncio.sleep(1)

        # assist turnstile (best-effort)
        try:
            element = await self._tab.select('[style="display: grid;"]')
            if element:
                log("[lmarena-client] Detected turnstile grid, attempting click assist.")
                await _click_turnstile(self._tab, 'document.querySelector(\'[style="display: grid;"]\')')
        except Exception as e:
            log_exc("turnstile-grid-click", e)

        try:
            if not await self._has_arena_auth_cookie_in_loop():
                log("[lmarena-client] Waiting for #cf-turnstile then clicking.")
                try:
                    await self._tab.select("#cf-turnstile", 300)
                except Exception:
                    pass
                await asyncio.sleep(3)
                await _click_turnstile(self._tab, 'document.getElementById("cf-turnstile")')
        except Exception as e:
            log_exc("turnstile-cf-click", e)

        await self._wait_for_cookie_in_loop(timeout=300)
        await self._wait_for_js_in_loop(
            "window.grecaptcha && window.grecaptcha.enterprise",
            timeout=180,
            label="grecaptcha.enterprise",
        )

        try:
            self._user_agent = await self._tab.evaluate("window.navigator.userAgent", return_by_value=True)
        except Exception:
            self._user_agent = None
        try:
            self._language = await self._tab.evaluate("window.navigator.language", return_by_value=True)
        except Exception:
            self._language = None

        self._bootstrapped = True
        log("[lmarena-client] Bootstrap complete.")
        if self._user_agent:
            log("[lmarena-client] UA:", self._user_agent)
        if self._language:
            log("[lmarena-client] lang:", self._language)

    async def _ensure_ready_in_loop(self, *, force_reload: bool = False) -> None:
        await self._ensure_inloop_lock()
        async with self._inloop_lock:
            if self._browser is None or self._tab is None:
                await self._start_browser_in_loop()

            if force_reload or not await self._tab_eval_ok_in_loop():
                log("[lmarena-client] Tab unhealthy or force_reload=True -> restarting browser.")
                await self._restart_browser_in_loop()

            await self._ensure_on_origin_in_loop()

            if not self._bootstrapped:
                await self._bootstrap_in_loop()

    async def _reload_tab_in_loop(self) -> None:
        await self._ensure_inloop_lock()
        async with self._inloop_lock:
            if self._tab is None:
                return
            log("[lmarena-client] Reloading tab:", self._boot_url())
            try:
                await self._tab.get(self._boot_url())
            except Exception:
                try:
                    await self._tab.reload()
                except Exception as e:
                    log_exc("reload_tab", e)
            self._bootstrapped = False

    async def _get_http_args_in_loop(self) -> HTTPArgs:
        cookies = await self._get_cookies_in_loop()
        headers = dict(BASE_HEADERS_TEMPLATE)
        headers["origin"] = self._config.origin
        headers["referer"] = self._config.origin + "/"

        headers["user-agent"] = self._user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        )
        if self._language:
            headers["accept-language"] = self._language

        return HTTPArgs(headers=headers, cookies=cookies)

    async def _get_grecaptcha_token_in_loop(self) -> str:
        await self._wait_for_js_in_loop(
            "window.grecaptcha && window.grecaptcha.enterprise",
            timeout=60,
            label="grecaptcha.enterprise",
        )

        token = await self._tab.evaluate(
            f"""new Promise((resolve) => {{
                window.grecaptcha.enterprise.ready(async () => {{
                    try {{
                        const t = await window.grecaptcha.enterprise.execute(
                            '{self._config.recaptcha_site_key}',
                            {{ action: 'chat_submit' }}
                        );
                        resolve(t);
                    }} catch (e) {{
                        console.error("[lmarena-client] reCAPTCHA execute failed:", e);
                        resolve(null);
                    }}
                }});
            }});""",
            await_promise=True,
        )
        if isinstance(token, str) and token:
            return token
        raise RuntimeError(f"grecaptcha returned: {token!r}")

    async def _get_page_html_in_loop(self) -> str:
        if self._tab is None:
            return ""
        try:
            return await self._tab.get_content()
        except Exception as e:
            log_exc("get_page_html", e)
            return ""

    # ---------------------------------------------------------------------
    # public API (marshalled to browser loop)
    # ---------------------------------------------------------------------

    async def ensure_ready(self, *, force_reload: bool = False) -> None:
        await self._run_on_loop(self._ensure_ready_in_loop(force_reload=force_reload))

    async def reload_tab(self) -> None:
        await self._run_on_loop(self._reload_tab_in_loop())

    async def get_http_args(self) -> HTTPArgs:
        await self.ensure_ready()
        return await self._run_on_loop(self._get_http_args_in_loop())

    async def get_grecaptcha_token(self) -> str:
        await self.ensure_ready()
        return await self._run_on_loop(self._get_grecaptcha_token_in_loop())

    async def get_page_html(self) -> str:
        await self.ensure_ready()
        return await self._run_on_loop(self._get_page_html_in_loop())

    async def get_cookies(self) -> dict[str, str]:
        await self.ensure_ready()
        return await self._run_on_loop(self._get_cookies_in_loop())
