"""Prompt templates. Versioned IDs are persisted on every AI artifact."""

from __future__ import annotations

SCHEMA_INFERENCE_V1 = """You are a data migration assistant. Given the following column metadata,
infer the semantic meaning, generate a transformation rule, and return a
confidence score with reasoning.

Column: {column}
Type:   {data_type}
Sample values: {sample_values}
Null rate: {null_rate}
Table: {table}
Related columns: {related_columns}

Propose a modern snake_case target table and column name. Expand abbreviations
when the meaning is clear. For undocumented status/code columns, infer labels
only when the sample values form a consistent closed set; otherwise lower
confidence and flag for human review.

Return JSON with fields: inferred_meaning, target_table, target_column,
target_type, transformation_rule, null_handling, edge_cases, mapping_dict
(object or null), confidence (0.0–1.0), reasoning.

Do not guess on values with no clear pattern — flag those for human review.
"""

RULE_GENERATION_V1 = """Generate a transformation rule for this approved mapping — include edge cases,
null handling, and a confidence score.

Source table.column: {source_table}.{source_column}
Source type: {source_type}
Target table.column: {target_table}.{target_column}
Target type: {target_type}
Inferred meaning: {inferred_meaning}
Existing transformation sketch: {transformation_rule}
Mapping dictionary (if any): {mapping_dict}
Null rate: {null_rate}
Sample values: {sample_values}
Human reviewed: {human_reviewed}
Override note: {override_note}

Emit executable SQL-style logic using `src` as the source expression, for example:
CASE WHEN src = 'A' THEN 'Active' WHEN src = 'D' THEN 'Discharged' ELSE NULL END

Return JSON with fields: logic, null_handling, edge_cases, mapping_dict,
transform_type (copy|map|cast|trim|date|custom), confidence (0.0–1.0), reasoning.
"""

DOC_GENERATION_V1 = """You are documenting a migrated warehouse schema for data stewards.
Write a concise business definition for this target column using only the
approved mapping and transformation rule. Do not invent source facts.

Target: {target_table}.{target_column}
Source: {source_table}.{source_column}
Meaning: {inferred_meaning}
Logic: {logic}
Null handling: {null_handling}
Human override: {override_note}

Return JSON with fields: definition, lineage_sentence.
"""

FLAGGING_V1 = """Which mappings should be flagged for human review, and what is the minimum
confidence threshold? Threshold is {threshold}.
Mappings JSON: {mappings_json}
Return JSON: {{ "flagged_source_columns": ["table.column", ...], "rationale": "..." }}
"""

FAILURE_MODE_V1 = """How should the LangGraph workflow handle a partial migration failure — retry
from checkpoint or full rollback? Current node: {node}. Error: {error}.
Checkpoint: {checkpoint}. Return JSON with fields: strategy (retry_checkpoint|rollback),
rationale.
"""

PROMPT_REGISTRY = {
    "schema_inference_v1": SCHEMA_INFERENCE_V1,
    "rule_generation_v1": RULE_GENERATION_V1,
    "doc_generation_v1": DOC_GENERATION_V1,
    "flagging_v1": FLAGGING_V1,
    "failure_mode_v1": FAILURE_MODE_V1,
}


def render(prompt_key: str, **kwargs: object) -> str:
    template = PROMPT_REGISTRY[prompt_key]
    return template.format(**kwargs)
