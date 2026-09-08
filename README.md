# AI-Assisted Legacy Data Migration Platform

FDE Capstone **FDE-CAPSTONE-DE-01**. LangChain agents infer schema semantics and emit auditable transformation rules. LangGraph orchestrates the pipeline with a human-in-the-loop confidence gate at every high-risk mapping. Great Expectations, dbt, and LangFuse provide validation and observability.

> Synthetic data only. Do not connect this project to production databases that contain real personal or customer data.

## Project Overview

Legacy migrations fail on **semantics**, not bytes. This platform:

1. Profiles a legacy OLTP schema (PostgreSQL, MySQL, or local SQLite).
2. Uses a LangChain mapping agent to propose source→target mappings with confidence scores and prompt IDs.
3. Pauses at `human_review_gate` when confidence is below `CONFIDENCE_THRESHOLD` (default **0.80**).
4. Generates transformation rules in the mandatory JSON schema.
5. Executes extract / transform / load to Snowflake, BigQuery, Postgres, or a local warehouse stand-in.
6. Validates with Great Expectations (three checkpoints) and dbt tests, then writes a reconciliation report and target data dictionary.

## Architecture Description

Six layers, matching the capstone architecture guide:

| Layer | Implementation |
| --- | --- |
| Source | `docker-compose.yml` PostgreSQL (`legacy_db`) or SQLite fallback |
| Profiling | `agents/schema_profiler.py` — SQLAlchemy reflection, null rates, cardinality, FK graph, PII flags |
| Orchestration | `workflow/langgraph_orchestrator.py` — 7 LangGraph nodes |
| Human review | CLI, JSON queue, HTML queue (`review_queue.html`) |
| Validation | Great Expectations + dbt + reconciliation |
| Observability | LangFuse SDK when keys are set; local JSONL traces otherwise |

**LangGraph nodes (in order):** `schema_profiler` → `ai_mapper` → `human_review_gate` → `rule_generator` → `migration_executor` → `validator` → `doc_generator`

See `docs/architecture.png` and `DECISIONS.md`.

## Setup Instructions

**Prerequisites:** Python 3.10–3.13, pip. Docker Desktop is recommended for PostgreSQL. Snowflake or BigQuery credentials are required for a cloud warehouse target.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

**With native PostgreSQL 18 (this workstation) and Snowflake:**

1. Put the Postgres installer password and Snowflake trial credentials in `.env`:

```
SOURCE_DB_URL=postgresql://postgres:<PASSWORD>@localhost:5432/legacy_db
TARGET_WAREHOUSE=snowflake
SNOWFLAKE_ACCOUNT=<org-account>
SNOWFLAKE_USER=<user>
SNOWFLAKE_PASSWORD=<password>
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=MIGRATION_TARGET
```

2. Create/seed the source and run:

```powershell
.\.venv\Scripts\Activate.ps1
python cli.py verify-stack
python cli.py seed --patients 12000
python cli.py migrate
python cli.py review --interactive
```

Docker Compose Postgres is optional and mapped to **host port 5433** so it does not collide with PostgreSQL 18 on 5432.

```
LLM_PROVIDER=none
SOURCE_DB_URL=sqlite:///./data/legacy_source.db
TARGET_WAREHOUSE=sqlite
TARGET_DB_URL=sqlite:///./data/target_warehouse.db
CONFIDENCE_THRESHOLD=0.80
```

Seed the synthetic legacy database (12,000 patients, 7 tables):

```powershell
python cli.py seed --patients 12000
```

With Docker / Postgres:

```powershell
docker compose up -d
# set SOURCE_DB_URL=postgresql://migrate:migrate@localhost:5432/legacy_db
python cli.py seed --patients 12000
```

## Environment Variables

Documented in `.env.example`. Required names from the capstone spec:

