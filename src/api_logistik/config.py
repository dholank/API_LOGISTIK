import os
from pathlib import Path
from typing import Literal, Self

from dotenv import dotenv_values
from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from api_logistik.errors import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        hide_input_in_errors=True,
        env_ignore_empty=True,
        populate_by_name=True,
        case_sensitive=False,
    )

    environment: Literal["development", "production", "test"] = "development"
    oracle_dsn: SecretStr | None = Field(default=None, repr=False)
    oracle_user: SecretStr | None = Field(default=None, repr=False)
    oracle_password: SecretStr | None = Field(default=None, repr=False)
    oracle_writer_user: SecretStr | None = Field(default=None, repr=False)
    oracle_writer_password: SecretStr | None = Field(default=None, repr=False)
    oracle_mode: Literal["thin", "thick"] = "thin"
    oracle_client_lib_dir: Path | None = None
    oracle_wallet_dir: Path | None = None
    oracle_wallet_password: SecretStr | None = Field(default=None, repr=False)
    oracle_pool_min: int = Field(default=1, ge=0, le=50)
    oracle_pool_max: int = Field(default=5, ge=1, le=50)
    oracle_pool_increment: int = Field(default=1, ge=1, le=10)
    oracle_pool_wait_ms: int = Field(default=5000, ge=1, le=60000)
    oracle_connect_timeout: float = Field(default=5, gt=0, le=60)
    oracle_call_timeout_ms: int = Field(default=5000, ge=1, le=60000)
    docs_enabled: bool | None = None
    bind_host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    key_secret_store_dir: Path | None = None
    key_encryption_key: SecretStr | None = Field(default=None, repr=False)
    key_encryption_key_file: Path | None = Field(default=None, repr=False)
    operator_authorized: bool = False

    @model_validator(mode="after")
    def consistent(self) -> Self:
        credentials = (self.oracle_dsn, self.oracle_user, self.oracle_password)
        if any(credentials) and not all(credentials):
            raise ValueError("Oracle credentials must be supplied together")
        if bool(self.oracle_writer_user) != bool(self.oracle_writer_password):
            raise ValueError("Writer credentials must be supplied together")
        if self.oracle_pool_min > self.oracle_pool_max:
            raise ValueError("Pool minimum exceeds maximum")
        if self.oracle_mode == "thick" and self.oracle_client_lib_dir is None:
            raise ValueError("Explicit client library directory required for Thick mode")
        if self.environment == "production" and not all(credentials):
            raise ValueError("Oracle configuration required in production")
        if self.key_encryption_key and self.key_encryption_key_file:
            raise ValueError("Choose one encryption key source")
        return self

    @property
    def expose_docs(self) -> bool:
        return (
            self.docs_enabled if self.docs_enabled is not None else self.environment != "production"
        )


def load_settings(env_file: Path | None = None) -> Settings:
    file_path = env_file or Path(os.environ.get("API_LOGISTIK_ENV_FILE", ".env"))
    try:
        raw = (
            dotenv_values(file_path, interpolate=False, encoding="utf-8-sig")
            if file_path.is_file()
            else {}
        )
        names = set(Settings.model_fields)
        values = {
            k.lower(): v for k, v in raw.items() if k.lower() in names and v not in (None, "")
        }
        values.update(
            {k.lower(): v for k, v in os.environ.items() if k.lower() in names and v != ""}
        )
        return Settings.model_validate(values)
    except ValidationError, ValueError, OSError, UnicodeError:
        raise ConfigurationError() from None
