from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from etl.sportmonks_api import SportmonksClient, date_chunks

load_dotenv()


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "premier_predictor"),
        user=os.getenv("POSTGRES_USER", "premier"),
        password=os.getenv("POSTGRES_PASSWORD", "premier"),
    )


def to_decimal(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def score_value(scores: list[dict], description: str, location: str) -> int | None:
    for row in scores:
        score = row.get("score") or {}
        if row.get("description") == description and score.get("participant") == location:
            goals = score.get("goals")
            return int(goals) if goals is not None else None
    return None


def participant_by_location(fixture: dict, location: str) -> dict | None:
    for participant in fixture.get("participants") or []:
        if (participant.get("meta") or {}).get("location") == location:
            return participant
    return None


def upsert_team(cur: psycopg.Cursor, team: dict | None) -> int | None:
    if not team or team.get("id") is None:
        return None

    cur.execute(
        """
        INSERT INTO dim_team (
            team_id, team_name, short_code, country_id, venue_id,
            image_path, founded, raw_team, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (team_id) DO UPDATE SET
            team_name = EXCLUDED.team_name,
            short_code = EXCLUDED.short_code,
            country_id = EXCLUDED.country_id,
            venue_id = EXCLUDED.venue_id,
            image_path = EXCLUDED.image_path,
            founded = EXCLUDED.founded,
            raw_team = EXCLUDED.raw_team,
            updated_at = NOW()
        """,
        (
            team["id"],
            team.get("name") or f"team_{team['id']}",
            team.get("short_code"),
            team.get("country_id"),
            team.get("venue_id"),
            team.get("image_path"),
            team.get("founded"),
            Jsonb(team),
        ),
    )
    return int(team["id"])


def upsert_fixture(cur: psycopg.Cursor, fixture: dict) -> tuple[int | None, int | None, int]:
    home = participant_by_location(fixture, "home")
    away = participant_by_location(fixture, "away")
    home_team_id = upsert_team(cur, home)
    away_team_id = upsert_team(cur, away)

    scores = fixture.get("scores") or []
    home_score = score_value(scores, "CURRENT", "home")
    away_score = score_value(scores, "CURRENT", "away")
    home_ht_score = score_value(scores, "1ST_HALF", "home")
    away_ht_score = score_value(scores, "1ST_HALF", "away")

    cur.execute(
        """
        INSERT INTO fact_match (
            match_id, league_id, season_id, stage_id, round_id, state_id,
            venue_id, match_name, starting_at, result_info,
            home_team_id, away_team_id, home_score, away_score,
            home_ht_score, away_ht_score, raw_fixture, updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, NOW()
        )
        ON CONFLICT (match_id) DO UPDATE SET
            league_id = EXCLUDED.league_id,
            season_id = EXCLUDED.season_id,
            stage_id = EXCLUDED.stage_id,
            round_id = EXCLUDED.round_id,
            state_id = EXCLUDED.state_id,
            venue_id = EXCLUDED.venue_id,
            match_name = EXCLUDED.match_name,
            starting_at = EXCLUDED.starting_at,
            result_info = EXCLUDED.result_info,
            home_team_id = EXCLUDED.home_team_id,
            away_team_id = EXCLUDED.away_team_id,
            home_score = EXCLUDED.home_score,
            away_score = EXCLUDED.away_score,
            home_ht_score = EXCLUDED.home_ht_score,
            away_ht_score = EXCLUDED.away_ht_score,
            raw_fixture = EXCLUDED.raw_fixture,
            updated_at = NOW()
        """,
        (
            fixture["id"],
            fixture.get("league_id"),
            fixture.get("season_id"),
            fixture.get("stage_id"),
            fixture.get("round_id"),
            fixture.get("state_id"),
            fixture.get("venue_id"),
            fixture.get("name"),
            fixture.get("starting_at"),
            fixture.get("result_info"),
            home_team_id,
            away_team_id,
            home_score,
            away_score,
            home_ht_score,
            away_ht_score,
            Jsonb(fixture),
        ),
    )

    return home_team_id, away_team_id, 1


def resolve_team_id(row: dict, home_team_id: int | None, away_team_id: int | None) -> int | None:
    participant_id = row.get("participant_id")
    if participant_id is not None:
        return int(participant_id)

    location = row.get("location")
    if location == "home":
        return home_team_id
    if location == "away":
        return away_team_id
    return None


def upsert_statistics(
    cur: psycopg.Cursor,
    fixture: dict,
    home_team_id: int | None,
    away_team_id: int | None,
) -> int:
    written = 0
    for stat in fixture.get("statistics") or []:
        team_id = resolve_team_id(stat, home_team_id, away_team_id)
        type_id = stat.get("type_id")
        if team_id is None or type_id is None:
            continue

        data = stat.get("data") or {}
        raw_value = data.get("value")
        numeric_value = to_decimal(raw_value)
        text_value = None if numeric_value is not None else (
            json.dumps(raw_value, ensure_ascii=False) if isinstance(raw_value, (dict, list)) else str(raw_value)
            if raw_value is not None else None
        )
        stat_type = stat.get("type") or {}

        cur.execute(
            """
            INSERT INTO fact_match_statistic (
                match_id, team_id, statistic_id, type_id, type_name,
                location, value_numeric, value_text, raw_value, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (match_id, team_id, type_id) DO UPDATE SET
                statistic_id = EXCLUDED.statistic_id,
                type_name = EXCLUDED.type_name,
                location = EXCLUDED.location,
                value_numeric = EXCLUDED.value_numeric,
                value_text = EXCLUDED.value_text,
                raw_value = EXCLUDED.raw_value,
                updated_at = NOW()
            """,
            (
                fixture["id"],
                team_id,
                stat.get("id"),
                type_id,
                stat_type.get("name"),
                stat.get("location"),
                numeric_value,
                text_value,
                Jsonb(data),
            ),
        )
        written += 1
    return written


def upsert_xg(
    cur: psycopg.Cursor,
    fixture: dict,
    home_team_id: int | None,
    away_team_id: int | None,
) -> int:
    written = 0
    for row in fixture.get("xgfixture") or fixture.get("xGFixture") or []:
        team_id = resolve_team_id(row, home_team_id, away_team_id)
        type_id = row.get("type_id")
        data = row.get("data") or {}
        xg_value = to_decimal(data.get("value"))

        if team_id is None or type_id is None or xg_value is None:
            continue

        cur.execute(
            """
            INSERT INTO fact_match_xg (
                match_id, team_id, type_id, location, xg_value, raw_value, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (match_id, team_id, type_id) DO UPDATE SET
                location = EXCLUDED.location,
                xg_value = EXCLUDED.xg_value,
                raw_value = EXCLUDED.raw_value,
                updated_at = NOW()
            """,
            (
                fixture["id"],
                team_id,
                type_id,
                row.get("location"),
                xg_value,
                Jsonb(data),
            ),
        )
        written += 1
    return written


def start_run(conn: psycopg.Connection, start_date: date, end_date: date) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_run_log (process_name, start_date, end_date, status)
            VALUES ('premier_league_matches', %s, %s, 'RUNNING')
            RETURNING run_id
            """,
            (start_date, end_date),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return int(run_id)


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    status: str,
    rows_read: int,
    rows_written: int,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE etl_run_log
               SET finished_at = NOW(),
                   status = %s,
                   rows_read = %s,
                   rows_written = %s,
                   error_message = %s
             WHERE run_id = %s
            """,
            (status, rows_read, rows_written, error_message, run_id),
        )
    conn.commit()


