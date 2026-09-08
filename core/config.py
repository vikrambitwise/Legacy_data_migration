"""Platform configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    llm_api_key: SecretStr | None = None
    llm_provider: Literal["openai", "anthropic", "none"] = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None

    source_db_url: str = "sqlite:///./data/legacy_source.db"

    snowflake_account: str | None = None
    snowflake_user: str | None = None
    snowflake_password: SecretStr | None = None
    snowflake_warehouse: str = "COMPUTE_WH"
    snowflake_database: str = "MIGRATION_TARGET"
    snowflake_schema: str = "PUBLIC"
    snowflake_role: str | None = None
    snowflake_authenticator: str = "snowflake"
    snowflake_passcode: str | None = None

    google_application_credentials: str | None = None
    bigquery_project_id: str | None = None
    bigquery_dataset: str = "migration_target"

    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    confidence_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    target_warehouse: Literal["snowflake", "bigquery", "postgres", "sqlite"] = "sqlite"
    target_db_url: str = "sqlite:///./data/target_warehouse.db"

    table_filter: str = ""
    review_mode: Literal["cli", "file", "auto"] = "cli"
    review_file: str = "./runs/latest/review_decisions.json"
    enable_incremental: bool = False
    watermark_column: str = "created_ts"
    max_retries: int = 4
    retry_base_seconds: float = 1.0
    log_level: str = "INFO"

    @property
    def table_selection(self) -> list[str] | None:
        raw = (self.table_filter or "").strip()
        if not raw:
            return None
        return [t.strip() for t in raw.split(",") if t.strip()]

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key) and self.llm_provider != "none"

    def snowflake_url(self) -> str:
        password = self.snowflake_password.get_secret_value() if self.snowflake_password else ""
        user = self.snowflake_user or ""
        query = f"warehouse={self.snowflake_warehouse}"
        if self.snowflake_role:
            query += f"&role={self.snowflake_role}"
        return (
            f"snowflake://{quote_plus(user)}:{quote_plus(password)}"
            f"@{self.snowflake_account}/{self.snowflake_database}/{self.snowflake_schema}"
            f"?{query}"
        )

    def snowflake_connect_kwargs(self) -> dict:
        password = self.snowflake_password.get_secret_value() if self.snowflake_password else ""
        kwargs = {
            "user": self.snowflake_user,
            "password": password,
            "account": self.snowflake_account,
            "warehouse": self.snowflake_warehouse,
            "database": self.snowflake_database,
            "schema": self.snowflake_schema,
            "authenticator": self.snowflake_authenticator,
            "client_session_keep_alive": True,
        }
        if self.snowflake_authenticator in {"username_password_mfa", "externalbrowser"}:
            kwargs["client_store_temporary_credential"] = True
            kwargs["client_request_mfa_token"] = True
        if self.snowflake_passcode:
            kwargs["passcode"] = self.snowflake_passcode
        if self.snowflake_role:
            kwargs["role"] = self.snowflake_role
        if self.snowflake_authenticator == "externalbrowser":
            kwargs.pop("password", None)
        return kwargs


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    ROOT.joinpath("data").mkdir(exist_ok=True)
    ROOT.joinpath("runs").mkdir(exist_ok=True)
    return Settings()
