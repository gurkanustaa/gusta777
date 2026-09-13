from __future__ import annotations

import os
from pathlib import Path
from statistics import mean

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Premier League Predictor", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "premier_predictor"),
        user=os.getenv("POSTGRES_USER", "premier"),
        password=os.getenv("POSTGRES_PASSWORD", "premier"),
        row_factory=psycopg.rows.dict_row,
    )


def clamp(value: float, low: float = 0.05, high: float = 0.95) -> float:
    return max(low, min(high, value))


def recent_team_matches(conn: psycopg.Connection, team_id: int, limit: int = 10) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                match_id, starting_at,
                home_team_id, away_team_id,
                home_score, away_score,
                home_ht_score, away_ht_score
            FROM fact_match
            WHERE (home_team_id = %s OR away_team_id = %s)
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
              AND starting_at < NOW()
            ORDER BY starting_at DESC
            LIMIT %s
            """,
            (team_id, team_id, limit),
        )
        return list(cur.fetchall())


def summarize_team(matches: list[dict], team_id: int) -> dict:
    if not matches:
        return {
            "matches": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "goals_for_avg": 0.0,
            "goals_against_avg": 0.0,
            "first_half_btts_rate": 0.0,
            "second_half_btts_rate": 0.0,
            "full_match_btts_rate": 0.0,
            "points_per_match": 0.0,
        }

    wins = draws = losses = 0
    goals_for: list[int] = []
    goals_against: list[int] = []
    fh_btts: list[int] = []
    sh_btts: list[int] = []
    full_btts: list[int] = []
    points: list[int] = []

    for match in matches:
        is_home = match["home_team_id"] == team_id
        gf = match["home_score"] if is_home else match["away_score"]
        ga = match["away_score"] if is_home else match["home_score"]
        h_ht = match["home_ht_score"] or 0
        a_ht = match["away_ht_score"] or 0
        h_2h = max((match["home_score"] or 0) - h_ht, 0)
        a_2h = max((match["away_score"] or 0) - a_ht, 0)

        goals_for.append(gf)
        goals_against.append(ga)
        fh_btts.append(int(h_ht > 0 and a_ht > 0))
        sh_btts.append(int(h_2h > 0 and a_2h > 0))
        full_btts.append(int((match["home_score"] or 0) > 0 and (match["away_score"] or 0) > 0))

        if gf > ga:
            wins += 1
            points.append(3)
        elif gf == ga:
            draws += 1
            points.append(1)
        else:
            losses += 1
            points.append(0)

    return {
        "matches": len(matches),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for_avg": round(mean(goals_for), 2),
        "goals_against_avg": round(mean(goals_against), 2),
        "first_half_btts_rate": round(mean(fh_btts), 3),
        "second_half_btts_rate": round(mean(sh_btts), 3),
        "full_match_btts_rate": round(mean(full_btts), 3),
        "points_per_match": round(mean(points), 2),
    }


def provisional_prediction(home: dict, away: dict) -> dict:
    # Geçici istatistiksel yaklaşım. ML modeli hazır olduğunda bu fonksiyon model servisiyle değiştirilecek.
    total_ppm = max(home["points_per_match"] + away["points_per_match"], 0.1)
    home_strength = home["points_per_match"] / total_ppm
    away_strength = away["points_per_match"] / total_ppm

    draw_prob = clamp(0.30 - abs(home_strength - away_strength) * 0.18, 0.18, 0.34)
    remaining = 1.0 - draw_prob
    home_prob = remaining * (0.56 * home_strength + 0.44 * 0.52)
    away_prob = max(remaining - home_prob, 0.05)

    total = home_prob + draw_prob + away_prob
    home_prob, draw_prob, away_prob = home_prob / total, draw_prob / total, away_prob / total

    fh_btts = clamp((home["first_half_btts_rate"] + away["first_half_btts_rate"]) / 2, 0.05, 0.80)
    sh_btts = clamp((home["second_half_btts_rate"] + away["second_half_btts_rate"]) / 2, 0.05, 0.90)
    full_btts = clamp((home["full_match_btts_rate"] + away["full_match_btts_rate"]) / 2, 0.10, 0.92)

    confidence = clamp(0.48 + abs(home_prob - away_prob) * 0.55, 0.48, 0.82)

    return {
        "home_win": round(home_prob, 3),
        "draw": round(draw_prob, 3),
        "away_win": round(away_prob, 3),
        "first_half_btts_yes": round(fh_btts, 3),
        "second_half_btts_yes": round(sh_btts, 3),
        "full_match_btts_yes": round(full_btts, 3),
        "confidence": round(confidence, 3),
        "model": "provisional_recent-form_v1",
    }


@app.get("/")
def home_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/statistics")
def statistics_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "statistics.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/upcoming")
def upcoming(limit: int = Query(10, ge=1, le=30)) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.match_id,
                    m.starting_at,
                    m.home_team_id,
                    h.team_name AS home_team,
                    h.image_path AS home_logo,
                    m.away_team_id,
                    a.team_name AS away_team,
                    a.image_path AS away_logo
                FROM fact_match m
                JOIN dim_team h ON h.team_id = m.home_team_id
                JOIN dim_team a ON a.team_id = m.away_team_id
                WHERE m.starting_at >= NOW()
                  AND m.home_score IS NULL
                  AND m.away_score IS NULL
                ORDER BY m.starting_at
                LIMIT %s
                """,
                (limit,),
            )
            fixtures = list(cur.fetchall())

        result = []
        for fixture in fixtures:
            home_form = summarize_team(recent_team_matches(conn, fixture["home_team_id"]), fixture["home_team_id"])
            away_form = summarize_team(recent_team_matches(conn, fixture["away_team_id"]), fixture["away_team_id"])
            fixture["home_form"] = home_form
            fixture["away_form"] = away_form
            fixture["prediction"] = provisional_prediction(home_form, away_form)
            result.append(fixture)

        return result


@app.get("/api/statistics/teams")
def team_statistics(limit_matches: int = Query(10, ge=3, le=20)) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT t.team_id, t.team_name, t.image_path
                FROM dim_team t
                JOIN fact_match m
                  ON m.home_team_id = t.team_id OR m.away_team_id = t.team_id
                WHERE m.league_id = %s
                ORDER BY t.team_name
                """,
                (int(os.getenv("SPORTMONKS_LEAGUE_ID", "8")),),
            )
            teams = list(cur.fetchall())

        output = []
        for team in teams:
            summary = summarize_team(recent_team_matches(conn, team["team_id"], limit_matches), team["team_id"])
            output.append({**team, **summary})

        return output
