"""Process-wide Snowflake session so one MFA TOTP covers DDL, load, and validation."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from core.config import get_settings
from core.logging import get_logger

logger = get_logger("connectors.snowflake")

_raw: Any = None


class _KeepAliveConnection:
    """SQLAlchemy may call close() on check-in; keep the shared MFA session alive."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def close(self) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def connect_snowflake(*, bootstrap: bool = True) -> Any:
    """Return a live native Snowflake connection, authenticating at most once per process."""
    global _raw
    if _raw is not None:
        try:
            if not _raw.is_closed():
                return _raw
        except Exception:
            _raw = None
    import snowflake.connector

    settings = get_settings()
    kwargs = settings.snowflake_connect_kwargs()
    logger.info(
        "Opening Snowflake session account=%s user=%s authenticator=%s",
        settings.snowflake_account,
        settings.snowflake_user,
        settings.snowflake_authenticator,
    )
    _raw = snowflake.connector.connect(**kwargs)
    if bootstrap:
        bootstrap_namespace(_raw)
    return _raw


def bootstrap_namespace(ctx: Any) -> None:
    settings = get_settings()
    warehouse = settings.snowflake_warehouse
    database = settings.snowflake_database
    schema = settings.snowflake_schema
    cur = ctx.cursor()
    try:
        try:
            cur.execute("ALTER ACCOUNT SET ALLOW_CLIENT_MFA_CACHING = TRUE")
            logger.info("Enabled Snowflake ALLOW_CLIENT_MFA_CACHING for later reconnects")
        except Exception as exc:
            logger.warning("Could not enable MFA token caching: %s", exc)
        try:
            cur.execute(f'USE WAREHOUSE "{warehouse}"')
        except Exception:
            cur.execute(
                f'CREATE WAREHOUSE IF NOT EXISTS "{warehouse}" '
                'WAREHOUSE_SIZE = "XSMALL" AUTO_SUSPEND = 60 AUTO_RESUME = TRUE'
            )
            cur.execute(f'USE WAREHOUSE "{warehouse}"')
        cur.execute(f'CREATE DATABASE IF NOT EXISTS "{database}"')
        cur.execute(f'USE DATABASE "{database}"')
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cur.execute(f'USE SCHEMA "{schema}"')
    finally:
        cur.close()


@lru_cache(maxsize=1)
def get_snowflake_engine() -> Engine:
    settings = get_settings()

    def creator() -> _KeepAliveConnection:
        return _KeepAliveConnection(connect_snowflake())

    return create_engine(
        settings.snowflake_url(),
        creator=creator,
        poolclass=StaticPool,
        future=True,
    )
