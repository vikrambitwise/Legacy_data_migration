"""Source and target SQLAlchemy engine factories."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from core.config import get_settings
from core.logging import get_logger

logger = get_logger("connectors")


def _engine(url: str, *, sqlite_fk: bool = False) -> Engine:
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        engine = create_engine(url, **kwargs)

        if sqlite_fk:
            from sqlalchemy import event

            @event.listens_for(engine, "connect")
            def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        return engine
    if url.startswith("postgresql"):
        kwargs["connect_args"] = {"connect_timeout": 8}
    return create_engine(url, **kwargs)


def get_source_engine(url: str | None = None) -> Engine:
    settings = get_settings()
    resolved = url or settings.source_db_url
    logger.info("Opening source engine dialect=%s", resolved.split(":")[0])
    return _engine(resolved, sqlite_fk=True)


def get_target_engine(url: str | None = None) -> Engine:
    settings = get_settings()
    warehouse = settings.target_warehouse
    if warehouse == "snowflake":
        from connectors.snowflake_session import get_snowflake_engine

        return get_snowflake_engine()
    if warehouse == "bigquery":
        project = settings.bigquery_project_id
        dataset = settings.bigquery_dataset
        bq_url = url or f"bigquery://{project}/{dataset}"
        return _engine(bq_url)
    return _engine(url or settings.target_db_url, sqlite_fk=True)


def redact_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        creds, host = rest.split("@", 1)
        if ":" in creds:
            user = creds.split(":", 1)[0]
            return f"{scheme}://{user}:***@{host}"
    return f"{scheme}://{rest}"
