"""Authentication module for Google Find My Device API.

Uses standard OAuth2 flow with localhost redirect for user consent.
Tokens are cached in ~/.config/find-my-phone/secrets.json.
"""

from __future__ import annotations

import json
import logging
import secrets
import urllib.parse
from typing import TYPE_CHECKING, Any

import httpx

from tracing import trace_span

if TYPE_CHECKING:
    from pathlib import Path

    from config import Settings

logger = logging.getLogger(__name__)

OAUTH2_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
OAUTH2_EXCHANGE_URL = "https://oauth2.googleapis.com/token"
OAUTH2_SCOPE = "https://www.googleapis.com/auth/android_device_manager"

CREDENTIALS_PATH = "~/.credentials/scm-pwd-web.json"
LOCAL_SERVER_TIMEOUT = 300
LOCAL_SERVER_PORT = 8002


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


def _load_client_credentials() -> dict[str, str]:
    """Load OAuth2 client credentials from the credentials file."""
    from pathlib import Path  # noqa: PLC0415

    creds_path = Path(CREDENTIALS_PATH).expanduser()
    if not creds_path.exists():
        msg = f"OAuth2 credentials not found at {creds_path}"
        raise FileNotFoundError(msg)

    with creds_path.open("r", encoding="utf-8") as fh:
        raw: dict[str, Any] = json.load(fh)

    web_config = raw.get("web", {})
    client_id = web_config.get("client_id", "")
    client_secret = web_config.get("client_secret", "")

    if not client_id or not client_secret:
        msg = "Missing client_id or client_secret in credentials file"
        raise ValueError(msg)

    return {"client_id": client_id, "client_secret": client_secret}


def _wait_for_auth_code() -> str:
    """Start a local HTTP server and wait for the OAuth2 callback with auth code."""
    import http.server  # noqa: PLC0415
    import threading  # noqa: PLC0415

    auth_code: str | None = None
    error: str | None = None

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            nonlocal auth_code, error
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

            if "code" in params:
                auth_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Login successful!</h2><p>You can close this tab.</p></body></html>")
            elif "error" in params:
                error = params["error"][0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f"<html><body><h2>Login failed: {error}</h2></body></html>".encode())
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            logger.debug(format, *args)

    server = http.server.HTTPServer(("127.0.0.1", LOCAL_SERVER_PORT), CallbackHandler)
    server.timeout = LOCAL_SERVER_TIMEOUT

    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()
    server_thread.join(timeout=LOCAL_SERVER_TIMEOUT)
    server.server_close()

    if error:
        msg = f"OAuth2 login denied: {error}"
        raise RuntimeError(msg)

    if not auth_code:
        msg = "Timed out waiting for login. Did you complete the consent in your browser?"
        raise RuntimeError(msg)

    return auth_code


def request_oauth2_token(settings: Settings) -> str:
    """Run standard OAuth2 flow: open browser for consent, receive token via localhost redirect.

    Opens the Google consent page in the user's default browser (respects existing
    session), then waits for the redirect on a local HTTP server to capture the
    auth code. Exchanges the code for access and refresh tokens.

    Returns the access token.
    """
    import webbrowser  # noqa: PLC0415

    creds = _load_client_credentials()
    redirect_uri = f"http://localhost:{LOCAL_SERVER_PORT}/"

    auth_params = urllib.parse.urlencode(
        {
            "client_id": creds["client_id"],
            "redirect_uri": redirect_uri,
            "scope": OAUTH2_SCOPE,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    auth_url = f"{OAUTH2_AUTH_URL}?{auth_params}"

    logger.info("Opening Google consent page in your browser...")
    webbrowser.open(auth_url)

    logger.info("Waiting for authorization (up to 5 minutes)...")
    code = _wait_for_auth_code()

    logger.info("Exchanging authorization code for tokens...")
    with httpx.Client() as client:
        token_response = client.post(
            OAUTH2_EXCHANGE_URL,
            data={
                "code": code,
                "client_id": creds["client_id"],
                "client_secret": creds["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_data = token_response.json()

    if "access_token" not in token_data:
        logger.error("Token exchange failed: %s", token_data)
        msg = f"Token exchange failed: {token_data.get('error_description', token_data.get('error', 'unknown'))}"
        raise RuntimeError(msg)

    cache = _load_secrets(settings)
    cache["access_token"] = token_data["access_token"]
    if "refresh_token" in token_data:
        cache["refresh_token"] = token_data["refresh_token"]
    _save_secrets(settings, cache)

    access_token: str = token_data["access_token"]
    logger.info("OAuth2 tokens obtained and cached")
    return access_token


def refresh_access_token(settings: Settings) -> str:
    """Refresh the access token using the cached refresh token."""
    with trace_span("auth.refresh_token"):
        cache = _load_secrets(settings)
        refresh_token = cache.get("refresh_token")
        if not refresh_token:
            msg = "No refresh token cached. Run 'find-my-phone login' first."
            raise RuntimeError(msg)

        creds = _load_client_credentials()

        with httpx.Client() as client:
            response = client.post(
                OAUTH2_EXCHANGE_URL,
                data={
                    "client_id": creds["client_id"],
                    "client_secret": creds["client_secret"],
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            token_data = response.json()

        if "access_token" not in token_data:
            logger.error("Token refresh failed: %s", token_data)
            msg = "Token refresh failed. Run 'find-my-phone login' again."
            raise RuntimeError(msg)

        cache["access_token"] = token_data["access_token"]
        _save_secrets(settings, cache)

        result: str = token_data["access_token"]
        logger.info("Access token refreshed")
        return result


def get_adm_token(settings: Settings) -> str:
    """Get a valid access token for the Android Device Manager API.

    First tries the cached access token. If that fails (expired),
    refreshes it using the cached refresh token.
    """
    with trace_span("auth.get_adm_token"):
        cache = _load_secrets(settings)
        access_token = cache.get("access_token")
        if not access_token:
            msg = "Not logged in. Run 'find-my-phone login' first."
            raise RuntimeError(msg)
        result: str = access_token
        return result


def login(settings: Settings) -> str:
    """Full login flow: OAuth2 consent in browser -> exchange code -> cache tokens."""
    access_token = request_oauth2_token(settings)
    logger.info("Login successful. Tokens cached.")
    return access_token


def is_logged_in(settings: Settings) -> bool:
    """Check if we have cached credentials."""
    cache = _load_secrets(settings)
    return bool(cache.get("refresh_token"))
