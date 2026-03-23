"""Authentication module for Google Find My Device API.

Uses Chrome-based login + gpsoauth for Android token exchange.
Tokens are cached in ~/.config/find-my-phone/secrets.json.
"""

from __future__ import annotations

import json
import logging
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import gpsoauth

from tracing import trace_span

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)

ADM_APP = "com.google.android.apps.adm"
ADM_CLIENT_SIG = "38918a453d07199354f8b19af05ec6562ced5788"
ADM_SCOPE = "oauth2:https://www.googleapis.com/auth/android_device_manager"


def _get_secrets_path(settings: Settings) -> Path:
    """Return path to secrets cache file."""
    return settings.secrets_dir / "secrets.json"


def _load_secrets(settings: Settings) -> dict[str, Any]:
    """Load cached secrets from disk."""
    path = _get_secrets_path(settings)
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
            return data
    return {}


def _save_secrets(settings: Settings, data: dict[str, Any]) -> None:
    """Save secrets to disk."""
    path = _get_secrets_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _generate_android_id() -> str:
    """Generate a random 16-char hex Android device ID."""
    return secrets.token_hex(8)


def _get_android_id(settings: Settings) -> str:
    """Get or create a persistent Android device ID."""
    data = _load_secrets(settings)
    android_id = data.get("android_id")
    if android_id:
        result: str = android_id
        return result
    android_id = _generate_android_id()
    data["android_id"] = android_id
    _save_secrets(settings, data)
    return android_id


CHROME_COOKIE_FILES = ("Cookies", "Cookies-journal", "Login Data", "Login Data-journal", "Web Data")
CHROME_WAIT_SECONDS = 3
CHROME_TERMINATE_TIMEOUT = 10


def _find_free_port() -> int:
    """Find a free TCP port for Chrome remote debugging."""
    import socket  # noqa: PLC0415

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def _prepare_temp_profile(settings: Settings) -> str:
    """Create a lightweight temp Chrome user data dir with session cookies from the real profile.

    Only copies cookie and login files (a few MB) instead of the entire profile (GB+).
    """
    temp_dir = tempfile.mkdtemp(prefix="find_my_phone_chrome_")
    source_profile = settings.chrome_user_data_dir / settings.chrome_profile
    dest_profile = Path(temp_dir) / settings.chrome_profile
    dest_profile.mkdir(parents=True, exist_ok=True)

    if source_profile.exists():
        logger.info("Copying session data from Chrome profile %s", settings.chrome_profile)
        for filename in CHROME_COOKIE_FILES:
            src = source_profile / filename
            if src.exists():
                shutil.copy2(src, dest_profile / filename)

        prefs_src = source_profile / "Preferences"
        if prefs_src.exists():
            shutil.copy2(prefs_src, dest_profile / "Preferences")

        local_state = settings.chrome_user_data_dir / "Local State"
        if local_state.exists():
            shutil.copy2(local_state, Path(temp_dir) / "Local State")
    else:
        logger.warning("Chrome profile not found at %s, using fresh profile", source_profile)

    return temp_dir


def request_oauth_token_via_chrome(settings: Settings) -> str:
    """Launch a temporary Chrome instance with session cookies and extract oauth_token.

    Creates a lightweight temp profile with only cookie/login files from the
    user's real Chrome profile, then launches Chrome with remote debugging
    to automate the login flow via Selenium.

    Returns the oauth_token value after user completes login.
    """
    import subprocess  # noqa: PLC0415  # nosec B404
    import time  # noqa: PLC0415

    from selenium import webdriver  # noqa: PLC0415
    from selenium.webdriver.support.ui import WebDriverWait  # noqa: PLC0415

    logger.info("Opening Chrome for Google login...")

    temp_dir = _prepare_temp_profile(settings)
    debug_port = _find_free_port()

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome_args = [
        chrome_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={temp_dir}",
        f"--profile-directory={settings.chrome_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://accounts.google.com/EmbeddedSetup",
    ]

    chrome_proc = subprocess.Popen(chrome_args)  # nosec B603
    logger.info("Chrome launched with PID %d on debug port %d", chrome_proc.pid, debug_port)

    try:
        time.sleep(CHROME_WAIT_SECONDS)

        options = webdriver.ChromeOptions()
        options.debugger_address = f"127.0.0.1:{debug_port}"
        driver = webdriver.Chrome(options=options)

        logger.info("Waiting for login completion (up to 5 minutes)...")
        WebDriverWait(driver, 300).until(lambda d: d.get_cookie("oauth_token") is not None)

        cookie = driver.get_cookie("oauth_token")
        if not cookie:
            msg = "Failed to retrieve oauth_token cookie"
            raise RuntimeError(msg)
        token: str = cookie["value"]
        logger.info("OAuth token retrieved successfully")
        return token
    finally:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=CHROME_TERMINATE_TIMEOUT)
        shutil.rmtree(temp_dir, ignore_errors=True)


def exchange_for_aas_token(settings: Settings, oauth_token: str) -> str:
    """Exchange Chrome oauth_token for an AAS (Android Auth Service) master token."""
    with trace_span("auth.exchange_aas_token"):
        android_id = _get_android_id(settings)

        response: dict[str, str] = gpsoauth.exchange_token(
            email="",
            token=oauth_token,
            android_id=android_id,
        )

        if "Token" not in response:
            logger.error("AAS token exchange failed: %s", response)
            msg = f"AAS token exchange failed: {response.get('Error', 'unknown error')}"
            raise RuntimeError(msg)

        aas_token: str = response["Token"]

        cache = _load_secrets(settings)
        cache["aas_token"] = aas_token
        if "Email" in response:
            cache["username"] = response["Email"]
        _save_secrets(settings, cache)

        logger.info("AAS token obtained for %s", cache.get("username", "unknown"))
        return aas_token


def get_adm_token(settings: Settings) -> str:
    """Get an ADM (Android Device Manager) scoped OAuth token.

    Uses the cached AAS token to request a scoped token via gpsoauth.
    """
    with trace_span("auth.get_adm_token"):
        cache = _load_secrets(settings)
        aas_token = cache.get("aas_token")
        if not aas_token:
            msg = "Not logged in. Run 'find-my-phone login' first."
            raise RuntimeError(msg)

        username = cache.get("username", "")
        android_id = _get_android_id(settings)

        response: dict[str, str] = gpsoauth.perform_oauth(
            email=username,
            master_token=aas_token,
            android_id=android_id,
            service=ADM_SCOPE,
            app=ADM_APP,
            client_sig=ADM_CLIENT_SIG,
        )

        if "Auth" not in response:
            logger.error("ADM token request failed: %s", response)
            msg = "ADM token request failed. Try running 'find-my-phone login' again."
            raise RuntimeError(msg)

        token: str = response["Auth"]
        logger.debug("ADM token obtained")
        return token


def login(settings: Settings) -> str:
    """Full login flow: Chrome login -> AAS token -> verify ADM token works."""
    oauth_token = request_oauth_token_via_chrome(settings)
    exchange_for_aas_token(settings, oauth_token)
    adm_token = get_adm_token(settings)
    logger.info("Login successful. Tokens cached.")
    return adm_token


def is_logged_in(settings: Settings) -> bool:
    """Check if we have cached credentials."""
    cache = _load_secrets(settings)
    return bool(cache.get("aas_token"))
