"""Source vs target reconciliation: row counts, null rates, distributions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from connectors.sql import quote_ident
from core.logging import get_logger
from core.models import ReconciliationReport, ReconciliationTable, TransformationRule

logger = get_logger("validation.reconciler")


class ReconciliationBlocked(RuntimeError):
    pass


class Reconciler:
    def __init__(self, artifact_dir: Path, audit: AuditLogger | None = None) -> None:
        self.artifact_dir = artifact_dir
        self.audit = audit or AuditLogger()

    def run(
        self,
        run_id: str,
        rules: list[TransformationRule],
        source: Engine,
        target: Engine,
        load_stats: dict,
    ) -> ReconciliationReport:
        tables: list[ReconciliationTable] = []
        failures: list[str] = []
        grouped: dict[str, list[TransformationRule]] = {}
        for rule in rules:
            grouped.setdefault(rule.source_table, []).append(rule)

        for source_table, table_rules in grouped.items():
            target_table = table_rules[0].target_table
            src_df = pd.read_sql(f"SELECT * FROM {quote_ident(source_table, source)}", source)
            tgt_df = pd.read_sql(f"SELECT * FROM {quote_ident(target_table, target)}", target)
            src_n, tgt_n = len(src_df), len(tgt_df)
            rejected = int(load_stats.get("tables", {}).get(source_table, {}).get("rejected", 0))
            expected_tgt = src_n - rejected
            row_match = tgt_n == expected_tgt
            if not row_match:
                failures.append(
                    f"{source_table}->{target_table}: source={src_n} target={tgt_n} rejected={rejected}"
                )
            src_nulls = {c: round(float(src_df[c].isna().mean()), 4) for c in src_df.columns}
            tgt_nulls = {c: round(float(tgt_df[c].isna().mean()), 4) for c in tgt_df.columns}
            dist: dict = {}
            for rule in table_rules:
                if rule.mapping_dict and rule.source_column in src_df.columns:
                    src_dist = src_df[rule.source_column].astype(str).value_counts(dropna=False).head(15).to_dict()
                    if rule.target_column in tgt_df.columns:
                        tgt_dist = tgt_df[rule.target_column].astype(str).value_counts(dropna=False).head(15).to_dict()
                    else:
                        tgt_dist = {}
                    dist[rule.source_column] = {"source": _stringify(src_dist), "target": _stringify(tgt_dist)}
            notes = []
            if rejected:
                notes.append(f"{rejected} rows written to reject file and excluded from target count")
            tables.append(
                ReconciliationTable(
                    source_table=source_table,
                    target_table=target_table,
                    source_rows=src_n,
                    target_rows=tgt_n,
                    row_count_match=row_match,
                    source_null_rates=src_nulls,
                    target_null_rates=tgt_nulls,
                    distribution_deltas=dist,
                    notes=notes,
                )
            )
        report = ReconciliationReport(
            run_id=run_id,
            tables=tables,
            passed=not failures,
            failures=failures,
        )
        path = self.artifact_dir / "reconciliation_report.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        self.audit.log(
            run_id,
            node="validator",
            action="reconciliation_completed",
            payload={"passed": report.passed, "failures": failures},
        )
        if not report.passed:
            raise ReconciliationBlocked("Reconciliation failed: " + "; ".join(failures))
        logger.info("Reconciliation passed for %s tables", len(tables))
        return report


def _stringify(d: dict) -> dict:
    return {str(k): int(v) for k, v in d.items()}
