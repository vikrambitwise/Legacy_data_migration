"""Append-only, immutable migration audit log."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import ROOT
from core.logging import get_logger
from core.models import AuditEvent

logger = get_logger("audit")

DEFAULT_LOG = ROOT / "audit" / "migration_audit_log.json"


class AuditLogger:
    """JSON-array file that is only ever appended to (never rewritten in place)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_LOG
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def append(self, event: AuditEvent) -> None:
        payload = event.model_dump(mode="json")
        self._append_record(payload)
        logger.info(
            "audit %s node=%s action=%s prompt_id=%s",
            event.event_id,
            event.node,
            event.action,
            event.prompt_id,
        )

    def log(
        self,
        run_id: str,
        node: str,
        action: str,
        *,
        actor: str = "system",
        payload: dict[str, Any] | None = None,
        prompt_id: str | None = None,
        confidence: float | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            run_id=run_id,
            actor=actor,  # type: ignore[arg-type]
            node=node,
            action=action,
            payload=payload or {},
            prompt_id=prompt_id,
            confidence=confidence,
        )
        self.append(event)
        return event

    def read_all(self) -> list[dict[str, Any]]:
        raw = self.path.read_text(encoding="utf-8").strip() or "[]"
        return json.loads(raw)

    def for_run(self, run_id: str) -> list[dict[str, Any]]:
        return [row for row in self.read_all() if row.get("run_id") == run_id]

    def _append_record(self, record: dict[str, Any]) -> None:
        """Append one JSON object without rewriting historical events."""
        text = json.dumps(record, default=str)
        data = self.path.read_text(encoding="utf-8")
        stripped = data.rstrip()
        if stripped in ("", "[]"):
            self.path.write_text("[\n  " + text + "\n]\n", encoding="utf-8")
            return
        if stripped.endswith("]"):
            body = stripped[:-1].rstrip()
            if body.endswith("["):
                new = body + "\n  " + text + "\n]\n"
            else:
                new = body + ",\n  " + text + "\n]\n"
            self.path.write_text(new, encoding="utf-8")
            return
        raise RuntimeError(f"Audit log {self.path} is malformed; refusing to write")
