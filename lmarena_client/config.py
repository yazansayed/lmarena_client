from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


@dataclass(frozen=True)
class BrowserConfig:
    """
    Configuration for nodriver.

    Defaults:
    - headful (headless=False) for reliability with Turnstile/reCAPTCHA
    - allow overriding via environment variables
    """
    executable_path: Optional[str] = None
    user_data_dir: Optional[str] = None
    profile_directory: Optional[str] = None
    incognito: bool = False
    headless: bool = False  # headful default

    @staticmethod
    def from_env(prefix: str = "LM_ARENA_") -> "BrowserConfig":
        def getenv_bool(key: str, default: bool) -> bool:
            v = os.environ.get(prefix + key)
            if v is None:
                return default
            return v.strip().lower() in ("1", "true", "yes", "on")

        return BrowserConfig(
            executable_path=os.environ.get(prefix + "BROWSER_EXECUTABLE_PATH") or None,
            user_data_dir=os.environ.get(prefix + "BROWSER_USER_DATA_DIR") or None,
            profile_directory=os.environ.get(prefix + "BROWSER_PROFILE_DIRECTORY") or None,
            incognito=getenv_bool("BROWSER_INCOGNITO", False),
            headless=getenv_bool("BROWSER_HEADLESS", False),
        )


@dataclass(frozen=True)
class ClientConfig:
    """
    Top-level client configuration.
    """
    origin: str = "https://lmarena.ai"
    boot_path: str = "/?mode=direct"
    image_path: str = "/?chat-modality=image"
    # reCAPTCHA site key used by lmarena.ai (subject to change)
    recaptcha_site_key: str = "6Led_uYrAAAAAKjxDIF58fgFtX3t8loNAK85bW9I"

    # HTTP
    timeout_seconds: int = 5 * 60

    # behavior
    image_cache: bool = True
    fail_fast_bootstrap: bool = True

    # browser
    browser: BrowserConfig = BrowserConfig()

    @staticmethod
    def from_env() -> "ClientConfig":
        browser = BrowserConfig.from_env()
        return ClientConfig(browser=browser)
