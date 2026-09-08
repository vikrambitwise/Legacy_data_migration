-- Runs automatically when the Postgres container is first created.
-- Creates the target warehouse database used for local (non-Snowflake/BigQuery) loads.

CREATE DATABASE migration_target;
GRANT ALL PRIVILEGES ON DATABASE migration_target TO migrate;
