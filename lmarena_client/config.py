from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Optional


def _parse_bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


def _parse_int(v: str) -> int:
    return int(v.strip())


def _strip_inline_comment(s: str) -> str:
    """
    Remove inline comments starting with #, but preserve hashes inside quotes.
    Very small parser for our simple config.yaml.
    """
    out = []
    in_single = False
    in_double = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _parse_simple_yaml(path: Path) -> dict[str, Any]:
    """
    Minimal YAML-like parser for simple `key: value` configs.

    Supported:
    - comments (# ...)
    - empty lines
    - strings: unquoted, "quoted", 'quoted'
    - python-ish raw strings: r"..." or r'...'
    - bool: true/false
    - null: null/~
    - ints
    """
    data: dict[str, Any] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = _strip_inline_comment(line)
        if not line:
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if value in ("", "null", "~"):
            data[key] = None
            continue

        # raw string form: r"..." / r'...'
        if (value.startswith('r"') and value.endswith('"')) or (value.startswith("r'") and value.endswith("'")):
            data[key] = value[2:-1]
            continue

        # quoted strings
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            data[key] = value[1:-1]
            continue

        # bool
        if value.lower() in ("true", "false"):
            data[key] = value.lower() == "true"
            continue

        # int
        try:
            data[key] = int(value)
            continue
        except ValueError:
            pass

        # fallback as-is
        data[key] = value

    return data


def _find_config_file() -> Optional[Path]:
    """
    Find config file using standard precedence for file location:
    1) <project_root>/config.yaml (parent of lmarena_client package)
    2) LM_ARENA_CONFIG (explicit path via env var)
    3) ./config.yaml (current working directory)
    """
    # Project root: parent of the lmarena_client package directory
    package_dir = Path(__file__).resolve().parent  # lmarena_client/
    project_root = package_dir.parent  # parent of lmarena_client/
    project_config = project_root / "config.yaml"
    if project_config.is_file():
        return project_config

    env_path = os.environ.get("LM_ARENA_CONFIG")
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_file():
            return p

    cwd = Path.cwd() / "config.yaml"
    if cwd.is_file():
        return cwd

    return None


@dataclass(frozen=True)
class BrowserConfig:
    """
    Configuration for nodriver.

    Defaults:
    - headful (headless=False) for reliability with Turnstile/reCAPTCHA
    """
    executable_path: Optional[str] = None
    user_data_dir: Optional[str] = None
    profile_directory: Optional[str] = None
    incognito: bool = False
    headless: bool = False  # headful default

    @staticmethod
    def from_mapping(m: dict[str, Any]) -> "BrowserConfig":
        return BrowserConfig(
            executable_path=m.get("browser_executable_path"),
            user_data_dir=m.get("browser_user_data_dir"),
            profile_directory=m.get("browser_profile") or m.get("browser_profile_directory"),
            headless=bool(m.get("headless")) if m.get("headless") is not None else False,
            incognito=bool(m.get("incognito")) if m.get("incognito") is not None else False,
        )

    @staticmethod
    def from_env(prefix: str = "LM_ARENA_") -> "BrowserConfig":
        def getenv_bool(key: str, default: Optional[bool] = None) -> Optional[bool]:
            v = os.environ.get(prefix + key)
            if v is None:
                return default
            return _parse_bool(v)

        return BrowserConfig(
            executable_path=os.environ.get(prefix + "BROWSER_EXECUTABLE_PATH") or None,
            user_data_dir=os.environ.get(prefix + "BROWSER_USER_DATA_DIR") or None,
            profile_directory=os.environ.get(prefix + "BROWSER_PROFILE") or os.environ.get(prefix + "BROWSER_PROFILE_DIRECTORY") or None,
            incognito=getenv_bool("INCOGNITO", None) if getenv_bool("INCOGNITO", None) is not None else False,
            headless=getenv_bool("HEADLESS", None) if getenv_bool("HEADLESS", None) is not None else False,
        )


