CREATE TABLE IF NOT EXISTS dim_team (
    team_id BIGINT PRIMARY KEY,
    team_name TEXT NOT NULL,
    short_code TEXT,
    country_id BIGINT,
    venue_id BIGINT,
    image_path TEXT,
    founded INTEGER,
    raw_team JSONB,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fact_match (
    match_id BIGINT PRIMARY KEY,
    league_id BIGINT NOT NULL,
    season_id BIGINT,
    stage_id BIGINT,
    round_id BIGINT,
    state_id BIGINT,
    venue_id BIGINT,
    match_name TEXT,
    starting_at TIMESTAMPTZ,
    result_info TEXT,
    home_team_id BIGINT,
    away_team_id BIGINT,
    home_score INTEGER,
    away_score INTEGER,
    home_ht_score INTEGER,
    away_ht_score INTEGER,
    raw_fixture JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_match_home_team FOREIGN KEY (home_team_id) REFERENCES dim_team(team_id),
    CONSTRAINT fk_match_away_team FOREIGN KEY (away_team_id) REFERENCES dim_team(team_id)
);

CREATE INDEX IF NOT EXISTS ix_fact_match_starting_at ON fact_match(starting_at);
CREATE INDEX IF NOT EXISTS ix_fact_match_league_date ON fact_match(league_id, starting_at);
CREATE INDEX IF NOT EXISTS ix_fact_match_home_team ON fact_match(home_team_id, starting_at);
CREATE INDEX IF NOT EXISTS ix_fact_match_away_team ON fact_match(away_team_id, starting_at);

CREATE TABLE IF NOT EXISTS fact_match_statistic (
    match_id BIGINT NOT NULL,
    team_id BIGINT NOT NULL,
    statistic_id BIGINT,
    type_id BIGINT NOT NULL,
    type_name TEXT,
    location TEXT,
    value_numeric NUMERIC,
    value_text TEXT,
    raw_value JSONB,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (match_id, team_id, type_id),
    CONSTRAINT fk_stat_match FOREIGN KEY (match_id) REFERENCES fact_match(match_id) ON DELETE CASCADE,
    CONSTRAINT fk_stat_team FOREIGN KEY (team_id) REFERENCES dim_team(team_id)
);

CREATE INDEX IF NOT EXISTS ix_fact_match_statistic_type ON fact_match_statistic(type_id, match_id);
CREATE INDEX IF NOT EXISTS ix_fact_match_statistic_team ON fact_match_statistic(team_id, match_id);

CREATE TABLE IF NOT EXISTS fact_match_xg (
    match_id BIGINT NOT NULL,
    team_id BIGINT NOT NULL,
    type_id BIGINT NOT NULL,
    location TEXT,
    xg_value NUMERIC,
    raw_value JSONB,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (match_id, team_id, type_id),
    CONSTRAINT fk_xg_match FOREIGN KEY (match_id) REFERENCES fact_match(match_id) ON DELETE CASCADE,
    CONSTRAINT fk_xg_team FOREIGN KEY (team_id) REFERENCES dim_team(team_id)
);

CREATE INDEX IF NOT EXISTS ix_fact_match_xg_team ON fact_match_xg(team_id, match_id);

CREATE TABLE IF NOT EXISTS etl_run_log (
    run_id BIGSERIAL PRIMARY KEY,
    process_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    start_date DATE,
    end_date DATE,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    rows_read INTEGER NOT NULL DEFAULT 0,
    rows_written INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);
