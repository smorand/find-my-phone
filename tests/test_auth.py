"""Tests for the auth module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auth import (
    _generate_android_id,
    _get_android_id,
    _load_secrets,
    _save_secrets,
    exchange_for_aas_token,
    get_adm_token,
    is_logged_in,
    login,
    request_oauth_token,
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
    """Test is_logged_in returns True when AAS token exists."""
    _save_secrets(settings, {"aas_token": "fake_token"})
    assert is_logged_in(settings) is True


def test_exchange_for_aas_token_success(settings: Settings) -> None:
    """Test successful AAS token exchange."""
    with patch("auth.gpsoauth.exchange_token") as mock_exchange:
        mock_exchange.return_value = {"Token": "test_aas_token", "Email": "test@example.com"}
        token = exchange_for_aas_token(settings, "fake_oauth")
        assert token == "test_aas_token"
        cache = _load_secrets(settings)
        assert cache["aas_token"] == "test_aas_token"
        assert cache["username"] == "test@example.com"


def test_exchange_for_aas_token_failure(settings: Settings) -> None:
    """Test AAS token exchange failure."""
    with patch("auth.gpsoauth.exchange_token") as mock_exchange:
        mock_exchange.return_value = {"Error": "BadAuth"}
        with pytest.raises(RuntimeError, match="AAS token exchange failed"):
            exchange_for_aas_token(settings, "bad_oauth")


def test_get_adm_token_not_logged_in(settings: Settings) -> None:
    """Test ADM token request when not logged in."""
    with pytest.raises(RuntimeError, match="Not logged in"):
        get_adm_token(settings)


def test_get_adm_token_success(settings: Settings) -> None:
    """Test successful ADM token retrieval."""
    _save_secrets(settings, {"aas_token": "test_aas", "username": "test@example.com", "android_id": "abc123"})
    with patch("auth.gpsoauth.perform_oauth") as mock_oauth:
        mock_oauth.return_value = {"Auth": "test_adm_token"}
        token = get_adm_token(settings)
        assert token == "test_adm_token"


def test_get_adm_token_failure(settings: Settings) -> None:
    """Test ADM token request failure."""
    _save_secrets(settings, {"aas_token": "test_aas", "username": "test@example.com", "android_id": "abc123"})
    with patch("auth.gpsoauth.perform_oauth") as mock_oauth:
        mock_oauth.return_value = {"Error": "BadToken"}
        with pytest.raises(RuntimeError, match="ADM token request failed"):
            get_adm_token(settings)


def test_request_oauth_token_silent_success(settings: Settings) -> None:
    """Test silent oauth_token extraction from Chrome cookies."""
    mock_response = MagicMock()
    mock_response.cookies = MagicMock()
    mock_response.cookies.get.return_value = "silent_oauth_token"

    with (
        patch("auth._get_chrome_cookies", return_value={"SID": "abc", "SSID": "def"}),
        patch("auth.httpx.Client") as mock_client_cls,
    ):
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        token = request_oauth_token(settings)
        assert token == "silent_oauth_token"


def test_request_oauth_token_fallback_to_browser(settings: Settings) -> None:
    """Test fallback to browser when silent auth fails."""
    with (
        patch("auth._get_chrome_cookies", return_value={}),
        patch("auth._obtain_oauth_token_via_browser", return_value="browser_token"),
    ):
        token = request_oauth_token(settings)
        assert token == "browser_token"


def test_login_full_flow(settings: Settings) -> None:
    """Test full login flow."""
    with (
        patch("auth.request_oauth_token") as mock_oauth,
        patch("auth.gpsoauth.exchange_token") as mock_exchange,
        patch("auth.gpsoauth.perform_oauth") as mock_perform,
    ):
        mock_oauth.return_value = "fake_oauth_token"
        mock_exchange.return_value = {"Token": "fake_aas", "Email": "user@example.com"}
        mock_perform.return_value = {"Auth": "fake_adm_token"}

        result = login(settings)
        assert result == "fake_adm_token"
        mock_oauth.assert_called_once_with(settings)
