"""LangChain rule generator — emits the mandatory transformation rule JSON schema."""

from __future__ import annotations

import json
from pathlib import Path

from agents.llm import get_chat_model, invoke_json, make_prompt_id
from audit.audit_logger import AuditLogger
from core.config import get_settings
from core.logging import get_logger
from core.models import ColumnMapping, SchemaProfile, TransformationRule
from core.observability import LLMTracer
from prompts.templates import render
from review.human_review import UnapprovedMappingError

logger = get_logger("agents.rule_generator")


class RuleGenerator:
    def __init__(self, tracer: LLMTracer, audit: AuditLogger | None = None) -> None:
        self.tracer = tracer
        self.audit = audit or AuditLogger()
        self.settings = get_settings()
        self.threshold = self.settings.confidence_threshold

    def run(
        self,
        mappings: list[ColumnMapping],
        profile: SchemaProfile,
        reviewed_keys: set[tuple[str, str]],
        override_notes: dict[tuple[str, str], str | None],
        output_path: Path | None = None,
    ) -> list[TransformationRule]:
        col_index = {
            (t.name, c.name): c
            for t in profile.tables
            for c in t.columns
        }
        rules: list[TransformationRule] = []
        use_llm = get_chat_model() is not None
        for mapping in mappings:
            column = col_index.get((mapping.source_table, mapping.source_column))
            human_reviewed = (mapping.source_table, mapping.source_column) in reviewed_keys
            note = override_notes.get((mapping.source_table, mapping.source_column))
            if use_llm:
                rule = self._llm_rule(mapping, column, human_reviewed, note)
            else:
                rule = self._heuristic_rule(mapping, human_reviewed, note)
            if not rule.is_approved_for_execution(self.threshold):
                raise UnapprovedMappingError(
                    f"Rule {rule.source_table}.{rule.source_column} blocked: "
                    f"confidence {rule.confidence} < {self.threshold} without "
                    "human_reviewed=true and override_note"
                )
            rules.append(rule)
            self.audit.log(
                self.tracer.run_id,
                node="rule_generator",
                action="rule_generated",
                actor="ai",
                payload=rule.to_spec_dict(),
                prompt_id=rule.prompt_id,
                confidence=rule.confidence,
            )
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps([r.model_dump(mode="json") for r in rules], indent=2, default=str),
                encoding="utf-8",
            )
        logger.info("Generated %s transformation rules", len(rules))
        return rules

    def _llm_rule(
        self,
        mapping: ColumnMapping,
        column,
        human_reviewed: bool,
        note: str | None,
    ) -> TransformationRule:
        prompt = render(
            "rule_generation_v1",
            source_table=mapping.source_table,
            source_column=mapping.source_column,
            source_type=mapping.source_type,
            target_table=mapping.target_table,
            target_column=mapping.target_column,
            target_type=mapping.target_type,
            inferred_meaning=mapping.inferred_meaning,
            transformation_rule=mapping.transformation_rule,
            mapping_dict=mapping.mapping_dict,
            null_rate=column.null_rate if column else 0,
            sample_values=column.sample_values if column else [],
            human_reviewed=human_reviewed,
            override_note=note,
        )
        fallback = self._heuristic_rule(mapping, human_reviewed, note)
        try:
            prompt_id, parsed = invoke_json(
                tracer=self.tracer,
                node="rule_generator",
                template_key="rule_generation_v1",
                prompt=prompt,
            )
            return TransformationRule(
                source_column=mapping.source_column,
                target_column=mapping.target_column,
                logic=parsed.get("logic") or fallback.logic,
                null_handling=parsed.get("null_handling") or fallback.null_handling,
                edge_cases=list(parsed.get("edge_cases") or fallback.edge_cases),
                confidence=float(parsed.get("confidence", mapping.confidence)),
                prompt_id=prompt_id,
                human_reviewed=human_reviewed,
                override_note=note,
                source_table=mapping.source_table,
                target_table=mapping.target_table,
                mapping_dict=parsed.get("mapping_dict") or mapping.mapping_dict,
                transform_type=parsed.get("transform_type") or fallback.transform_type,
            )
        except Exception as exc:
            logger.warning("LLM rule generation failed for %s: %s", mapping.source_column, exc)
            fallback.prompt_id = fallback.prompt_id
            return fallback

    def _heuristic_rule(
        self,
        mapping: ColumnMapping,
        human_reviewed: bool,
        note: str | None,
    ) -> TransformationRule:
        prompt_id = make_prompt_id("rule_generation_v1")
        transform_type = "copy"
        logic = mapping.transformation_rule or "src"
        if mapping.mapping_dict:
            transform_type = "map"
        elif "TO_DATE" in logic.upper():
            transform_type = "date"
        elif "TRIM" in logic.upper():
            transform_type = "trim"
        elif "CAST" in logic.upper():
            transform_type = "cast"
        with self.tracer.span(
            "rule_generator_heuristic",
            prompt_id=prompt_id,
            input_payload=mapping.model_dump(mode="json"),
        ) as span:
            span["output"] = {"logic": logic, "transform_type": transform_type}
        return TransformationRule(
            source_column=mapping.source_column,
            target_column=mapping.target_column,
            logic=logic,
            null_handling=mapping.null_handling,
            edge_cases=mapping.edge_cases,
            confidence=mapping.confidence,
            prompt_id=prompt_id,
            human_reviewed=human_reviewed,
            override_note=note,
            source_table=mapping.source_table,
            target_table=mapping.target_table,
            mapping_dict=mapping.mapping_dict,
            transform_type=transform_type,  # type: ignore[arg-type]
        )
