"""Authentication module for Google Find My Device API.

Reads Google session cookies from the user's Chrome browser, uses them
to obtain an oauth_token from EmbeddedSetup, then exchanges it via
gpsoauth for an Android Device Manager scoped token.

Tokens are cached in ~/.config/find-my-phone/secrets.json.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import TYPE_CHECKING, Any

import gpsoauth
import httpx

from tracing import trace_span

if TYPE_CHECKING:
    from pathlib import Path

    from config import Settings

logger = logging.getLogger(__name__)

ADM_APP = "com.google.android.apps.adm"
ADM_CLIENT_SIG = "38918a453d07199354f8b19af05ec6562ced5788"
ADM_SCOPE = "oauth2:https://www.googleapis.com/auth/android_device_manager"

EMBEDDED_SETUP_URL = "https://accounts.google.com/EmbeddedSetup"
COOKIE_POLL_INTERVAL = 2
COOKIE_POLL_TIMEOUT = 300


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


def _get_chrome_cookies() -> dict[str, str]:
    """Read Google session cookies from the user's Chrome browser."""
    from pycookiecheat import chrome_cookies  # noqa: PLC0415

    cookies: dict[str, str] = chrome_cookies("https://accounts.google.com")
    return cookies


def _obtain_oauth_token_from_cookies(chrome_cookies_dict: dict[str, str]) -> str:
    """Use existing Chrome cookies to obtain an oauth_token from EmbeddedSetup.

    Makes an HTTP request to EmbeddedSetup with the user's Google session
    cookies. If the session is valid, Google sets the oauth_token cookie
    without requiring interactive login.
    """
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        response = client.get(EMBEDDED_SETUP_URL, cookies=chrome_cookies_dict)

    oauth_token = response.cookies.get("oauth_token")
    if not oauth_token:
        logger.debug("EmbeddedSetup response status: %s", response.status_code)
        logger.debug("EmbeddedSetup cookies received: %s", list(response.cookies.keys()))
        msg = "Could not obtain oauth_token from your Chrome session. Make sure you are logged into Google in Chrome."
        raise RuntimeError(msg)

    return oauth_token


def _obtain_oauth_token_via_browser() -> str:
    """Fall back to opening EmbeddedSetup in browser and polling Chrome cookies."""
    import time  # noqa: PLC0415
    import webbrowser  # noqa: PLC0415

    logger.info("Opening EmbeddedSetup in your browser for manual login...")
    webbrowser.open(EMBEDDED_SETUP_URL)

    logger.info("Waiting for login completion (up to 5 minutes)...")
    deadline = time.monotonic() + COOKIE_POLL_TIMEOUT

    while time.monotonic() < deadline:
        time.sleep(COOKIE_POLL_INTERVAL)
        try:
            cookies = _get_chrome_cookies()
            if "oauth_token" in cookies:
                return cookies["oauth_token"]
        except Exception:
            logger.debug("Cookie read attempt failed, retrying...")

    msg = "Timed out waiting for oauth_token. Did you complete the login in Chrome?"
    raise RuntimeError(msg)


def request_oauth_token(settings: Settings) -> str:
    """Obtain an oauth_token, preferring automatic cookie extraction.

    First tries to read Chrome cookies and use them to silently obtain
    the token. If that fails, falls back to opening the browser for
    manual login.
    """
    _ = settings  # reserved for future use (e.g. Chrome profile config)
    try:
        logger.info("Reading Google session from Chrome cookies...")
        cookies = _get_chrome_cookies()
        if not cookies:
            logger.info("No Chrome cookies found, falling back to browser login")
            return _obtain_oauth_token_via_browser()

        logger.info("Attempting silent authentication via Chrome session...")
        return _obtain_oauth_token_from_cookies(cookies)
    except RuntimeError:
        logger.info("Silent auth failed, falling back to browser login")
        return _obtain_oauth_token_via_browser()


def exchange_for_aas_token(settings: Settings, oauth_token: str) -> str:
    """Exchange oauth_token for an AAS (Android Auth Service) master token."""
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
    """Full login flow: Chrome cookies -> oauth_token -> AAS token -> ADM token."""
    oauth_token = request_oauth_token(settings)
    exchange_for_aas_token(settings, oauth_token)
    adm_token = get_adm_token(settings)
    logger.info("Login successful. Tokens cached.")
    return adm_token


def is_logged_in(settings: Settings) -> bool:
    """Check if we have cached credentials."""
    cache = _load_secrets(settings)
    return bool(cache.get("aas_token"))