def load(start_date: date, end_date: date, chunk_days: int) -> None:
    client = SportmonksClient()
    rows_read = 0
    rows_written = 0

    with get_connection() as conn:
        run_id = start_run(conn, start_date, end_date)

        try:
            for chunk_start, chunk_end in date_chunks(start_date, end_date, chunk_days):
                print(f"Fetching EPL fixtures: {chunk_start} -> {chunk_end}")
                fixtures = client.get_fixtures(chunk_start, chunk_end)
                rows_read += len(fixtures)

                with conn.cursor() as cur:
                    for fixture in fixtures:
                        home_team_id, away_team_id, count = upsert_fixture(cur, fixture)
                        rows_written += count
                        rows_written += upsert_statistics(cur, fixture, home_team_id, away_team_id)
                        rows_written += upsert_xg(cur, fixture, home_team_id, away_team_id)

                conn.commit()
                print(f"Loaded {len(fixtures)} fixtures for this window.")

            finish_run(conn, run_id, "SUCCESS", rows_read, rows_written)
            print(
                f"ETL completed successfully. fixtures={rows_read}, database_rows={rows_written}"
            )
        except Exception as exc:
            conn.rollback()
            finish_run(conn, run_id, "FAILED", rows_read, rows_written, str(exc)[:4000])
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Premier League fixtures into PostgreSQL")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=int(os.getenv("ETL_LOOKBACK_DAYS", "365")),
        help="Days to load when --start-date is omitted (default: ETL_LOOKBACK_DAYS or 365)",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=int(os.getenv("ETL_CHUNK_DAYS", "100")),
        help="Split longer history loads into date windows",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    end_date = args.end_date or date.today()

    if args.start_date:
        start_date = args.start_date
    else:
        if args.lookback_days < 1:
            raise ValueError("lookback-days must be at least 1")
        start_date = end_date - timedelta(days=args.lookback_days - 1)

    if end_date < start_date:
        raise ValueError("end-date cannot be earlier than start-date")

    load(start_date, end_date, args.chunk_days)


if __name__ == "__main__":
    main()
