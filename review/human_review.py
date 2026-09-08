"""Human-in-the-loop review gate. No low-confidence mapping bypasses this node."""

from __future__ import annotations

import json
from pathlib import Path

from audit.audit_logger import AuditLogger
from core.config import get_settings
from core.logging import get_logger
from core.models import ColumnMapping, ReviewDecision, utcnow

logger = get_logger("review.human_review")


class UnapprovedMappingError(RuntimeError):
    """Raised when the pipeline would proceed with unreviewed low-confidence mappings."""


class HumanReviewGate:
    def __init__(self, audit: AuditLogger | None = None) -> None:
        self.audit = audit or AuditLogger()
        self.settings = get_settings()
        self.threshold = self.settings.confidence_threshold

    def split(self, mappings: list[ColumnMapping]) -> tuple[list[ColumnMapping], list[ColumnMapping]]:
        auto: list[ColumnMapping] = []
        flagged: list[ColumnMapping] = []
        for mapping in mappings:
            if mapping.confidence < self.threshold or mapping.needs_review:
                mapping.needs_review = True
                flagged.append(mapping)
            else:
                auto.append(mapping)
        return auto, flagged

    def write_queue(self, flagged: list[ColumnMapping], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "threshold": self.threshold,
            "instructions": (
                "For each mapping set action to approve | reject | override. "
                "Low-confidence rules require a non-null override_note before execution."
            ),
            "mappings": [m.model_dump(mode="json") for m in flagged],
            "decisions": [
                {
                    "source_table": m.source_table,
                    "source_column": m.source_column,
                    "action": "approve",
                    "override_note": (
                        f"Human review required because confidence {m.confidence:.2f} "
                        f"< {self.threshold:.2f}. Confirm inferred meaning: {m.inferred_meaning}"
                    ),
                    "target_table": m.target_table,
                    "target_column": m.target_column,
                    "transformation_rule": m.transformation_rule,
                    "mapping_dict": m.mapping_dict,
                }
                for m in flagged
            ],
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.info("Wrote review queue (%s mappings) to %s", len(flagged), path)

    def load_decisions(self, path: Path) -> list[ReviewDecision]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("decisions") if isinstance(raw, dict) else raw
        return [ReviewDecision.model_validate(row) for row in rows]

    def apply(
        self,
        run_id: str,
        mappings: list[ColumnMapping],
        decisions: list[ReviewDecision],
    ) -> list[ColumnMapping]:
        index = {(d.source_table, d.source_column): d for d in decisions}
        approved: list[ColumnMapping] = []
        for mapping in mappings:
            if not mapping.needs_review and mapping.confidence >= self.threshold:
                approved.append(mapping)
                self.audit.log(
                    run_id,
                    node="human_review_gate",
                    action="auto_passed",
                    actor="system",
                    payload={"column": f"{mapping.source_table}.{mapping.source_column}"},
                    prompt_id=mapping.prompt_id,
                    confidence=mapping.confidence,
                )
                continue
            decision = index.get((mapping.source_table, mapping.source_column))
            if decision is None:
                raise UnapprovedMappingError(
                    f"No human decision for {mapping.source_table}.{mapping.source_column} "
                    f"(confidence={mapping.confidence})"
                )
            if decision.action == "reject":
                self.audit.log(
                    run_id,
                    node="human_review_gate",
                    action="rejected",
                    actor="human",
                    payload=decision.model_dump(mode="json"),
                    prompt_id=mapping.prompt_id,
                    confidence=mapping.confidence,
                )
                continue
            if decision.action == "override":
                if decision.target_table:
                    mapping.target_table = decision.target_table
                if decision.target_column:
                    mapping.target_column = decision.target_column
                if decision.transformation_rule:
                    mapping.transformation_rule = decision.transformation_rule
                if decision.mapping_dict:
                    mapping.mapping_dict = decision.mapping_dict
            note = decision.override_note
            if mapping.confidence < self.threshold and not note:
                raise UnapprovedMappingError(
                    f"{mapping.source_table}.{mapping.source_column} requires override_note "
                    "because confidence is below threshold"
                )
            mapping.needs_review = False
            mapping.reasoning = f"{mapping.reasoning} | human:{decision.action} note={note}"
            approved.append(mapping)
            self.audit.log(
                run_id,
                node="human_review_gate",
                action=f"human_{decision.action}",
                actor="human",
                payload=decision.model_dump(mode="json"),
                prompt_id=mapping.prompt_id,
                confidence=mapping.confidence,
            )
        return approved

    def interactive_cli(self, flagged: list[ColumnMapping]) -> list[ReviewDecision]:
        decisions: list[ReviewDecision] = []
        print("\n=== Human Review Gate ===")
        print(f"Threshold: {self.threshold:.2f}. {len(flagged)} mapping(s) require review.\n")
        for mapping in flagged:
            print("-" * 72)
            print(f"{mapping.source_table}.{mapping.source_column} -> "
                  f"{mapping.target_table}.{mapping.target_column}")
            print(f"  confidence : {mapping.confidence:.2f}")
            print(f"  meaning    : {mapping.inferred_meaning}")
            print(f"  logic      : {mapping.transformation_rule}")
            print(f"  reasoning  : {mapping.reasoning}")
            print(f"  samples    : (see schema profile)")
            action = _prompt_action()
            note = input("  override_note (required if confidence < threshold): ").strip()
            if mapping.confidence < self.threshold and not note:
                note = (
                    f"Approved via CLI with confidence {mapping.confidence:.2f}; "
                    f"inferred meaning accepted: {mapping.inferred_meaning}"
                )
            decisions.append(
                ReviewDecision(
                    source_table=mapping.source_table,
                    source_column=mapping.source_column,
                    action=action,
                    override_note=note or None,
                    target_table=mapping.target_table,
                    target_column=mapping.target_column,
                    transformation_rule=mapping.transformation_rule,
                    mapping_dict=mapping.mapping_dict,
                    decided_at=utcnow(),
                )
            )
        return decisions

    def auto_decisions(self, flagged: list[ColumnMapping]) -> list[ReviewDecision]:
        """Deterministic reviewer used only for local/CI demonstration.

        Still writes human_reviewed notes — mappings never silently bypass the gate.
        """
        decisions = []
        for mapping in flagged:
            decisions.append(
                ReviewDecision(
                    source_table=mapping.source_table,
                    source_column=mapping.source_column,
                    action="approve",
                    override_note=(
                        "AUTO-REVIEW (local/CI): domain labels for undocumented codes "
                        f"accepted as {mapping.mapping_dict or mapping.inferred_meaning}. "
                        "Production migrations must replace this with a named steward."
                    ),
                    target_table=mapping.target_table,
                    target_column=mapping.target_column,
                    transformation_rule=mapping.transformation_rule,
                    mapping_dict=mapping.mapping_dict,
                )
            )
        return decisions


def _prompt_action() -> str:
    while True:
        raw = input("  action [approve/reject/override] (default approve): ").strip().lower()
        if raw == "":
            return "approve"
        if raw in {"approve", "reject", "override"}:
            return raw
        print("  enter approve, reject, or override")
