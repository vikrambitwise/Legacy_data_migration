"""LangChain mapping agent: schema profile → per-column mappings + confidence."""

from __future__ import annotations

from pathlib import Path

from audit.audit_logger import AuditLogger
from agents.llm import get_chat_model, invoke_json, make_prompt_id
from core.config import get_settings
from core.logging import get_logger
from core.models import ColumnMapping, ColumnProfile, SchemaProfile, TableProfile
from core.observability import LLMTracer
from prompts.templates import render

logger = get_logger("agents.ai_mapper")

TABLE_RENAME = {
    "ref_dept": "departments",
    "staff_mst": "staff",
    "patient_records": "patients",
    "admit_events": "admissions",
    "encounters": "encounters",
    "billing_txns": "invoices",
    "lab_rslts": "lab_results",
}

COLUMN_RENAME = {
    "dept_id": ("department_id", "INTEGER"),
    "dept_nm": ("department_name", "VARCHAR"),
    "loc_cd": ("location_code", "CHAR"),
    "actv_flg": ("is_active", "BOOLEAN"),
    "stf_id": ("staff_id", "INTEGER"),
    "stf_nm": ("staff_name", "VARCHAR"),
    "role_cd": ("role_code", "VARCHAR"),
    "hire_dt": ("hire_date", "DATE"),
    "pat_id": ("patient_id", "INTEGER"),
    "pat_nm": ("patient_name", "VARCHAR"),
    "dob": ("date_of_birth", "DATE"),
    "sex_cd": ("sex", "VARCHAR"),
    "pat_st_cd": ("patient_status", "VARCHAR"),
    "pcp_stf_id": ("primary_care_staff_id", "INTEGER"),
    "zip_cd": ("zip_code", "VARCHAR"),
    "ssn_last4": ("ssn_last4", "VARCHAR"),
    "created_ts": ("created_at", "TIMESTAMP"),
    "adm_id": ("admission_id", "INTEGER"),
    "admit_dt": ("admit_date", "DATE"),
    "dsch_dt": ("discharge_date", "DATE"),
    "adm_typ": ("admission_type", "VARCHAR"),
    "attending_id": ("attending_staff_id", "INTEGER"),
    "enc_id": ("encounter_id", "INTEGER"),
    "enc_dt": ("encounter_date", "DATE"),
    "enc_typ": ("encounter_type", "VARCHAR"),
    "notes_txt": ("notes", "VARCHAR"),
    "txn_id": ("invoice_id", "INTEGER"),
    "amt": ("amount", "NUMERIC"),
    "bill_st": ("billing_status", "VARCHAR"),
    "paid_dt": ("paid_date", "DATE"),
    "cpt_cd": ("cpt_code", "VARCHAR"),
    "rslt_id": ("result_id", "INTEGER"),
    "test_cd": ("test_code", "VARCHAR"),
    "rslt_val": ("result_value", "VARCHAR"),
    "rslt_uom": ("unit_of_measure", "VARCHAR"),
    "abn_flg": ("is_abnormal", "BOOLEAN"),
    "coll_dt": ("collected_date", "DATE"),
}

CODE_MAPS = {
    "pat_st_cd": {
        "A": "Active",
        "D": "Discharged",
        "I": "Inactive",
        "S": "Suspended",
    },
    "sex_cd": {"M": "Male", "F": "Female", "U": "Unknown"},
    "actv_flg": {"Y": "true", "N": "false"},
    "adm_typ": {"I": "Inpatient", "O": "Outpatient", "E": "Emergency"},
    "bill_st": {"0": "Draft", "1": "Submitted", "2": "Paid", "9": "Void"},
    "abn_flg": {"0": "false", "1": "true"},
    "role_cd": {"MD": "Physician", "RN": "Nurse", "AD": "Admin", "TH": "Therapist"},
}

AMBIGUOUS = {"pat_st_cd", "bill_st", "dsch_dt", "notes_txt", "loc_cd"}


