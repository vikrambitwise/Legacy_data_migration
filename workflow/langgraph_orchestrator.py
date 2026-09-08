"""LangGraph orchestrator — 7-node migration workflow with HITL confidence gating."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypedDict

import pandas as pd
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.ai_mapper import AIMapper
from agents.doc_generator import DocGenerator
from agents.rule_generator import RuleGenerator
from agents.schema_profiler import SchemaProfiler
from audit.audit_logger import AuditLogger
from connectors.db import get_source_engine, get_target_engine
from core.config import ROOT, get_settings
from core.logging import get_logger
from core.models import (
    ColumnMapping,
    ReviewDecision,
    SchemaProfile,
    TransformationRule,
    new_id,
)
from core.observability import LLMTracer
from etl.migration_executor import MigrationExecutor
from review.human_review import HumanReviewGate, UnapprovedMappingError
from validation.dbt_runner import DbtRunner
from validation.ge_runner import GERunner
from validation.reconciler import Reconciler

logger = get_logger("workflow.orchestrator")


class MigrationState(TypedDict, total=False):
    run_id: str
    table_filter: list[str] | None
    artifact_dir: str
    schema_profile: dict[str, Any]
    mappings: list[dict[str, Any]]
    flagged_mappings: list[dict[str, Any]]
    review_decisions: list[dict[str, Any]]
    awaiting_review: bool
    rules: list[dict[str, Any]]
    load_stats: dict[str, Any]
    validation: dict[str, Any]
    reconciliation: dict[str, Any]
    data_dictionary_path: str
    errors: list[str]
    status: str
    checkpoint: str


def build_graph(checkpointer: MemorySaver | None = None):
    graph = StateGraph(MigrationState)
    graph.add_node("schema_profiler", schema_profiler_node)
    graph.add_node("ai_mapper", ai_mapper_node)
    graph.add_node("human_review_gate", human_review_gate_node)
    graph.add_node("rule_generator", rule_generator_node)
    graph.add_node("migration_executor", migration_executor_node)
    graph.add_node("validator", validator_node)
    graph.add_node("doc_generator", doc_generator_node)

    graph.add_edge(START, "schema_profiler")
    graph.add_edge("schema_profiler", "ai_mapper")
    graph.add_edge("ai_mapper", "human_review_gate")
    graph.add_conditional_edges(
        "human_review_gate",
        route_after_review,
        {"pause": END, "continue": "rule_generator"},
    )
    graph.add_edge("rule_generator", "migration_executor")
    graph.add_edge("migration_executor", "validator")
    graph.add_edge("validator", "doc_generator")
    graph.add_edge("doc_generator", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())


def route_after_review(state: MigrationState) -> Literal["pause", "continue"]:
    if state.get("awaiting_review"):
        return "pause"
    return "continue"


def schema_profiler_node(state: MigrationState) -> dict[str, Any]:
    run_id = state["run_id"]
    artifact = Path(state["artifact_dir"])
    audit = AuditLogger()
    profiler = SchemaProfiler(audit=audit)
    profile = profiler.run(
        run_id,
        table_filter=state.get("table_filter"),
        output_path=artifact / "schema_profile.json",
    )
    ge = GERunner(artifact, audit=audit)
    ge.source_baseline(run_id, profile, get_source_engine())
    audit.log(run_id, node="schema_profiler", action="source_baseline_passed")
    return {
        "schema_profile": json.loads(profile.model_dump_json()),
        "checkpoint": "schema_profiler",
        "status": "profiled",
    }


def ai_mapper_node(state: MigrationState) -> dict[str, Any]:
    run_id = state["run_id"]
    artifact = Path(state["artifact_dir"])
    tracer = LLMTracer(run_id)
    profile = SchemaProfile.model_validate(state["schema_profile"])
    mapper = AIMapper(tracer=tracer)
    mappings = mapper.run(profile, output_path=artifact / "mappings.json")
    tracer.flush()
    return {
        "mappings": [m.model_dump(mode="json") for m in mappings],
        "checkpoint": "ai_mapper",
        "status": "mapped",
    }


def human_review_gate_node(state: MigrationState) -> dict[str, Any]:
    """Every mapping passes through this node. Low-confidence rows pause the graph."""
    run_id = state["run_id"]
    artifact = Path(state["artifact_dir"])
    settings = get_settings()
    gate = HumanReviewGate()
    mappings = [ColumnMapping.model_validate(m) for m in state.get("mappings") or []]
    _auto, flagged = gate.split(mappings)
    queue_path = artifact / "review_queue.json"

    existing = state.get("review_decisions") or []
    if flagged and not existing:
        gate.write_queue(flagged, queue_path)
        _write_html_queue(flagged, artifact / "review_queue.html")
        AuditLogger().log(
            run_id,
            node="human_review_gate",
            action="paused_for_review",
            payload={"flagged": len(flagged), "queue": str(queue_path)},
        )
        return {
            "flagged_mappings": [m.model_dump(mode="json") for m in flagged],
            "awaiting_review": True,
            "checkpoint": "human_review_gate",
            "status": "awaiting_human_review",
        }

    decisions = [ReviewDecision.model_validate(d) for d in existing]
    if flagged and settings.review_mode == "file" and not existing:
        raise UnapprovedMappingError("Review file produced no decisions")

    approved = gate.apply(run_id, mappings, decisions)
    return {
        "mappings": [m.model_dump(mode="json") for m in approved],
        "flagged_mappings": [m.model_dump(mode="json") for m in flagged],
        "awaiting_review": False,
        "checkpoint": "human_review_gate",
        "status": "review_complete",
    }


def rule_generator_node(state: MigrationState) -> dict[str, Any]:
    run_id = state["run_id"]
    artifact = Path(state["artifact_dir"])
    tracer = LLMTracer(run_id)
    mappings = [ColumnMapping.model_validate(m) for m in state["mappings"]]
    profile = SchemaProfile.model_validate(state["schema_profile"])
    decisions = [ReviewDecision.model_validate(d) for d in state.get("review_decisions") or []]
    reviewed_keys = {(d.source_table, d.source_column) for d in decisions}
    notes = {(d.source_table, d.source_column): d.override_note for d in decisions}
    generator = RuleGenerator(tracer=tracer)
    rules = generator.run(
        mappings,
        profile,
        reviewed_keys=reviewed_keys,
        override_notes=notes,
        output_path=artifact / "transformation_rules.json",
    )
    tracer.flush()
    return {
        "rules": [r.model_dump(mode="json") for r in rules],
        "checkpoint": "rule_generator",
        "status": "rules_ready",
    }


def migration_executor_node(state: MigrationState) -> dict[str, Any]:
    run_id = state["run_id"]
    artifact = Path(state["artifact_dir"])
    profile = SchemaProfile.model_validate(state["schema_profile"])
    rules = [TransformationRule.model_validate(r) for r in state["rules"]]
    executor = MigrationExecutor(run_id, artifact)
    stats = executor.run(profile, rules, table_filter=state.get("table_filter"))
    return {
        "load_stats": stats,
        "checkpoint": "migration_executor",
        "status": "loaded",
    }


def validator_node(state: MigrationState) -> dict[str, Any]:
    run_id = state["run_id"]
    artifact = Path(state["artifact_dir"])
    audit = AuditLogger()
    profile = SchemaProfile.model_validate(state["schema_profile"])
    rules = [TransformationRule.model_validate(r) for r in state["rules"]]
    ge = GERunner(artifact, audit=audit)
    extracted: dict[str, pd.DataFrame] = {}
    extract_dir = artifact / "extracted"
    if extract_dir.exists():
        for csv in extract_dir.glob("*.csv"):
            extracted[csv.stem] = pd.read_csv(csv)
    ge.post_extraction(run_id, profile, extracted)
    source_to_target = {}
    for rule in rules:
        source_to_target[rule.source_table] = rule.target_table
    ge.post_load(run_id, profile, get_target_engine(), source_to_target)
    report = Reconciler(artifact, audit=audit).run(
        run_id, rules, get_source_engine(), get_target_engine(), state.get("load_stats") or {}
    )
    dbt = DbtRunner(artifact, audit=audit).run(run_id, get_target_engine())
    return {
        "validation": {"post_extraction": True, "post_load": True, "dbt": dbt},
        "reconciliation": json.loads(report.model_dump_json()),
        "checkpoint": "validator",
        "status": "validated",
    }


def doc_generator_node(state: MigrationState) -> dict[str, Any]:
    run_id = state["run_id"]
    artifact = Path(state["artifact_dir"])
    tracer = LLMTracer(run_id)
    rules = [TransformationRule.model_validate(r) for r in state["rules"]]
    mappings = [ColumnMapping.model_validate(m) for m in state["mappings"]]
    meanings = {(m.source_table, m.source_column): m.inferred_meaning for m in mappings}
    md_path = artifact / "data_dictionary.md"
    json_path = artifact / "data_dictionary.json"
    DocGenerator(tracer=tracer).run(rules, meanings, md_path, json_path)
    # also copy latest dictionary into docs/
    docs_copy = ROOT / "docs" / "data_dictionary.md"
    docs_copy.parent.mkdir(exist_ok=True)
    docs_copy.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    tracer.flush()
    AuditLogger().log(run_id, node="doc_generator", action="run_completed", payload={"status": "completed"})
    return {
        "data_dictionary_path": str(md_path),
        "checkpoint": "doc_generator",
        "status": "completed",
    }


def _write_html_queue(flagged: list[ColumnMapping], path: Path) -> None:
    rows = []
    for m in flagged:
        rows.append(
            f"<tr><td>{m.source_table}.{m.source_column}</td>"
            f"<td>{m.target_table}.{m.target_column}</td>"
            f"<td>{m.confidence:.2f}</td>"
            f"<td>{m.inferred_meaning}</td>"
            f"<td><code>{m.transformation_rule}</code></td></tr>"
        )
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Human Review Queue</title>
<style>
body {{ font-family: sans-serif; background:#0f1623; color:#e2e8f0; padding:24px; }}
table {{ border-collapse: collapse; width:100%; }}
th,td {{ border:1px solid #1e2d45; padding:8px; font-size:13px; }}
th {{ background:#161d2e; }}
.low {{ color:#f59e0b; }}
</style></head><body>
<h1>Human Review Queue</h1>
<p>Mappings below the confidence threshold. Record decisions in review_queue.json.</p>
<table>
<tr><th>Source</th><th>Target</th><th>Confidence</th><th>Meaning</th><th>Logic</th></tr>
{''.join(rows)}
</table>
</body></html>"""
    path.write_text(html, encoding="utf-8")


class MigrationOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.checkpointer = MemorySaver()
        self.app = build_graph(self.checkpointer)
        self.thread = {"configurable": {"thread_id": "migration-main"}}

    def start(self, table_filter: list[str] | None = None, run_id: str | None = None) -> MigrationState:
        rid = run_id or new_id("run")
        self.thread = {"configurable": {"thread_id": rid}}
        artifact = ROOT / "runs" / rid
        artifact.mkdir(parents=True, exist_ok=True)
        (ROOT / "runs" / "LATEST_RUN.txt").write_text(str(artifact), encoding="utf-8")
        initial: MigrationState = {
            "run_id": rid,
            "table_filter": table_filter or self.settings.table_selection,
            "artifact_dir": str(artifact),
            "errors": [],
            "status": "started",
        }
        AuditLogger().log(rid, node="orchestrator", action="run_started", payload={"artifact_dir": str(artifact)})
        result = self.app.invoke(initial, config=self.thread)
        self._persist(result)
        return result

    def resume(self, decisions: list[ReviewDecision] | None = None) -> MigrationState:
        snapshot = self.app.get_state(self.thread)
        if not snapshot.values:
            raise RuntimeError("No in-memory graph state; use continue_after_review()")
        values = dict(snapshot.values)
        if decisions is None:
            artifact = Path(values["artifact_dir"])
            queue = artifact / "review_queue.json"
            decisions = HumanReviewGate().load_decisions(queue)
        values["review_decisions"] = [d.model_dump(mode="json") for d in decisions]
        values["awaiting_review"] = False
        self.app.update_state(self.thread, values, as_node="ai_mapper")
        result = self.app.invoke(None, config=self.thread)
        self._persist(result)
        return result

    def continue_after_review(
        self, saved: dict[str, Any], decisions: list[ReviewDecision]
    ) -> MigrationState:
        """Process-restart safe resume: remaining nodes run from the review gate onward."""
        state: MigrationState = dict(saved)  # type: ignore[arg-type]
        state["review_decisions"] = [d.model_dump(mode="json") for d in decisions]
        state["awaiting_review"] = False
        for fn in (
            human_review_gate_node,
            rule_generator_node,
            migration_executor_node,
            validator_node,
            doc_generator_node,
        ):
            updates = fn(state)
            state.update(updates)
            self._persist(state)
            if state.get("awaiting_review"):
                return state
        return state

    def _persist(self, state: dict[str, Any]) -> None:
        artifact = Path(state["artifact_dir"])
        (artifact / "pipeline_state.json").write_text(
            json.dumps(state, indent=2, default=str), encoding="utf-8"
        )


def node_names() -> list[str]:
    return [
        "schema_profiler",
        "ai_mapper",
        "human_review_gate",
        "rule_generator",
        "migration_executor",
        "validator",
        "doc_generator",
    ]
