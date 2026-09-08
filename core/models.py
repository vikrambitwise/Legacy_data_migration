"""Canonical data contracts for profiles, mappings, rules, and audit events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class ForeignKeyRef(BaseModel):
    column: str
    referred_table: str
    referred_column: str
    nullable: bool = True


class ColumnProfile(BaseModel):
    name: str
    data_type: str
    nullable: bool
    is_pk: bool = False
    is_fk: bool = False
    fk_target: str | None = None
    null_rate: float = 0.0
    cardinality: int = 0
    row_count: int = 0
    sample_values: list[Any] = Field(default_factory=list)
    value_distribution: dict[str, int] = Field(default_factory=dict)
    min_value: str | None = None
    max_value: str | None = None
    avg_length: float | None = None
    pii_flags: list[str] = Field(default_factory=list)
    comment: str | None = None


class TableProfile(BaseModel):
    name: str
    row_count: int
    columns: list[ColumnProfile]
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyRef] = Field(default_factory=list)
    indexes: list[str] = Field(default_factory=list)


class SchemaProfile(BaseModel):
    source_dialect: str
    source_url_redacted: str
    profiled_at: datetime
    tables: list[TableProfile]
    fk_graph: dict[str, list[str]] = Field(default_factory=dict)
    load_order: list[str] = Field(default_factory=list)
    profiler_version: str = "1.0.0"


class ColumnMapping(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    source_type: str
    target_type: str
    inferred_meaning: str
    transformation_rule: str
    null_handling: str
    edge_cases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    prompt_id: str
    needs_review: bool = False
    mapping_dict: dict[str, str] | None = None


class ReviewDecision(BaseModel):
    source_table: str
    source_column: str
    action: Literal["approve", "reject", "override"]
    override_note: str | None = None
    target_table: str | None = None
    target_column: str | None = None
    transformation_rule: str | None = None
    mapping_dict: dict[str, str] | None = None
    reviewer: str = "human"
    decided_at: datetime = Field(default_factory=utcnow)


class TransformationRule(BaseModel):
    """Mandatory JSON rule schema from the capstone specification, plus table context."""

    source_column: str
    target_column: str
    logic: str
    null_handling: str
    edge_cases: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    prompt_id: str
    human_reviewed: bool = False
    override_note: str | None = None
    # Extensions required for multi-table execution (still serialized in audit artifacts)
    source_table: str
    target_table: str
    mapping_dict: dict[str, str] | None = None
    transform_type: Literal["copy", "map", "cast", "trim", "date", "custom"] = "copy"

    def to_spec_dict(self) -> dict[str, Any]:
        return {
            "source_column": self.source_column,
            "target_column": self.target_column,
            "logic": self.logic,
            "null_handling": self.null_handling,
            "edge_cases": self.edge_cases,
            "confidence": self.confidence,
            "prompt_id": self.prompt_id,
            "human_reviewed": self.human_reviewed,
            "override_note": self.override_note,
        }

    def is_approved_for_execution(self, threshold: float = 0.80) -> bool:
        if self.confidence >= threshold:
            return True
        return bool(self.human_reviewed and self.override_note)


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    run_id: str
    ts: datetime = Field(default_factory=utcnow)
    actor: Literal["system", "ai", "human"]
    node: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    prompt_id: str | None = None
    confidence: float | None = None


class ReconciliationTable(BaseModel):
    source_table: str
    target_table: str
    source_rows: int
    target_rows: int
    row_count_match: bool
    source_null_rates: dict[str, float] = Field(default_factory=dict)
    target_null_rates: dict[str, float] = Field(default_factory=dict)
    distribution_deltas: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ReconciliationReport(BaseModel):
    run_id: str
    generated_at: datetime = Field(default_factory=utcnow)
    tables: list[ReconciliationTable]
    passed: bool
    failures: list[str] = Field(default_factory=list)


class ValidationCheckpointResult(BaseModel):
    checkpoint: Literal["source_baseline", "post_extraction", "post_load"]
    success: bool
    results: list[dict[str, Any]] = Field(default_factory=list)
    suite_name: str


class DataDictionaryEntry(BaseModel):
    target_table: str
    target_column: str
    definition: str
    source_table: str
    source_column: str
    lineage: str
    transformation_logic: str
    human_override: str | None = None
    prompt_id: str
