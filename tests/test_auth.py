"""Tests for the auth module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auth import (
    _generate_android_id,
    _get_android_id,
    _load_client_credentials,
    _load_secrets,
    _save_secrets,
    _wait_for_auth_code,
    get_adm_token,
    is_logged_in,
    login,
    refresh_access_token,
    request_oauth2_token,
)
from config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Create test settings with a temporary secrets directory."""
    return Settings(secrets_dir=tmp_path)


def test_generate_android_id() -> None:
    """Test that generated Android ID is a 16-char hex string."""
    aid = _generate_android_id()
    assert len(aid) == 16
    int(aid, 16)


def test_save_and_load_secrets(settings: Settings) -> None:
    """Test saving and loading secrets to/from disk."""
    data = {"key": "value", "number": 42}
    _save_secrets(settings, data)
    loaded = _load_secrets(settings)
    assert loaded == data


def test_load_secrets_empty(settings: Settings) -> None:
    """Test loading secrets when file doesn't exist."""
    loaded = _load_secrets(settings)
    assert loaded == {}


def test_get_android_id_creates_and_caches(settings: Settings) -> None:
    """Test that get_android_id creates an ID and caches it."""
    aid1 = _get_android_id(settings)
    assert len(aid1) == 16
    aid2 = _get_android_id(settings)
    assert aid1 == aid2


def test_is_logged_in_false(settings: Settings) -> None:
    """Test is_logged_in returns False when not logged in."""
    assert is_logged_in(settings) is False


def test_is_logged_in_true(settings: Settings) -> None:
    """Test is_logged_in returns True when refresh token exists."""
    _save_secrets(settings, {"refresh_token": "fake_refresh"})
    assert is_logged_in(settings) is True


def test_get_adm_token_not_logged_in(settings: Settings) -> None:
    """Test get_adm_token when not logged in."""
    with pytest.raises(RuntimeError, match="Not logged in"):
        get_adm_token(settings)


def test_get_adm_token_success(settings: Settings) -> None:
    """Test successful access token retrieval from cache."""
    _save_secrets(settings, {"access_token": "test_token"})
    token = get_adm_token(settings)
    assert token == "test_token"


def test_refresh_access_token_success(settings: Settings) -> None:
    """Test successful token refresh."""
    _save_secrets(settings, {"refresh_token": "test_refresh"})

    mock_response = MagicMock()
    mock_response.json.return_value = {"access_token": "new_access_token"}

    with (
        patch("auth._load_client_credentials") as mock_creds,
        patch("auth.httpx.Client") as mock_client_cls,
    ):
        mock_creds.return_value = {"client_id": "id", "client_secret": "secret"}
        mock_client_cls.return_value.__enter__ = MagicMock(
            return_value=MagicMock(post=MagicMock(return_value=mock_response))
        )
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        token = refresh_access_token(settings)
        assert token == "new_access_token"
        cache = _load_secrets(settings)
        assert cache["access_token"] == "new_access_token"


def test_refresh_access_token_no_refresh_token(settings: Settings) -> None:
    """Test token refresh when no refresh token is cached."""
    with pytest.raises(RuntimeError, match="No refresh token"):
        refresh_access_token(settings)


def test_refresh_access_token_failure(settings: Settings) -> None:
    """Test token refresh failure."""
    _save_secrets(settings, {"refresh_token": "test_refresh"})

    mock_response = MagicMock()
    mock_response.json.return_value = {"error": "invalid_grant"}

    with (
        patch("auth._load_client_credentials") as mock_creds,
        patch("auth.httpx.Client") as mock_client_cls,
    ):
        mock_creds.return_value = {"client_id": "id", "client_secret": "secret"}
        mock_client_cls.return_value.__enter__ = MagicMock(
            return_value=MagicMock(post=MagicMock(return_value=mock_response))
        )
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(RuntimeError, match="Token refresh failed"):
            refresh_access_token(settings)


