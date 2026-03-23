"""Application settings using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Environment variables are prefixed with FIND_MY_PHONE_ (e.g., FIND_MY_PHONE_APP_NAME).
    A .env file is loaded automatically if present.
    """

    model_config = SettingsConfigDict(
        env_prefix="FIND_MY_PHONE_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "find_my_phone"
    debug: bool = False
