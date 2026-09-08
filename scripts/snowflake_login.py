"""Open a Snowflake browser login (required for MFA enrollment on trial accounts)."""

from __future__ import annotations

from core.config import get_settings


def main() -> None:
    import snowflake.connector

    settings = get_settings()
    kwargs = settings.snowflake_connect_kwargs()
    kwargs["authenticator"] = "externalbrowser"
    kwargs.pop("password", None)
    kwargs.pop("database", None)
    kwargs.pop("schema", None)
    print("A browser window should open. Sign in to Snowsight, enroll MFA if asked, then return here.")
    ctx = snowflake.connector.connect(**kwargs)
    row = ctx.cursor().execute("SELECT CURRENT_USER(), CURRENT_ACCOUNT(), CURRENT_VERSION()").fetchone()
    print("Snowflake login OK:", row)
    ctx.close()


if __name__ == "__main__":
    main()
