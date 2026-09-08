from pathlib import Path

from audit.audit_logger import AuditLogger
from core.models import AuditEvent


def test_audit_log_is_append_only(tmp_path: Path):
    path = tmp_path / "audit.json"
    log = AuditLogger(path)
    log.append(
        AuditEvent(run_id="r1", actor="ai", node="ai_mapper", action="mapping_generated", prompt_id="p1")
    )
    log.append(
        AuditEvent(run_id="r1", actor="human", node="human_review_gate", action="human_approve")
    )
    rows = log.read_all()
    assert len(rows) == 2
    assert rows[0]["prompt_id"] == "p1"
    assert rows[1]["actor"] == "human"
    first_event_id = rows[0]["event_id"]
    log.log("r1", "validator", "reconciliation_completed")
    rows2 = log.read_all()
    assert rows2[0]["event_id"] == first_event_id
    assert len(rows2) == 3
