"""Execute dbt when configured; otherwise run equivalent SQL tests via SQLAlchemy."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from connectors.sql import quote_ident
from core.logging import get_logger

logger = get_logger("validation.dbt_runner")

DBT_DIR = Path(__file__).resolve().parent / "dbt_models"


class DbtRunner:
    def __init__(self, artifact_dir: Path, audit: AuditLogger | None = None) -> None:
        self.artifact_dir = artifact_dir
        self.audit = audit or AuditLogger()

    def run(self, run_id: str, target_engine: Engine) -> dict:
        dbt_ok = self._try_dbt()
        sql_ok = self._sql_tests(target_engine)
        payload = {"dbt": dbt_ok, "sql_tests": sql_ok}
        path = self.artifact_dir / "dbt_validation.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        self.audit.log(run_id, node="validator", action="dbt_completed", payload=payload)
        failures = [k for k, v in sql_ok.items() if v.get("failed")]
        if failures:
            raise RuntimeError("dbt-equivalent tests failed: " + ", ".join(failures))
        return payload

    def _try_dbt(self) -> dict:
        profiles = DBT_DIR / "profiles.yml"
        if not profiles.exists():
            return {"skipped": True, "reason": "profiles.yml not configured"}
        try:
            proc = subprocess.run(
                ["dbt", "test", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            return {
                "returncode": proc.returncode,
                "stdout_tail": proc.stdout[-2000:],
                "stderr_tail": proc.stderr[-1000:],
            }
        except Exception as exc:
            return {"skipped": True, "reason": str(exc)}

    def _sql_tests(self, engine: Engine) -> dict:
        q = lambda name: quote_ident(name, engine)
        tests = {
            "patients_row_count": f"SELECT COUNT(*) FROM {q('patients')}",
            "orphan_patient_pcp": (
                f"SELECT COUNT(*) FROM {q('patients')} p "
                f"LEFT JOIN {q('staff')} s ON p.{q('primary_care_staff_id')} = s.{q('staff_id')} "
                f"WHERE p.{q('primary_care_staff_id')} IS NOT NULL AND s.{q('staff_id')} IS NULL"
            ),
            "invalid_patient_status": (
                f"SELECT COUNT(*) FROM {q('patients')} "
                f"WHERE {q('patient_status')} IS NOT NULL AND {q('patient_status')} NOT IN "
                "('Active','Discharged','Inactive','Suspended')"
            ),
            "invalid_billing_status": (
                f"SELECT COUNT(*) FROM {q('invoices')} "
                f"WHERE {q('billing_status')} IS NOT NULL AND {q('billing_status')} NOT IN "
                "('Draft','Submitted','Paid','Void')"
            ),
            "orphan_attending": (
                f"SELECT COUNT(*) FROM {q('admissions')} a "
                f"LEFT JOIN {q('staff')} s ON a.{q('attending_staff_id')} = s.{q('staff_id')} "
                f"WHERE a.{q('attending_staff_id')} IS NOT NULL AND s.{q('staff_id')} IS NULL"
            ),
        }
        results = {}
        with engine.connect() as conn:
            for name, sql in tests.items():
                try:
                    value = conn.execute(text(sql)).scalar_one()
                    failed = False if name == "patients_row_count" else int(value) > 0
                    if name == "patients_row_count":
                        failed = int(value) < 1
                    results[name] = {"value": int(value), "failed": failed}
                except Exception as exc:
                    results[name] = {"error": str(exc), "failed": True}
        return results
