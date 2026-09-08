"""
Optional Airflow DAG wrapping the Python retry baseline.

This is a scheduling extension (capstone bonus). The required executor already
retries with exponential backoff in etl/migration_executor.py. Use this DAG
only when Airflow is available in the environment.
"""

from __future__ import annotations

from datetime import datetime

try:
    from airflow import DAG
    from airflow.operators.bash import BashOperator
except Exception:  # pragma: no cover - Airflow is optional
    DAG = None
    BashOperator = None


def create_dag():
    if DAG is None:
        raise RuntimeError("apache-airflow is not installed")
    with DAG(
        dag_id="legacy_migration_pipeline",
        start_date=datetime(2026, 1, 1),
        schedule=None,
        catchup=False,
        tags=["legacy-migration", "fde-capstone"],
    ) as dag:
        seed = BashOperator(
            task_id="seed_source",
            bash_command="python cli.py seed --patients 12000",
        )
        migrate = BashOperator(
            task_id="migrate_until_review_gate",
            bash_command="python cli.py migrate",
        )
        # Human review is intentionally NOT automated in Airflow.
        resume = BashOperator(
            task_id="resume_after_review_file",
            bash_command="python cli.py review --file ./runs/$(cat ./runs/LATEST_RUN.txt | xargs basename)/review_queue.json",
        )
        seed >> migrate >> resume
        return dag


if DAG is not None:
    dag = create_dag()