def test_load_client_credentials_success(tmp_path: Path) -> None:
    """Test loading OAuth2 client credentials."""
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"web": {"client_id": "test_id", "client_secret": "test_secret"}}')
    with patch("auth.CREDENTIALS_PATH", str(creds_file)):
        creds = _load_client_credentials()
        assert creds["client_id"] == "test_id"
        assert creds["client_secret"] == "test_secret"


def test_load_client_credentials_missing(tmp_path: Path) -> None:
    """Test loading credentials when file is missing."""
    with (
        patch("auth.CREDENTIALS_PATH", str(tmp_path / "nonexistent.json")),
        pytest.raises(FileNotFoundError, match="OAuth2 credentials not found"),
    ):
        _load_client_credentials()


def test_load_client_credentials_invalid(tmp_path: Path) -> None:
    """Test loading credentials with missing fields."""
    creds_file = tmp_path / "creds.json"
    creds_file.write_text('{"web": {"client_id": ""}}')
    with (
        patch("auth.CREDENTIALS_PATH", str(creds_file)),
        pytest.raises(ValueError, match="Missing client_id"),
    ):
        _load_client_credentials()


def test_wait_for_auth_code_success() -> None:
    """Test waiting for auth code via local server."""
    import threading  # noqa: PLC0415
    import time  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    def send_callback() -> None:
        time.sleep(0.5)
        urllib.request.urlopen("http://127.0.0.1:8002/?code=test_auth_code")

    thread = threading.Thread(target=send_callback, daemon=True)
    thread.start()
    code = _wait_for_auth_code()
    assert code == "test_auth_code"


def test_wait_for_auth_code_error() -> None:
    """Test auth code callback with error."""
    import threading  # noqa: PLC0415
    import time  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    def send_error() -> None:
        import contextlib  # noqa: PLC0415

        time.sleep(0.5)
        with contextlib.suppress(Exception):
            urllib.request.urlopen("http://127.0.0.1:8002/?error=access_denied")

    thread = threading.Thread(target=send_error, daemon=True)
    thread.start()
    with pytest.raises(RuntimeError, match="OAuth2 login denied"):
        _wait_for_auth_code()


def test_request_oauth2_token_success(settings: Settings) -> None:
    """Test full OAuth2 token request flow."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "new_token",
        "refresh_token": "new_refresh",
    }

    with (
        patch("auth._load_client_credentials") as mock_creds,
        patch("auth._wait_for_auth_code", return_value="test_code"),
        patch("auth.httpx.Client") as mock_client_cls,
        patch("webbrowser.open") as mock_open,
    ):
        mock_creds.return_value = {"client_id": "id", "client_secret": "secret"}
        mock_client_cls.return_value.__enter__ = MagicMock(
            return_value=MagicMock(post=MagicMock(return_value=mock_response))
        )
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        token = request_oauth2_token(settings)
        assert token == "new_token"
        mock_open.assert_called_once()

        cache = _load_secrets(settings)
        assert cache["access_token"] == "new_token"
        assert cache["refresh_token"] == "new_refresh"


def test_request_oauth2_token_failure(settings: Settings) -> None:
    """Test OAuth2 token exchange failure."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"error": "invalid_grant", "error_description": "Bad code"}

    with (
        patch("auth._load_client_credentials") as mock_creds,
        patch("auth._wait_for_auth_code", return_value="bad_code"),
        patch("auth.httpx.Client") as mock_client_cls,
        patch("webbrowser.open"),
    ):
        mock_creds.return_value = {"client_id": "id", "client_secret": "secret"}
        mock_client_cls.return_value.__enter__ = MagicMock(
            return_value=MagicMock(post=MagicMock(return_value=mock_response))
        )
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(RuntimeError, match="Bad code"):
            request_oauth2_token(settings)


def test_login_full_flow(settings: Settings) -> None:
    """Test full login flow."""
    with patch("auth.request_oauth2_token") as mock_oauth:
        mock_oauth.return_value = "fake_access_token"
        result = login(settings)
        assert result == "fake_access_token"
        mock_oauth.assert_called_once_with(settings)
