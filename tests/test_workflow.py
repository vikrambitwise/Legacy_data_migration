from pathlib import Path

from sqlalchemy import create_engine

from agents.schema_profiler import SchemaProfiler
from audit.audit_logger import AuditLogger
from review.human_review import HumanReviewGate
from source.seed import seed
from workflow.langgraph_orchestrator import node_names


def test_seven_langgraph_nodes_present():
    assert node_names() == [
        "schema_profiler",
        "ai_mapper",
        "human_review_gate",
        "rule_generator",
        "migration_executor",
        "validator",
        "doc_generator",
    ]


def test_profiler_and_confidence_gate(tmp_path: Path):
    db = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db}")
    counts = seed(engine, patient_n=80, seed=1)
    assert counts["patient_records"] == 80
    assert counts["ref_dept"] >= 5

    profiler = SchemaProfiler(engine=engine, audit=AuditLogger(tmp_path / "audit.json"))
    profile = profiler.run("run-test")
    names = {t.name for t in profile.tables}
    assert {"ref_dept", "staff_mst", "patient_records", "admit_events", "encounters"}.issubset(names)
    patients = next(t for t in profile.tables if t.name == "patient_records")
    status = next(c for c in patients.columns if c.name == "pat_st_cd")
    assert status.comment is None
    assert status.cardinality >= 3
    assert any(c.pii_flags for c in patients.columns)
    assert profile.load_order[0] == "ref_dept"

    from agents.ai_mapper import AIMapper
    from core.observability import LLMTracer

    tracer = LLMTracer("run-test")
    mappings = AIMapper(tracer=tracer).run(profile)
    gate = HumanReviewGate()
    auto, flagged = gate.split(mappings)
    assert flagged, "undocumented status codes must be gated"
    assert all(m.confidence < 0.80 or m.needs_review for m in flagged)
    decisions = gate.auto_decisions(flagged)
    approved = gate.apply("run-test", mappings, decisions)
    assert approved
    assert all(d.override_note for d in decisions)
