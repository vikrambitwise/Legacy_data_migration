# Architecture and product decisions

FDE-CAPSTONE-DE-01 — AI-Assisted Legacy Data Migration Platform.

## Sensitive data acknowledgment

This project is an educational assessment. **No real personal data, customer data, employee records, or confidential business data may be used.** The bundled source database is 100% synthetic (generated names, dates of birth, ZIP codes, and four-digit SSN fragments). Treat even synthetic PII columns as sensitive in documentation and access control. Column-level comments are intentionally absent on the source to simulate the undocumented legacy estate described in the problem statement.

If this design were deployed against a regulated domain (health, finance, public sector):

- Data at rest must use warehouse-native encryption (Snowflake Tri-Secret, BigQuery CMEK, or Postgres TDE / filesystem encryption).
- Access must be role-based: profiler/read on source, loader/write on target, no developer SELECT on production PII without a ticketed role.
- The append-only audit log and LangFuse traces are the audit obligation artifacts. They must be retained per policy and must not be rewritten.

## Confidence threshold: 0.80

The capstone mandates `CONFIDENCE_THRESHOLD=0.80`. We keep that default because:

- It is high enough that undocumented status codes (`pat_st_cd`, `bill_st`) and mixed-format varchar dates (`dsch_dt`) fall through to human review — the failure mode of the previous manual migration.
- It is not so high that primary keys and obvious renames (`pat_id` → `patient_id`) block the pipeline.

Rules with `confidence < 0.80` cannot reach `migration_executor` unless `human_reviewed=true` **and** `override_note` is non-null. This is enforced in `TransformationRule.is_approved_for_execution` and again in the executor. There is no bypass flag.

## Human overrides

Override notes must state *why* a label is correct. Example: “D = Discharged, not Deceased — confirmed against admissions with non-null discharge dates.” Auto-review (`cli.py review --auto`) exists only so evaluators can run the graph non-interactively; it still writes a note that the mapping is unconfirmed by a named steward. Production runs must use `--interactive` or a filled `review_queue.json`.

## Retry vs rollback

- **Transient extract/load errors** (network, warehouse warehouse-suspend): retry with exponential backoff (`MAX_RETRIES`, `RETRY_BASE_SECONDS`) via tenacity.
- **Transformation, approval, or validation failure**: do not leave a half-loaded schema. The executor rolls back by dropping target tables listed in the run checkpoint, then raises. Re-run from the approved rule set; do not invent mappings after failure.
- **Rejects** (unparseable dates, unknown after mapping where business requires a value) are written to `runs/<run_id>/rejects/` and subtracted in reconciliation so row-count drift is explained.

## Source and target choices

**HTML requirement:** PostgreSQL or MySQL source; Snowflake or BigQuery target.

**Implemented:** SQLAlchemy adapters for Postgres, MySQL, Snowflake, and BigQuery.

**Local assumption (this workstation has no Docker and no cloud warehouse):** SQLite source `data/legacy_source.db` and SQLite target `data/target_warehouse.db` so the pipeline is demonstrable end-to-end. `docker-compose.yml` provisions Postgres `legacy_db` + `migration_target` when Docker is available. Switching is an environment-variable change, not a code fork.

## LLM and LangFuse

- Any LangChain-supported provider via `LLM_PROVIDER` + `LLM_API_KEY`.
- If the key is absent, a heuristic mapper/rule/doc path still records `prompt_id` and writes local LangFuse-shaped traces. This is a **demo fallback**, not a substitute for traced LLM calls in a scored submission. Set LangFuse keys for the dashboard deliverable.

## Schema design of the synthetic legacy system

Seven tables, abbreviated names, **no column comments**, nullable FKs, undocumented codes:

- `pat_st_cd`: A/D/I/S plus rare unknown tokens (the “silently corrupted status mapping” scenario).
- `bill_st`: integer 0/1/2/9.
- `dsch_dt`: VARCHAR with ISO, US, and compact dates.

Primary tables seed at **12,000+** patient rows by default.

## Bonus features (labelled)

- PII/sensitive column flags in the profiler (`core/pii.py`).
- FK-graph topological load order (`core/graph.py`).
- Incremental watermark extract (`ENABLE_INCREMENTAL`).
- HTML review queue.
- Optional Airflow DAG (`airflow/migration_dag.py`) — scheduling extension only; Python retry remains the baseline.
