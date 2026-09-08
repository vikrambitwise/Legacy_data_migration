"""Extract → transform → load with retry, checkpoints, rejects, and rollback."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tenacity import retry, stop_after_attempt, wait_exponential

from audit.audit_logger import AuditLogger
from connectors.db import get_source_engine, get_target_engine
from connectors.sql import quote_ident
from core.config import get_settings
from core.logging import get_logger
from core.models import SchemaProfile, TransformationRule
from etl.transforms import apply_rule
from review.human_review import UnapprovedMappingError

logger = get_logger("etl.migration_executor")


class MigrationExecutor:
    def __init__(
        self,
        run_id: str,
        artifact_dir: Path,
        audit: AuditLogger | None = None,
        source: Engine | None = None,
        target: Engine | None = None,
    ) -> None:
        self.run_id = run_id
        self.artifact_dir = artifact_dir
        self.audit = audit or AuditLogger()
        self.settings = get_settings()
        self.source = source or get_source_engine()
        self.target = target or get_target_engine()
        self.reject_dir = artifact_dir / "rejects"
        self.reject_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        profile: SchemaProfile,
        rules: list[TransformationRule],
        table_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        self._assert_executable(rules)
        if self.settings.target_warehouse == "snowflake":
            from connectors.snowflake_session import connect_snowflake

            connect_snowflake()
        grouped = self._group_rules(rules)
        targets = sorted({table_rules[0].target_table for table_rules in grouped.values()})
        with self.target.begin() as conn:
            for table in reversed(targets):
                ident = quote_ident(table, self.target)
                conn.execute(text(f"DROP TABLE IF EXISTS {ident}"))
        load_order = [t for t in profile.load_order if t in grouped]
        if table_filter:
            load_order = [t for t in load_order if t in set(table_filter)]
        stats: dict[str, Any] = {"tables": {}, "rejects": []}
        created_targets: list[str] = []
        try:
            for source_table in load_order:
                table_rules = grouped[source_table]
                target_table = table_rules[0].target_table
                extracted = self._extract(source_table)
                extract_dir = self.artifact_dir / "extracted"
                extract_dir.mkdir(parents=True, exist_ok=True)
                extracted.to_csv(extract_dir / f"{source_table}.csv", index=False)
                transformed, rejects = self._transform(extracted, table_rules)
                self._write_rejects(source_table, rejects)
                self._ensure_target_table(target_table, transformed)
                loaded = self._load(target_table, transformed)
                created_targets.append(target_table)
                stats["tables"][source_table] = {
                    "target_table": target_table,
                    "extracted": int(len(extracted)),
                    "loaded": int(loaded),
                    "rejected": int(len(rejects)),
                }
                self.audit.log(
                    self.run_id,
                    node="migration_executor",
                    action="table_loaded",
                    payload=stats["tables"][source_table],
                )
                self._checkpoint({"completed_tables": created_targets, "stats": stats})
            stats["status"] = "loaded"
            stats["target_tables"] = created_targets
            return stats
        except Exception as exc:
            logger.exception("Migration failed; initiating rollback")
            self.audit.log(
                self.run_id,
                node="migration_executor",
                action="failure",
                payload={"error": str(exc), "completed": created_targets},
            )
            self.rollback(created_targets)
            raise

    def rollback(self, target_tables: list[str] | None = None) -> None:
        tables = target_tables or self._checkpoint_tables()
        with self.target.begin() as conn:
            for table in reversed(tables):
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {quote_ident(table, self.target)}"))
                    logger.info("Rolled back target table %s", table)
                except Exception as exc:
                    logger.warning("Rollback drop failed for %s: %s", table, exc)
        self.audit.log(
            self.run_id,
            node="migration_executor",
            action="rollback_completed",
            payload={"tables": tables},
        )

    def _assert_executable(self, rules: list[TransformationRule]) -> None:
        threshold = self.settings.confidence_threshold
        blocked = [r for r in rules if not r.is_approved_for_execution(threshold)]
        if blocked:
            names = [f"{r.source_table}.{r.source_column}" for r in blocked]
            raise UnapprovedMappingError(
                "Unapproved rules blocked pipeline: " + ", ".join(names)
            )

    def _group_rules(self, rules: list[TransformationRule]) -> dict[str, list[TransformationRule]]:
        grouped: dict[str, list[TransformationRule]] = defaultdict(list)
        for rule in rules:
            grouped[rule.source_table].append(rule)
        return grouped

    def _extract(self, table: str) -> pd.DataFrame:
        return self._extract_with_retry(table)

    def _extract_with_retry(self, table: str) -> pd.DataFrame:
        @retry(
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(
                multiplier=self.settings.retry_base_seconds, min=1, max=30
            ),
            reraise=True,
        )
        def _inner() -> pd.DataFrame:
            logger.info("Extracting %s", table)
            query = f"SELECT * FROM {quote_ident(table, self.source)}"
            if self.settings.enable_incremental:
                watermark_path = self.artifact_dir / "watermarks.json"
                watermarks = {}
                if watermark_path.exists():
                    watermarks = json.loads(watermark_path.read_text(encoding="utf-8"))
                last = watermarks.get(table)
                col = quote_ident(self.settings.watermark_column, self.source)
                if last:
                    query = (
                        f"SELECT * FROM {quote_ident(table, self.source)} "
                        f"WHERE {col} > '{last}'"
                    )
            return pd.read_sql(query, self.source)

        return _inner()

    def _transform(
        self, frame: pd.DataFrame, rules: list[TransformationRule]
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        out = pd.DataFrame(index=frame.index)
        for rule in rules:
            if rule.source_column not in frame.columns:
                logger.warning("Missing source column %s", rule.source_column)
                continue
            out[rule.target_column] = apply_rule(frame[rule.source_column], rule)
        reject_mask = pd.Series(False, index=frame.index)
        for rule in rules:
            if rule.transform_type == "date" and rule.target_column in out:
                src = frame[rule.source_column]
                present = src.notna() & src.astype(str).str.strip().ne("")
                reject_mask = reject_mask | (present & out[rule.target_column].isna())
        rejects = frame.loc[reject_mask].copy()
        loaded = out.loc[~reject_mask].copy()
        loaded["_migration_run_id"] = self.run_id
        for col in loaded.columns:
            if col == "_migration_run_id":
                continue
            if col.endswith("_id") or col in {"department_id", "staff_id", "patient_id"}:
                loaded[col] = pd.to_numeric(loaded[col], errors="coerce").astype("Int64")
        return loaded, rejects

    def _write_rejects(self, table: str, rejects: pd.DataFrame) -> None:
        if rejects.empty:
            return
        path = self.reject_dir / f"{table}_rejects.csv"
        rejects.to_csv(path, index=False)
        logger.info("Wrote %s rejects for %s", len(rejects), table)

    def _ensure_target_table(self, table: str, frame: pd.DataFrame) -> None:
        cols = []
        for name, dtype in frame.dtypes.items():
            sql_type = "VARCHAR"
            if pd.api.types.is_integer_dtype(dtype):
                sql_type = "NUMBER" if self.settings.target_warehouse == "snowflake" else "BIGINT"
            elif pd.api.types.is_float_dtype(dtype):
                sql_type = "FLOAT" if self.settings.target_warehouse == "snowflake" else "DOUBLE PRECISION"
            elif pd.api.types.is_bool_dtype(dtype):
                sql_type = "BOOLEAN"
            cols.append(f"{quote_ident(str(name), self.target)} {sql_type}")
        ddl = f"CREATE TABLE IF NOT EXISTS {quote_ident(table, self.target)} ({', '.join(cols)})"
        with self.target.begin() as conn:
            if self.settings.target_warehouse == "bigquery":
                conn.execute(text(ddl))
            else:
                conn.execute(text(ddl))

    def _load(self, table: str, frame: pd.DataFrame) -> int:
        return self._load_with_retry(table, frame)

    def _load_with_retry(self, table: str, frame: pd.DataFrame) -> int:
        @retry(
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(
                multiplier=self.settings.retry_base_seconds, min=1, max=30
            ),
            reraise=True,
        )
        def _inner() -> int:
            logger.info("Loading %s rows into %s", len(frame), table)
            if self.settings.target_warehouse == "bigquery":
                return self._load_bigquery(table, frame)
            if self.settings.target_warehouse == "snowflake":
                return self._load_snowflake(table, frame)
            frame.to_sql(
                table,
                self.target,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
            return len(frame)

        return _inner()

    def _load_snowflake(self, table: str, frame: pd.DataFrame) -> int:
        from snowflake.connector.pandas_tools import write_pandas

        from connectors.snowflake_session import connect_snowflake

        payload = frame.copy()
        for col in payload.columns:
            if str(payload[col].dtype) == "Int64":
                payload[col] = payload[col].astype(object).where(payload[col].notna(), None)
        ctx = connect_snowflake()
        success, _nchunks, nrows, _ = write_pandas(
            ctx,
            payload,
            table_name=table,
            database=self.settings.snowflake_database,
            schema=self.settings.snowflake_schema,
            quote_identifiers=True,
            auto_create_table=False,
            overwrite=False,
        )
        if not success:
            raise RuntimeError(f"Snowflake write_pandas reported failure for {table}")
        return int(nrows)

    def _load_bigquery(self, table: str, frame: pd.DataFrame) -> int:
        from google.cloud import bigquery

        settings = self.settings
        client = bigquery.Client(project=settings.bigquery_project_id)
        dest = f"{settings.bigquery_project_id}.{settings.bigquery_dataset}.{table}"
        job = client.load_table_from_dataframe(frame, dest)
        job.result()
        return len(frame)

    def _checkpoint(self, payload: dict[str, Any]) -> None:
        path = self.artifact_dir / "executor_checkpoint.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _checkpoint_tables(self) -> list[str]:
        path = self.artifact_dir / "executor_checkpoint.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("completed_tables") or [])
