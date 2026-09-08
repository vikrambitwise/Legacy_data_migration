"""LangChain documentation agent — target data dictionary + lineage."""

from __future__ import annotations

from pathlib import Path

from agents.llm import get_chat_model, invoke_json, make_prompt_id
from audit.audit_logger import AuditLogger
from core.logging import get_logger
from core.models import DataDictionaryEntry, TransformationRule
from core.observability import LLMTracer
from prompts.templates import render

logger = get_logger("agents.doc_generator")


class DocGenerator:
    def __init__(self, tracer: LLMTracer, audit: AuditLogger | None = None) -> None:
        self.tracer = tracer
        self.audit = audit or AuditLogger()

    def run(
        self,
        rules: list[TransformationRule],
        meanings: dict[tuple[str, str], str],
        output_md: Path,
        output_json: Path,
    ) -> list[DataDictionaryEntry]:
        entries: list[DataDictionaryEntry] = []
        use_llm = get_chat_model() is not None
        for rule in rules:
            meaning = meanings.get((rule.source_table, rule.source_column), "")
            if use_llm:
                entry = self._llm_entry(rule, meaning)
            else:
                entry = self._heuristic_entry(rule, meaning)
            entries.append(entry)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(self._to_markdown(entries), encoding="utf-8")
        output_json.write_text(
            __import__("json").dumps([e.model_dump(mode="json") for e in entries], indent=2),
            encoding="utf-8",
        )
        self.audit.log(
            self.tracer.run_id,
            node="doc_generator",
            action="dictionary_written",
            actor="ai",
            payload={"entries": len(entries), "path": str(output_md)},
        )
        logger.info("Wrote data dictionary with %s entries", len(entries))
        return entries

    def _llm_entry(self, rule: TransformationRule, meaning: str) -> DataDictionaryEntry:
        prompt = render(
            "doc_generation_v1",
            target_table=rule.target_table,
            target_column=rule.target_column,
            source_table=rule.source_table,
            source_column=rule.source_column,
            inferred_meaning=meaning,
            logic=rule.logic,
            null_handling=rule.null_handling,
            override_note=rule.override_note,
        )
        fallback = self._heuristic_entry(rule, meaning)
        try:
            prompt_id, parsed = invoke_json(
                tracer=self.tracer,
                node="doc_generator",
                template_key="doc_generation_v1",
                prompt=prompt,
            )
            return DataDictionaryEntry(
                target_table=rule.target_table,
                target_column=rule.target_column,
                definition=parsed.get("definition") or fallback.definition,
                source_table=rule.source_table,
                source_column=rule.source_column,
                lineage=parsed.get("lineage_sentence") or fallback.lineage,
                transformation_logic=rule.logic,
                human_override=rule.override_note,
                prompt_id=prompt_id,
            )
        except Exception:
            return fallback

    def _heuristic_entry(self, rule: TransformationRule, meaning: str) -> DataDictionaryEntry:
        prompt_id = make_prompt_id("doc_generation_v1")
        definition = meaning or (
            f"{rule.target_table}.{rule.target_column} is sourced from "
            f"{rule.source_table}.{rule.source_column}."
        )
        lineage = (
            f"{rule.source_table}.{rule.source_column} -> {rule.target_table}.{rule.target_column} "
            f"via {rule.logic} (prompt {rule.prompt_id})"
        )
        with self.tracer.span(
            "doc_generator_heuristic",
            prompt_id=prompt_id,
            input_payload={"target": f"{rule.target_table}.{rule.target_column}"},
        ) as span:
            span["output"] = {"definition": definition}
        return DataDictionaryEntry(
            target_table=rule.target_table,
            target_column=rule.target_column,
            definition=definition,
            source_table=rule.source_table,
            source_column=rule.source_column,
            lineage=lineage,
            transformation_logic=rule.logic,
            human_override=rule.override_note,
            prompt_id=prompt_id,
        )

    def _to_markdown(self, entries: list[DataDictionaryEntry]) -> str:
        lines = [
            "# Target Data Dictionary",
            "",
            "Canonical documentation generated from approved mappings and transformation rules.",
            "",
        ]
        current = None
        for entry in entries:
            if entry.target_table != current:
                current = entry.target_table
                lines += [f"## {current}", ""]
            lines += [
                f"### `{entry.target_column}`",
                "",
                entry.definition,
                "",
                f"- **Lineage:** {entry.lineage}",
                f"- **Transformation:** `{entry.transformation_logic}`",
                f"- **Human override:** {entry.human_override or '_none_'}",
                f"- **Prompt ID:** `{entry.prompt_id}`",
                "",
            ]
        return "\n".join(lines)
