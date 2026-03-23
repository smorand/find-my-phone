"""Tests for the config module."""

import pytest

from config import Settings


def test_default_settings() -> None:
    """Test that default settings are loaded."""
    settings = Settings()
    assert settings.app_name == "find_my_phone"
    assert settings.debug is False


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that settings can be overridden via environment variables."""
    monkeypatch.setenv("FIND_MY_PHONE_APP_NAME", "test_app")
    monkeypatch.setenv("FIND_MY_PHONE_DEBUG", "true")
    settings = Settings()
    assert settings.app_name == "test_app"
    assert settings.debug is True
