"""Connectivity checks for Postgres, Snowflake, and Great Expectations."""

from __future__ import annotations

from core.config import get_settings
from core.logging import get_logger

logger = get_logger("stack_check")


def verify() -> dict[str, str]:
    settings = get_settings()
    results: dict[str, str] = {}

    try:
        import great_expectations as gx

        results["great_expectations"] = f"ok ({gx.__version__})"
    except Exception as exc:
        results["great_expectations"] = f"FAIL: {exc}"

    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine.url import make_url

        url = make_url(settings.source_db_url)
        if url.get_backend_name() in {"postgresql", "postgres"}:
            url = url.set(database="postgres")
        engine = create_engine(
            url.render_as_string(hide_password=False),
            future=True,
            connect_args={"connect_timeout": 8} if url.get_backend_name() in {"postgresql", "postgres"} else {},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        results["source"] = f"ok ({engine.dialect.name} user={url.username} db=postgres)"
        engine.dispose()
    except Exception as exc:
        results["source"] = f"FAIL: {exc}"

    try:
        warehouse = settings.target_warehouse
        if warehouse == "snowflake":
            missing = [
                name
                for name, val in {
                    "SNOWFLAKE_ACCOUNT": settings.snowflake_account,
                    "SNOWFLAKE_USER": settings.snowflake_user,
                    "SNOWFLAKE_PASSWORD": settings.snowflake_password,
                }.items()
                if not val
            ]
            if missing:
                raise RuntimeError("missing " + ", ".join(missing))
            from connectors.snowflake_session import connect_snowflake

            ctx = connect_snowflake()
            row = ctx.cursor().execute("SELECT CURRENT_VERSION()").fetchone()
            results["target"] = f"ok (snowflake {row[0] if row else ''} account={settings.snowflake_account})"
        else:
            from sqlalchemy import text as sql_text

            from connectors.db import get_target_engine

            engine = get_target_engine()
            with engine.connect() as conn:
                conn.execute(sql_text("SELECT 1"))
            results["target"] = f"ok ({warehouse}/{engine.dialect.name})"
    except Exception as exc:
        results["target"] = f"FAIL: {exc}"

    return results
