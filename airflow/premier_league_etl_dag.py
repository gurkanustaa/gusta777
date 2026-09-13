from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="premier_league_etl",
    description="Refresh recent Premier League fixtures and statistics from Sportmonks",
    start_date=pendulum.datetime(2026, 9, 1, tz="Europe/Istanbul"),
    schedule="0 3 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "gusta777",
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["premier-league", "sportmonks", "etl"],
) as dag:
    refresh_recent_matches = BashOperator(
        task_id="refresh_recent_matches",
        bash_command=(
            'cd "${GUSTA777_PROJECT_ROOT:-/opt/airflow/gusta777}" '
            "&& python -m etl.load_matches --lookback-days 14"
        ),
    )

    refresh_recent_matches
