"""Create the native PostgreSQL databases used as the legacy source (and optional local target)."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from core.logging import get_logger

logger = get_logger("source.bootstrap_postgres")


def ensure_database(admin_url: str, database: str) -> None:
    url = make_url(admin_url)
    maintenance = url.set(database="postgres")
    engine = create_engine(maintenance.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT", future=True)
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": database},
        ).scalar()
        if exists:
            logger.info("PostgreSQL database %s already exists", database)
            return
        conn.execute(text(f'CREATE DATABASE "{database}"'))
        logger.info("Created PostgreSQL database %s", database)
    engine.dispose()


def ensure_from_source_url(source_url: str) -> None:
    url = make_url(source_url)
    if url.get_backend_name() not in {"postgresql", "postgres"}:
        return
    database = url.database
    if not database:
        raise RuntimeError("SOURCE_DB_URL must include a database name, e.g. .../legacy_db")
    ensure_database(source_url, database)
