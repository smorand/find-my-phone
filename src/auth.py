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


def request_oauth_token_via_chrome(settings: Settings) -> str:
    """Open Chrome with existing profile and extract oauth_token cookie.

    Copies the user's Chrome profile to a temp directory so Chrome
    can run even if the main browser is already open. The user's
    existing Google session is preserved, avoiding a fresh login.

    Returns the oauth_token value after user completes login.
    """
    import undetected_chromedriver as uc  # noqa: PLC0415
    from selenium.webdriver.support.ui import WebDriverWait  # noqa: PLC0415

    logger.info("Opening Chrome for Google login...")

    temp_dir = tempfile.mkdtemp(prefix="find_my_phone_chrome_")
    source_profile = settings.chrome_user_data_dir / settings.chrome_profile
    dest_profile = Path(temp_dir) / settings.chrome_profile

    if source_profile.exists():
        logger.info("Copying Chrome profile from %s", source_profile)
        shutil.copytree(
            source_profile,
            dest_profile,
            ignore=shutil.ignore_patterns("SingletonLock", "SingletonSocket", "SingletonCookie"),
        )
    else:
        logger.warning("Chrome profile not found at %s, using fresh profile", source_profile)

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={temp_dir}")
    options.add_argument(f"--profile-directory={settings.chrome_profile}")
    driver = uc.Chrome(options=options)

    try:
        driver.get("https://accounts.google.com/EmbeddedSetup")
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
        driver.quit()
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