| Variable | Purpose |
| --- | --- |
| `LLM_API_KEY` | OpenAI or Anthropic key for LangChain agents |
| `SOURCE_DB_URL` | SQLAlchemy URL for the legacy source |
| `SNOWFLAKE_ACCOUNT` / `USER` / `PASSWORD` / `WAREHOUSE` / `DATABASE` | Snowflake target |
| `GOOGLE_APPLICATION_CREDENTIALS` / `BIGQUERY_PROJECT_ID` | BigQuery target |
| `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` / `HOST` | LLM tracing |
| `CONFIDENCE_THRESHOLD` | Default `0.80` |

Additional variables (`LLM_PROVIDER`, `TARGET_WAREHOUSE`, `TARGET_DB_URL`, `REVIEW_MODE`, retry settings) are documented in `.env.example`.

Never commit a populated `.env` or service-account JSON.

## How to Run the Migration Pipeline

```powershell
python cli.py nodes
python cli.py migrate
```

The graph **always** stops at `human_review_gate` when any mapping is below the threshold. Inspect:

- `runs/<run_id>/review_queue.json`
- `runs/<run_id>/review_queue.html`
- `runs/<run_id>/schema_profile.json`
- `runs/<run_id>/mappings.json`

Then complete review and resume:

```powershell
python cli.py review --interactive
# or edit review_queue.json and:
python cli.py review --file .\runs\<run_id>\review_queue.json
```

`--auto` writes explicit override notes for local/CI demonstration only. It does **not** skip the gate.

A complete local demo:

```powershell
python cli.py seed --patients 12000
python cli.py migrate
python cli.py review --auto
python cli.py inspect-audit
```

## How to Rollback a Failed Migration

The executor retries extract/load with exponential backoff. If a load still fails, it drops target tables created in that run (checkpoint-aware). To roll back manually:

```powershell
python cli.py rollback --run-id <run_id>
```

This drops warehouse tables recorded in `runs/<run_id>/executor_checkpoint.json`. Re-run `python cli.py migrate` after fixing the cause. Partial reruns use the same approved rule file; rejected rows remain in `runs/<run_id>/rejects/`.

**Decision:** retry from checkpoint for transient warehouse errors; full rollback of loaded tables for transformation or validation failures. Rationale is in `DECISIONS.md`.

## How to Inspect AI Decisions (Audit Log + LangFuse)

```powershell
python cli.py inspect-audit
python cli.py inspect-audit --run-id <run_id>
```

- Immutable JSON log: `audit/migration_audit_log.json` (append-only).
- Every AI artifact includes `prompt_id`.
- LangFuse Cloud: set the three `LANGFUSE_*` variables and open the project dashboard (per-agent traces for the run).
- Local fallback traces: `runs/<run_id>/langfuse_local_traces.jsonl` (prompt input, output, latency).

## Known Limitations

- Without `LLM_API_KEY`, agents use a conservative heuristic mapper that still emits prompt IDs and under-threshold confidence for undocumented codes so the HITL gate is exercised.
- Local SQLite is a development stand-in for Postgres/MySQL source and Snowflake/BigQuery target. Cloud adapters are implemented and selected via `TARGET_WAREHOUSE`.
- Great Expectations 1.x fluent API is used when the package imports; otherwise a pandas validator writes the same checkpoint JSON (still blocking on failure).
- dbt `dbt test` requires `validation/dbt_models/profiles.yml`. Equivalent SQL tests always run against the target via `validation/dbt_runner.py`.
- `--auto` review is not acceptable for production sign-off.
- Mixed `dsch_dt` formats that cannot be parsed are rejected (CSV under `rejects/`) and excluded from row-count reconciliation.
- Incremental mode (`ENABLE_INCREMENTAL=true`) is watermark-based on `created_ts` and is a bonus path, not the default full-refresh load.

## Project layout

Matches the required ZIP structure, plus supporting packages:

```
README.md
DECISIONS.md
.env.example
agents/
workflow/langgraph_orchestrator.py
validation/great_expectations/
validation/dbt_models/
audit/migration_audit_log.json
docs/architecture.png
```
