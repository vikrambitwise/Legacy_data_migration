"""Dialect-aware SQL identifier quoting."""

from __future__ import annotations

from sqlalchemy.engine import Engine


def quote_ident(name: str, dialect: str | Engine) -> str:
    dialect_name = dialect if isinstance(dialect, str) else dialect.dialect.name
    cleaned = name.replace('"', "")
    if dialect_name in {"snowflake", "postgresql", "postgres", "sqlite"}:
        return f'"{cleaned}"'
    return cleaned


def qualify_table(name: str, dialect: str | Engine) -> str:
    return quote_ident(name, dialect)
