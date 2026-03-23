"""Authentication module for Google Find My Device API.

Uses Chrome-based login + gpsoauth for Android token exchange.
Tokens are cached in ~/.config/find-my-phone/secrets.json.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

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


EMBEDDED_SETUP_URL = "https://accounts.google.com/EmbeddedSetup"
COOKIE_POLL_INTERVAL = 2
COOKIE_POLL_TIMEOUT = 300
APPLESCRIPT_READ_COOKIE = """
tell application "Google Chrome"
    set targetTabIndex to -1
    set targetWindowIndex to -1
    repeat with w from 1 to (count of windows)
        repeat with t from 1 to (count of tabs of window w)
            if URL of tab t of window w starts with "https://accounts.google.com" then
                set targetTabIndex to t
                set targetWindowIndex to w
                exit repeat
            end if
        end repeat
        if targetTabIndex > 0 then exit repeat
    end repeat
    if targetTabIndex > 0 then
        set active tab index of window targetWindowIndex to targetTabIndex
        return execute tab targetTabIndex of window targetWindowIndex javascript "document.cookie"
    else
        return ""
    end if
end tell
"""


def _extract_oauth_token_from_cookies(cookie_string: str) -> str | None:
    """Extract the oauth_token value from a cookie string."""
    for part in cookie_string.split(";"):
        key_value = part.strip().split("=", 1)
        if len(key_value) == 2 and key_value[0].strip() == "oauth_token":  # noqa: PLR2004
            return key_value[1].strip()
    return None


def request_oauth_token_via_chrome() -> str:
    """Open Google login in the user's existing Chrome and extract oauth_token.

    Opens a new tab in the running Chrome browser, then polls for
    the oauth_token cookie via AppleScript. The user's existing
    Google session is preserved.

    Returns the oauth_token value after user completes login.
    """
    import subprocess  # noqa: PLC0415  # nosec B404
    import time  # noqa: PLC0415
    import webbrowser  # noqa: PLC0415

    logger.info("Opening Google login in your browser...")
    webbrowser.open(EMBEDDED_SETUP_URL)

    logger.info("Waiting for login completion (up to 5 minutes)...")
    deadline = time.monotonic() + COOKIE_POLL_TIMEOUT

    while time.monotonic() < deadline:
        time.sleep(COOKIE_POLL_INTERVAL)

        result = subprocess.run(  # nosec B603 B607
            ["osascript", "-e", APPLESCRIPT_READ_COOKIE],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode != 0:
            logger.debug("AppleScript returned error: %s", result.stderr.strip())
            continue

        cookie_str = result.stdout.strip()
        if not cookie_str:
            continue

        token = _extract_oauth_token_from_cookies(cookie_str)
        if token:
            logger.info("OAuth token retrieved successfully")
            return token

    msg = "Timed out waiting for oauth_token cookie. Did you complete the login?"
    raise RuntimeError(msg)


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
    oauth_token = request_oauth_token_via_chrome()
    exchange_for_aas_token(settings, oauth_token)
    adm_token = get_adm_token(settings)
    logger.info("Login successful. Tokens cached.")
    return adm_token


def is_logged_in(settings: Settings) -> bool:
    """Check if we have cached credentials."""
    cache = _load_secrets(settings)
    return bool(cache.get("aas_token"))
