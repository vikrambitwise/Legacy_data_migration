"""Schema profiling via SQLAlchemy reflection — ground truth for all AI nodes."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, func, inspect, select
from sqlalchemy.engine import Engine

from audit.audit_logger import AuditLogger
from connectors.db import get_source_engine, redact_url
from core.config import get_settings
from core.graph import topological_load_order
from core.logging import get_logger
from core.models import ColumnProfile, ForeignKeyRef, SchemaProfile, TableProfile, new_id
from core.pii import detect_pii

logger = get_logger("agents.schema_profiler")

SAMPLE_LIMIT = 8
DIST_LIMIT = 25
MAX_SCAN_ROWS = 50_000


class SchemaProfiler:
    def __init__(self, engine: Engine | None = None, audit: AuditLogger | None = None) -> None:
        self.engine = engine or get_source_engine()
        self.audit = audit or AuditLogger()

    def run(
        self,
        run_id: str,
        table_filter: list[str] | None = None,
        output_path: Path | None = None,
    ) -> SchemaProfile:
        inspector = inspect(self.engine)
        table_names = inspector.get_table_names()
        if table_filter:
            wanted = set(table_filter)
            table_names = [t for t in table_names if t in wanted]
        metadata = MetaData()
        metadata.reflect(bind=self.engine, only=table_names or None)

        tables: list[TableProfile] = []
        fk_graph: dict[str, list[str]] = {t: [] for t in table_names}

        for name in table_names:
            sa_table = metadata.tables[name]
            tables.append(self._profile_table(inspector, sa_table, fk_graph))

        load_order = topological_load_order(fk_graph, table_names)
        profile = SchemaProfile(
            source_dialect=self.engine.dialect.name,
            source_url_redacted=redact_url(str(self.engine.url)),
            profiled_at=datetime.now(timezone.utc),
            tables=tables,
            fk_graph=fk_graph,
            load_order=load_order,
        )
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

        self.audit.log(
            run_id,
            node="schema_profiler",
            action="profile_completed",
            payload={
                "tables": table_names,
                "load_order": load_order,
                "prompt_id": None,
            },
        )
        logger.info("Profiled %s tables; load_order=%s", len(tables), load_order)
        return profile

    def _profile_table(
        self,
        inspector: Any,
        sa_table: Table,
        fk_graph: dict[str, list[str]],
    ) -> TableProfile:
        name = sa_table.name
        pk = inspector.get_pk_constraint(name).get("constrained_columns") or []
        fks_raw = inspector.get_foreign_keys(name)
        indexes = [ix.get("name") or "" for ix in inspector.get_indexes(name)]
        fk_models: list[ForeignKeyRef] = []
        fk_by_col: dict[str, str] = {}
        for fk in fks_raw:
            referred = fk.get("referred_table")
            if referred:
                fk_graph[name].append(referred)
            for col, refcol in zip(fk.get("constrained_columns") or [], fk.get("referred_columns") or []):
                fk_models.append(
                    ForeignKeyRef(
                        column=col,
                        referred_table=referred or "",
                        referred_column=refcol,
                        nullable=bool(sa_table.c[col].nullable) if col in sa_table.c else True,
                    )
                )
                fk_by_col[col] = f"{referred}.{refcol}"

        with self.engine.connect() as conn:
            row_count = conn.execute(select(func.count()).select_from(sa_table)).scalar_one()
            scan_n = min(int(row_count), MAX_SCAN_ROWS)
            sample_stmt = select(sa_table).limit(scan_n)
            rows = conn.execute(sample_stmt).mappings().all()

        columns: list[ColumnProfile] = []
        for col in sa_table.columns:
            values = [r.get(col.name) for r in rows]
            non_null = [v for v in values if v is not None and v != ""]
            nulls = len(values) - len(non_null)
            null_rate = (nulls / len(values)) if values else (1.0 if col.nullable else 0.0)
            counter = Counter(str(v) for v in non_null)
            dist = dict(counter.most_common(DIST_LIMIT))
            samples = [v for v, _ in counter.most_common(SAMPLE_LIMIT)]
            min_v = max_v = None
            avg_len = None
            if non_null:
                try:
                    min_v = str(min(non_null))
                    max_v = str(max(non_null))
                except TypeError:
                    pass
                avg_len = round(sum(len(str(v)) for v in non_null) / len(non_null), 2)
            columns.append(
                ColumnProfile(
                    name=col.name,
                    data_type=str(col.type),
                    nullable=bool(col.nullable),
                    is_pk=col.name in pk,
                    is_fk=col.name in fk_by_col,
                    fk_target=fk_by_col.get(col.name),
                    null_rate=round(null_rate, 4),
                    cardinality=len(counter),
                    row_count=int(row_count),
                    sample_values=samples,
                    value_distribution=dist,
                    min_value=min_v,
                    max_value=max_v,
                    avg_length=avg_len,
                    pii_flags=detect_pii(col.name, samples),
                    comment=col.comment,
                )
            )
        return TableProfile(
            name=name,
            row_count=int(row_count),
            columns=columns,
            primary_key=list(pk),
            foreign_keys=fk_models,
            indexes=[i for i in indexes if i],
        )


def run_profiler(run_id: str | None = None, output_path: Path | None = None) -> SchemaProfile:
    settings = get_settings()
    rid = run_id or new_id("run")
    profiler = SchemaProfiler()
    return profiler.run(rid, table_filter=settings.table_selection, output_path=output_path)


if __name__ == "__main__":
    profile = run_profiler()
    print(json.dumps(json.loads(profile.model_dump_json()), indent=2)[:4000])
