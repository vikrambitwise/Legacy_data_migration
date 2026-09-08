"""Command-line entrypoint for the AI-Assisted Legacy Data Migration Platform."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from audit.audit_logger import AuditLogger, DEFAULT_LOG
from core.config import ROOT, get_settings
from core.logging import get_logger
from etl.migration_executor import MigrationExecutor
from review.human_review import HumanReviewGate
from source.seed import main as seed_main
from workflow.langgraph_orchestrator import MigrationOrchestrator, node_names

logger = get_logger("cli")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AI-Assisted Legacy Data Migration Platform (FDE-CAPSTONE-DE-01)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="Create synthetic legacy source data")
    p_seed.add_argument("--patients", type=int, default=12000)

    p_mig = sub.add_parser("migrate", help="Start the LangGraph migration workflow")
    p_mig.add_argument("--tables", default="", help="Comma-separated source tables (default: all)")
    p_mig.add_argument("--run-id", default="")

    p_rev = sub.add_parser("review", help="Apply human review decisions and resume")
    p_rev.add_argument("--file", default="", help="Path to review_queue.json with decisions")
    p_rev.add_argument("--interactive", action="store_true")
    p_rev.add_argument("--auto", action="store_true", help="CI/demo auto-approve with override notes")

    sub.add_parser("resume", help="Resume a paused run using review_queue.json")

    p_rb = sub.add_parser("rollback", help="Drop target tables created by a run")
    p_rb.add_argument("--run-id", required=True)

    p_audit = sub.add_parser("inspect-audit", help="Print the immutable audit log")
    p_audit.add_argument("--run-id", default="")

    sub.add_parser("nodes", help="List LangGraph node names")
    sub.add_parser("verify-stack", help="Check Postgres, Snowflake, and Great Expectations connectivity")

    args = parser.parse_args(argv)
    if args.command == "seed":
        sys.argv = ["seed", "--patients", str(args.patients)]
        seed_main()
        return 0
    if args.command == "nodes":
        print("\n".join(node_names()))
        return 0
    if args.command == "verify-stack":
        from core.stack_check import verify

        results = verify()
        for name, status in results.items():
            print(f"{name:22} {status}")
        return 0 if all(v.startswith("ok") for v in results.values()) else 1
    if args.command == "inspect-audit":
        return _inspect_audit(args.run_id)
    if args.command == "rollback":
        return _rollback(args.run_id)
    if args.command == "migrate":
        return _migrate(args.tables, args.run_id)
    if args.command == "review":
        return _review(args.file, args.interactive, args.auto)
    if args.command == "resume":
        return _review("", False, False)
    return 1


def _migrate(tables: str, run_id: str) -> int:
    settings = get_settings()
    table_filter = [t.strip() for t in tables.split(",") if t.strip()] or settings.table_selection
    orch = MigrationOrchestrator()
    state = orch.start(table_filter=table_filter, run_id=run_id or None)
    _print_status(state)
    if state.get("awaiting_review"):
        print("\nPipeline paused at human_review_gate.")
        print(f"Edit {state['artifact_dir']}/review_queue.json then run:")
        print("  python cli.py review --file <path>")
        print("  python cli.py review --interactive")
        print("  python cli.py review --auto   # local/CI demo only")
        return 0
    print("\nMigration completed.")
    return 0


def _review(file_path: str, interactive: bool, auto: bool) -> int:
    from core.models import ColumnMapping

    latest = _latest_artifact()
    if latest is None:
        print("No paused run found. Start with: python cli.py migrate")
        return 1
    state_path = latest / "pipeline_state.json"
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    flagged = [ColumnMapping.model_validate(m) for m in saved.get("flagged_mappings") or []]
    gate = HumanReviewGate()
    queue = Path(file_path) if file_path else latest / "review_queue.json"
    if interactive:
        decisions = gate.interactive_cli(flagged)
    elif auto:
        decisions = gate.auto_decisions(flagged)
    else:
        decisions = gate.load_decisions(queue)
    payload = json.loads(queue.read_text(encoding="utf-8")) if queue.exists() else {"decisions": []}
    payload["decisions"] = [d.model_dump(mode="json") for d in decisions]
    queue.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    orch = MigrationOrchestrator()
    state = orch.continue_after_review(saved, decisions)
    _print_status(state)
    return 0


def _rollback(run_id: str) -> int:
    artifact = ROOT / "runs" / run_id
    executor = MigrationExecutor(run_id, artifact)
    executor.rollback()
    print(f"Rollback complete for run {run_id}")
    return 0


def _inspect_audit(run_id: str) -> int:
    logger.info("Reading audit log %s", DEFAULT_LOG)
    rows = AuditLogger().read_all()
    if run_id:
        rows = [r for r in rows if r.get("run_id") == run_id]
    print(json.dumps(rows, indent=2, default=str))
    print(f"\n{len(rows)} event(s). LangFuse local traces live under runs/<run_id>/langfuse_local_traces.jsonl")
    return 0


def _print_status(state: dict) -> None:
    print(f"run_id     : {state.get('run_id')}")
    print(f"status     : {state.get('status')}")
    print(f"checkpoint : {state.get('checkpoint')}")
    print(f"artifacts  : {state.get('artifact_dir')}")
    if state.get("awaiting_review"):
        print(f"flagged    : {len(state.get('flagged_mappings') or [])}")


def _latest_artifact() -> Path | None:
    marker = ROOT / "runs" / "LATEST_RUN.txt"
    if marker.exists():
        path = Path(marker.read_text(encoding="utf-8").strip())
        if path.exists():
            return path
    runs = ROOT / "runs"
    if not runs.exists():
        return None
    dirs = [p for p in runs.iterdir() if p.is_dir() and p.name != "latest"]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


if __name__ == "__main__":
    raise SystemExit(main())