@dataclass(frozen=True)
class ClientConfig:
    """
    Top-level client configuration.

    Precedence for values:
    - explicit code config (when you pass Client(config=...))
    - environment variables
    - config.yaml
    - built-in defaults
    """
    origin: str = "https://lmarena.ai"
    boot_path: str = "/?mode=direct"
    image_path: str = "/?chat-modality=image"

    # reCAPTCHA site key used by lmarena.ai (subject to change)
    recaptcha_site_key: str = "6Led_uYrAAAAAKjxDIF58fgFtX3t8loNAK85bW9I"

    # HTTP
    timeout_seconds: int = 5 * 60
    upload_timeout_seconds: int = 10 * 60

    # behavior
    image_cache: bool = True
    fail_fast_bootstrap: bool = True

    # browser
    browser: BrowserConfig = BrowserConfig()

    @staticmethod
    def load() -> "ClientConfig":
        """
        Load configuration using precedence:
        1) config.yaml (if present)
        2) environment overrides (LM_ARENA_*)
        3) defaults
        """
        base: dict[str, Any] = {}
        cfg_path = _find_config_file()
        if cfg_path:
            base.update(_parse_simple_yaml(cfg_path))

        # Apply env overrides (higher precedence than file)
        env = os.environ

        if env.get("LM_ARENA_ORIGIN"):
            base["origin"] = env["LM_ARENA_ORIGIN"]
        if env.get("LM_ARENA_BOOT_PATH"):
            base["boot_path"] = env["LM_ARENA_BOOT_PATH"]
        if env.get("LM_ARENA_IMAGE_PATH"):
            base["image_path"] = env["LM_ARENA_IMAGE_PATH"]
        if env.get("LM_ARENA_RECAPTCHA_SITE_KEY"):
            base["recaptcha_site_key"] = env["LM_ARENA_RECAPTCHA_SITE_KEY"]

        if env.get("LM_ARENA_TIMEOUT_SECONDS"):
            base["timeout_seconds"] = _parse_int(env["LM_ARENA_TIMEOUT_SECONDS"])
        if env.get("LM_ARENA_UPLOAD_TIMEOUT_SECONDS"):
            base["upload_timeout_seconds"] = _parse_int(env["LM_ARENA_UPLOAD_TIMEOUT_SECONDS"])

        if env.get("LM_ARENA_IMAGE_CACHE") is not None:
            base["image_cache"] = _parse_bool(env["LM_ARENA_IMAGE_CACHE"])
        if env.get("LM_ARENA_FAIL_FAST_BOOTSTRAP") is not None:
            base["fail_fast_bootstrap"] = _parse_bool(env["LM_ARENA_FAIL_FAST_BOOTSTRAP"])

        browser = BrowserConfig.from_mapping(base)
        env_browser = BrowserConfig.from_env()

        # Merge browser fields with env taking precedence over file
        browser = BrowserConfig(
            executable_path=env_browser.executable_path or browser.executable_path,
            user_data_dir=env_browser.user_data_dir or browser.user_data_dir,
            profile_directory=env_browser.profile_directory or browser.profile_directory,
            headless=env_browser.headless if "LM_ARENA_HEADLESS" in env else browser.headless,
            incognito=env_browser.incognito if "LM_ARENA_INCOGNITO" in env else browser.incognito,
        )

        return ClientConfig(
            origin=base.get("origin", ClientConfig.origin),
            boot_path=base.get("boot_path", ClientConfig.boot_path),
            image_path=base.get("image_path", ClientConfig.image_path),
            recaptcha_site_key=base.get("recaptcha_site_key", ClientConfig.recaptcha_site_key),
            timeout_seconds=int(base.get("timeout_seconds", ClientConfig.timeout_seconds)),
            upload_timeout_seconds=int(base.get("upload_timeout_seconds", ClientConfig.upload_timeout_seconds)),
            image_cache=bool(base.get("image_cache", ClientConfig.image_cache)),
            fail_fast_bootstrap=bool(base.get("fail_fast_bootstrap", ClientConfig.fail_fast_bootstrap)),
            browser=browser,
        )

    @staticmethod
    def from_env() -> "ClientConfig":
        """
        Backward-compatible alias: previously this only read env.
        Now it loads config.yaml + env.
        """
        return ClientConfig.load()

