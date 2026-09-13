from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Iterator

import requests
from dotenv import load_dotenv

load_dotenv()


class SportmonksApiError(RuntimeError):
    """Raised when Sportmonks returns an unexpected response."""


class SportmonksClient:
    BASE_URL = "https://api.sportmonks.com/v3/football"

    def __init__(self, api_token: str | None = None, league_id: int | None = None, timeout: int = 45):
        self.api_token = api_token or os.getenv("SPORTMONKS_API_TOKEN")
        self.league_id = league_id or int(os.getenv("SPORTMONKS_LEAGUE_ID", "8"))
        self.timeout = timeout

        if not self.api_token or self.api_token == "YOUR_TOKEN_HERE":
            raise ValueError("SPORTMONKS_API_TOKEN is missing. Add it to your .env file.")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": self.api_token,
                "User-Agent": "gusta777-premier-league-predictor/1.0",
            }
        )

    def _get_paginated(self, path: str, params: dict | None = None) -> list[dict]:
        params = dict(params or {})
        params.setdefault("per_page", 50)
        page = 1
        rows: list[dict] = []

        while True:
            request_params = {**params, "page": page}
            response = self.session.get(
                f"{self.BASE_URL}{path}",
                params=request_params,
                timeout=self.timeout,
            )

            if response.status_code >= 400:
                try:
                    details = response.json()
                except ValueError:
                    details = response.text
                raise SportmonksApiError(
                    f"Sportmonks request failed ({response.status_code}): {details}"
                )

            payload = response.json()
            rows.extend(payload.get("data", []))

            pagination = payload.get("pagination") or {}
            if not pagination.get("has_more"):
                break

            page += 1

        return rows

    def get_fixtures(self, start_date: date, end_date: date) -> list[dict]:
        """Return Premier League fixtures and match-level statistics for a date range."""
        if end_date < start_date:
            raise ValueError("end_date cannot be earlier than start_date")

        params = {
            "include": "participants;scores;statistics.type;xGFixture.type",
            "filters": f"fixtureLeagues:{self.league_id}",
            "order": "asc",
        }

        return self._get_paginated(
            f"/fixtures/between/{start_date.isoformat()}/{end_date.isoformat()}",
            params=params,
        )


def date_chunks(start_date: date, end_date: date, chunk_days: int = 100) -> Iterator[tuple[date, date]]:
    """Split a long history request into smaller, non-overlapping date windows."""
    if chunk_days < 1:
        raise ValueError("chunk_days must be at least 1")

    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end_date)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)