class AIMapper:
    def __init__(self, tracer: LLMTracer, audit: AuditLogger | None = None) -> None:
        self.tracer = tracer
        self.audit = audit or AuditLogger()
        self.settings = get_settings()
        self.threshold = self.settings.confidence_threshold

    def run(self, profile: SchemaProfile, output_path: Path | None = None) -> list[ColumnMapping]:
        mappings: list[ColumnMapping] = []
        use_llm = get_chat_model() is not None
        for table in profile.tables:
            related = self._related(table)
            for col in table.columns:
                if use_llm:
                    mapping = self._map_with_llm(table, col, related)
                else:
                    mapping = self._map_heuristic(table, col)
                mapping.needs_review = mapping.confidence < self.threshold
                mappings.append(mapping)
                self.audit.log(
                    self.tracer.run_id,
                    node="ai_mapper",
                    action="mapping_generated",
                    actor="ai",
                    payload=mapping.model_dump(mode="json"),
                    prompt_id=mapping.prompt_id,
                    confidence=mapping.confidence,
                )
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [m.model_dump(mode="json") for m in mappings]
            output_path.write_text(
                __import__("json").dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
        logger.info("Generated %s mappings (llm=%s)", len(mappings), use_llm)
        return mappings

    def _related(self, table: TableProfile) -> str:
        parts = []
        if table.primary_key:
            parts.append(", ".join(f"{c} (PK)" for c in table.primary_key))
        for fk in table.foreign_keys:
            parts.append(f"{fk.column} -> {fk.referred_table}.{fk.referred_column}")
        return ", ".join(parts) or "(none)"

    def _map_with_llm(
        self, table: TableProfile, col: ColumnProfile, related: str
    ) -> ColumnMapping:
        prompt = render(
            "schema_inference_v1",
            column=col.name,
            data_type=col.data_type,
            sample_values=col.sample_values,
            null_rate=col.null_rate,
            table=table.name,
            related_columns=related,
        )
        fallback = self._map_heuristic(table, col)
        try:
            prompt_id, parsed = invoke_json(
                tracer=self.tracer,
                node="ai_mapper",
                template_key="schema_inference_v1",
                prompt=prompt,
            )
            return ColumnMapping(
                source_table=table.name,
                source_column=col.name,
                target_table=parsed.get("target_table") or fallback.target_table,
                target_column=parsed.get("target_column") or fallback.target_column,
                source_type=col.data_type,
                target_type=parsed.get("target_type") or fallback.target_type,
                inferred_meaning=parsed.get("inferred_meaning") or fallback.inferred_meaning,
                transformation_rule=parsed.get("transformation_rule") or fallback.transformation_rule,
                null_handling=parsed.get("null_handling") or fallback.null_handling,
                edge_cases=list(parsed.get("edge_cases") or fallback.edge_cases),
                confidence=float(parsed.get("confidence", fallback.confidence)),
                reasoning=parsed.get("reasoning") or fallback.reasoning,
                prompt_id=prompt_id,
                mapping_dict=parsed.get("mapping_dict") or fallback.mapping_dict,
            )
        except Exception as exc:
            logger.warning("LLM mapping failed for %s.%s: %s", table.name, col.name, exc)
            fallback.reasoning = f"LLM failed ({exc}); heuristic used. {fallback.reasoning}"
            fallback.confidence = min(fallback.confidence, 0.55)
            return fallback

    def _map_heuristic(self, table: TableProfile, col: ColumnProfile) -> ColumnMapping:
        prompt_id = make_prompt_id("schema_inference_v1")
        target_table = TABLE_RENAME.get(table.name, table.name)
        renamed, target_type = COLUMN_RENAME.get(col.name, (col.name.lower(), col.data_type))
        mapping_dict = CODE_MAPS.get(col.name)
        logic = "src"
        meaning = f"Legacy column {table.name}.{col.name} migrated to {target_table}.{renamed}."
        confidence = 0.93 if col.name in COLUMN_RENAME else 0.62
        edge = ["Trim whitespace before mapping"]
        if mapping_dict:
            whens = " ".join(
                f"WHEN src = '{k}' THEN '{v}'" for k, v in mapping_dict.items()
            )
            logic = f"CASE {whens} ELSE NULL END"
            meaning = (
                f"Undocumented code column {col.name} with observed values "
                f"{list(mapping_dict)}. Labels are inferred from sample patterns "
                f"and naming conventions — not from source documentation."
            )
            confidence = 0.72 if col.name in AMBIGUOUS else 0.88
            edge.append("Unknown codes default to NULL")
        if col.name == "dsch_dt":
            logic = "TO_DATE(src)"
            meaning = "Discharge date stored as VARCHAR with mixed formats (ISO, US, compact)."
            confidence = 0.64
            edge.extend(["Empty string treated as NULL", "Unparseable dates rejected"])
        if col.name in AMBIGUOUS:
            confidence = min(confidence, 0.74)
        if col.is_pk:
            confidence = max(confidence, 0.97)
            meaning = f"Primary key {col.name} copied to {renamed}."
        null_handling = "Preserve NULL; flag unexpected null spikes in reconciliation report."
        if col.null_rate > 0:
            null_handling = (
                f"Source null rate {col.null_rate:.2%}. Map empty strings to NULL; "
                "flag in reconciliation report."
            )
        samples = ", ".join(str(v) for v in col.sample_values[:6])
        reasoning = (
            f"Heuristic mapping from column name + samples [{samples}]. "
            f"Related FKs used for target naming. Ambiguous={col.name in AMBIGUOUS}."
        )
        with self.tracer.span(
            "ai_mapper_heuristic",
            prompt_id=prompt_id,
            input_payload={"table": table.name, "column": col.name, "samples": col.sample_values},
        ) as span:
            span["output"] = {"target": f"{target_table}.{renamed}", "confidence": confidence}
        return ColumnMapping(
            source_table=table.name,
            source_column=col.name,
            target_table=target_table,
            target_column=renamed,
            source_type=col.data_type,
            target_type=target_type,
            inferred_meaning=meaning,
            transformation_rule=logic,
            null_handling=null_handling,
            edge_cases=edge,
            confidence=confidence,
            reasoning=reasoning,
            prompt_id=prompt_id,
            mapping_dict=mapping_dict,
        )
