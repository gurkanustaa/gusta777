from __future__ import annotations

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine

load_dotenv()


def get_engine():
    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "premier"),
        password=os.getenv("POSTGRES_PASSWORD", "premier"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "premier_predictor"),
    )
    return create_engine(url)


def load_completed_matches(engine) -> pd.DataFrame:
    query = """
        SELECT
            match_id,
            starting_at,
            home_team_id,
            away_team_id,
            home_score,
            away_score
        FROM fact_match
        WHERE home_team_id IS NOT NULL
          AND away_team_id IS NOT NULL
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
        ORDER BY starting_at, match_id
    """
    return pd.read_sql(query, engine)


def to_team_match_rows(matches: pd.DataFrame) -> pd.DataFrame:
    home = matches[
        ["match_id", "starting_at", "home_team_id", "away_team_id", "home_score", "away_score"]
    ].copy()
    home.columns = ["match_id", "starting_at", "team_id", "opponent_id", "goals_for", "goals_against"]
    home["location"] = "home"

    away = matches[
        ["match_id", "starting_at", "away_team_id", "home_team_id", "away_score", "home_score"]
    ].copy()
    away.columns = ["match_id", "starting_at", "team_id", "opponent_id", "goals_for", "goals_against"]
    away["location"] = "away"

    team_rows = pd.concat([home, away], ignore_index=True)
    team_rows["points"] = 0
    team_rows.loc[team_rows["goals_for"] == team_rows["goals_against"], "points"] = 1
    team_rows.loc[team_rows["goals_for"] > team_rows["goals_against"], "points"] = 3
    team_rows["win"] = (team_rows["points"] == 3).astype(int)
    team_rows["goal_diff"] = team_rows["goals_for"] - team_rows["goals_against"]
    team_rows = team_rows.sort_values(["team_id", "starting_at", "match_id"]).reset_index(drop=True)
    team_rows["matches_played_prior"] = team_rows.groupby("team_id").cumcount()
    return team_rows


def add_rolling_features(team_rows: pd.DataFrame, windows: tuple[int, ...] = (5, 10)) -> pd.DataFrame:
    metrics = ["points", "goals_for", "goals_against", "goal_diff", "win"]

    for window in windows:
        for metric in metrics:
            team_rows[f"{metric}_avg_{window}"] = team_rows.groupby("team_id")[metric].transform(
                lambda series: series.shift(1).rolling(window=window, min_periods=1).mean()
            )

    return team_rows


def build_match_features(matches: pd.DataFrame, team_rows: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [
        "match_id",
        "location",
        "matches_played_prior",
        "points_avg_5",
        "goals_for_avg_5",
        "goals_against_avg_5",
        "goal_diff_avg_5",
        "win_avg_5",
        "points_avg_10",
        "goals_for_avg_10",
        "goals_against_avg_10",
        "goal_diff_avg_10",
        "win_avg_10",
    ]

    home = team_rows.loc[team_rows["location"] == "home", feature_cols].drop(columns="location")
    home = home.rename(columns={col: f"home_{col}" for col in home.columns if col != "match_id"})

    away = team_rows.loc[team_rows["location"] == "away", feature_cols].drop(columns="location")
    away = away.rename(columns={col: f"away_{col}" for col in away.columns if col != "match_id"})

    features = matches.merge(home, on="match_id", how="left").merge(away, on="match_id", how="left")
    features["target"] = "X"
    features.loc[features["home_score"] > features["away_score"], "target"] = "1"
    features.loc[features["home_score"] < features["away_score"], "target"] = "2"
    return features


def main() -> None:
    engine = get_engine()
    matches = load_completed_matches(engine)

    if matches.empty:
        print("No completed matches found. Run the ETL first.")
        return

    team_rows = to_team_match_rows(matches)
    team_rows = add_rolling_features(team_rows)
    features = build_match_features(matches, team_rows)

    features.to_sql("ml_match_features", engine, if_exists="replace", index=False)
    print(f"Created ml_match_features with {len(features)} rows.")


if __name__ == "__main__":
    main()
