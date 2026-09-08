"""Great Expectations checkpoints: source baseline, post-extraction, post-load."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.engine import Engine

from connectors.sql import quote_ident
from core.logging import get_logger
from core.models import SchemaProfile, ValidationCheckpointResult

logger = get_logger("validation.ge_runner")

SUITE_DIR = Path(__file__).resolve().parent / "great_expectations" / "expectations"


class ValidationBlocked(RuntimeError):
    """Raised when a checkpoint fails and the pipeline must stop."""


class GERunner:
    def __init__(self, artifact_dir: Path, audit: AuditLogger | None = None) -> None:
        self.artifact_dir = artifact_dir
        self.audit = audit or AuditLogger()
        self.out_dir = artifact_dir / "validation"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def source_baseline(self, run_id: str, profile: SchemaProfile, engine: Engine) -> ValidationCheckpointResult:
        results: list[dict[str, Any]] = []
        for table in profile.tables:
            df = pd.read_sql(f"SELECT * FROM {quote_ident(table.name, engine)}", engine)
            results.extend(self._run_table_suite("source_baseline", table.name, df, profile))
        return self._finalize(run_id, "source_baseline", results)

    def post_extraction(
        self, run_id: str, profile: SchemaProfile, frames: dict[str, pd.DataFrame]
    ) -> ValidationCheckpointResult:
        results: list[dict[str, Any]] = []
        for table in profile.tables:
            df = frames.get(table.name)
            if df is None:
                continue
            results.extend(self._run_table_suite("post_extraction", table.name, df, profile))
        return self._finalize(run_id, "post_extraction", results)

    def post_load(
        self,
        run_id: str,
        profile: SchemaProfile,
        target_engine: Engine,
        source_to_target: dict[str, str],
    ) -> ValidationCheckpointResult:
        results: list[dict[str, Any]] = []
        for table in profile.tables:
            target = source_to_target.get(table.name)
            if not target:
                continue
            df = pd.read_sql(f"SELECT * FROM {quote_ident(target, target_engine)}", target_engine)
            results.extend(self._run_table_suite("post_load", target, df, profile, source_name=table.name))
        return self._finalize(run_id, "post_load", results)

    def _run_table_suite(
        self,
        checkpoint: str,
        table_name: str,
        df: pd.DataFrame,
        profile: SchemaProfile,
        source_name: str | None = None,
    ) -> list[dict[str, Any]]:
        src = next((t for t in profile.tables if t.name == (source_name or table_name)), None)
        expectations = self._expectations_for(src, df, checkpoint, table_name=table_name)
        gx_results = self._try_great_expectations(df, expectations, f"{checkpoint}_{table_name}")
        if gx_results is not None:
            return gx_results
        return self._pandas_expectations(df, expectations, table_name)

    def _expectations_for(self, table, df: pd.DataFrame, checkpoint: str, table_name: str = "") -> list[dict[str, Any]]:
        expectations: list[dict[str, Any]] = [
            {
                "type": "expect_table_row_count_to_be_between",
                "kwargs": {"min_value": 1, "max_value": 10_000_000},
                "meta": {"checkpoint": checkpoint},
            }
        ]
        if table is None:
            return expectations
        for col in table.columns:
            if col.is_pk and col.name in df.columns:
                expectations.append(
                    {
                        "type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": col.name},
                    }
                )
                expectations.append(
                    {
                        "type": "expect_column_values_to_be_unique",
                        "kwargs": {"column": col.name},
                    }
                )
            if col.null_rate == 0 and col.name in df.columns:
                expectations.append(
                    {
                        "type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": col.name},
                    }
                )
        pk_by_table = {
            "departments": "department_id",
            "staff": "staff_id",
            "patients": "patient_id",
            "admissions": "admission_id",
            "encounters": "encounter_id",
            "invoices": "invoice_id",
            "lab_results": "result_id",
        }
        pk_col = pk_by_table.get(table_name)
        if pk_col and pk_col in df.columns:
            expectations.append(
                {"type": "expect_column_values_to_not_be_null", "kwargs": {"column": pk_col}}
            )
            expectations.append(
                {"type": "expect_column_values_to_be_unique", "kwargs": {"column": pk_col}}
            )
        # Post-load business rule: patient_status / billing_status closed sets
        if "patient_status" in df.columns:
            expectations.append(
                {
                    "type": "expect_column_values_to_be_in_set",
                    "kwargs": {
                        "column": "patient_status",
                        "value_set": ["Active", "Discharged", "Inactive", "Suspended", None],
                    },
                }
            )
        if "billing_status" in df.columns:
            expectations.append(
                {
                    "type": "expect_column_values_to_be_in_set",
                    "kwargs": {
                        "column": "billing_status",
                        "value_set": ["Draft", "Submitted", "Paid", "Void", None],
                    },
                }
            )
        return [e for e in expectations if e.get("kwargs", {}).get("column") is not False]

    def _try_great_expectations(
        self, df: pd.DataFrame, expectations: list[dict[str, Any]], suite_name: str
    ) -> list[dict[str, Any]] | None:
        try:
            import great_expectations as gx  # noqa: F401
        except Exception as exc:
            logger.warning("great_expectations import failed (%s); using pandas validator", exc)
            return None
        try:
            return self._gx_pandas(df, expectations, suite_name)
        except Exception as exc:
            logger.warning("GX execution failed (%s); using pandas validator", exc)
            return None

    def _gx_pandas(
        self, df: pd.DataFrame, expectations: list[dict[str, Any]], suite_name: str
    ) -> list[dict[str, Any]]:
        """GX 1.x fluent API against an in-memory pandas dataframe."""
        import great_expectations as gx

        context = gx.get_context(mode="ephemeral")
        data_source = context.data_sources.add_pandas(name=f"pandas_{suite_name}")
        asset = data_source.add_dataframe_asset(name=f"asset_{suite_name}")
        batch_def = asset.add_batch_definition_whole_dataframe(f"batch_{suite_name}")
        batch = batch_def.get_batch(batch_parameters={"dataframe": df})
        results = []
        for spec in expectations:
            column = spec.get("kwargs", {}).get("column")
            if column and column not in df.columns:
                continue
            etype = spec["type"]
            try:
                if etype == "expect_table_row_count_to_be_between":
                    expectation = gx.expectations.ExpectTableRowCountToBeBetween(
                        min_value=spec["kwargs"]["min_value"],
                        max_value=spec["kwargs"]["max_value"],
                    )
                elif etype == "expect_column_values_to_not_be_null":
                    expectation = gx.expectations.ExpectColumnValuesToNotBeNull(column=column)
                elif etype == "expect_column_values_to_be_unique":
                    expectation = gx.expectations.ExpectColumnValuesToBeUnique(column=column)
                elif etype == "expect_column_values_to_be_in_set":
                    expectation = gx.expectations.ExpectColumnValuesToBeInSet(
                        column=column, value_set=[v for v in spec["kwargs"]["value_set"] if v is not None]
                    )
                else:
                    continue
                result = batch.validate(expectation)
                success = bool(getattr(result, "success", False))
                results.append(
                    {
                        "expectation": etype,
                        "success": success,
                        "kwargs": spec.get("kwargs"),
                        "engine": "great_expectations",
                    }
                )
            except Exception as exc:
                results.append({"expectation": etype, "success": False, "error": str(exc)})
        return results

    def _pandas_expectations(
        self, df: pd.DataFrame, expectations: list[dict[str, Any]], table_name: str
    ) -> list[dict[str, Any]]:
        results = []
        for spec in expectations:
            etype = spec["type"]
            kwargs = spec.get("kwargs") or {}
            column = kwargs.get("column")
            if column is not None and column not in df.columns:
                continue
            success = True
            detail: dict[str, Any] = {}
            if etype == "expect_table_row_count_to_be_between":
                n = len(df)
                success = kwargs["min_value"] <= n <= kwargs["max_value"]
                detail = {"row_count": n}
            elif column and column not in df.columns:
                success = False
                detail = {"missing_column": column}
            elif etype == "expect_column_values_to_not_be_null":
                nulls = int(df[column].isna().sum())
                success = nulls == 0
                detail = {"nulls": nulls}
            elif etype == "expect_column_values_to_be_unique":
                dupes = int(df[column].duplicated().sum())
                success = dupes == 0
                detail = {"duplicates": dupes}
            elif etype == "expect_column_values_to_be_in_set":
                allowed = set(kwargs.get("value_set") or [])
                present = set(df[column].dropna().astype(str)) | ({None} if df[column].isna().any() else set())
                # Compare loosely
                allowed_str = {str(v) if v is not None else None for v in allowed}
                extras = [v for v in df[column].dropna().unique() if str(v) not in allowed_str and v is not None]
                success = len(extras) == 0
                detail = {"unexpected": [str(x) for x in extras[:20]]}
            results.append(
                {
                    "table": table_name,
                    "expectation": etype,
                    "success": success,
                    "kwargs": kwargs,
                    "detail": detail,
                    "engine": "pandas_fallback",
                }
            )
        return results

    def _finalize(
        self, run_id: str, checkpoint: str, results: list[dict[str, Any]]
    ) -> ValidationCheckpointResult:
        success = all(r.get("success", False) for r in results) if results else False
        payload = ValidationCheckpointResult(
            checkpoint=checkpoint,  # type: ignore[arg-type]
            success=success,
            results=results,
            suite_name=f"{checkpoint}_suite",
        )
        path = self.out_dir / f"{checkpoint}.json"
        path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        SUITE_DIR.mkdir(parents=True, exist_ok=True)
        (SUITE_DIR / f"{checkpoint}.json").write_text(
            json.dumps({"checkpoint": checkpoint, "results": results}, indent=2, default=str),
            encoding="utf-8",
        )
        self.audit.log(
            run_id,
            node="validator",
            action=f"{checkpoint}_{'passed' if success else 'failed'}",
            payload={"result_count": len(results), "success": success},
        )
        if not success:
            raise ValidationBlocked(f"Great Expectations checkpoint '{checkpoint}' failed; see {path}")
        return payload
