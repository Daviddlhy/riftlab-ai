import logging
import os
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
from dotenv import load_dotenv


class RiotClient:
    """Client HTTP pour l'API Riot Games."""

    def __init__(self):
        load_dotenv()

        api_key = os.getenv("RIOT_API_KEY")
        region = os.getenv("RIOT_REGION", "europe")

        if not api_key:
            raise ValueError("RIOT_API_KEY is missing.")

        self.base_url = f"https://{region}.api.riotgames.com"

        self.session = requests.Session()
        # Espacement minimal entre deux requêtes HTTP
        self.min_request_interval = 1.5

        # Horodatage de la dernière requête
        self.last_request_time = None
        self.session.headers.update({"X-Riot-Token": api_key})

    def _wait_for_rate_limit(self) -> None:
        """Espace les requêtes HTTP pour limiter leur débit."""

        now = time.monotonic()

        if self.last_request_time is not None:
            elapsed = now - self.last_request_time

            remaining = self.min_request_interval - elapsed

            if remaining > 0:
                time.sleep(remaining)

        self.last_request_time = time.monotonic()

    def _get(self, endpoint: str, params: dict | None = None):
        """GET avec retry sur rate limit et erreurs temporaires."""

        max_attempts = 5

        for attempt in range(max_attempts):
            try:
                self._wait_for_rate_limit()
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    params=params,
                    timeout=15,
                )

                # Rate limit ou erreur temporaire
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == max_attempts - 1:
                        response.raise_for_status()

                    retry_after = response.headers.get("Retry-After")
                    delay = None

                    if retry_after:
                        try:
                            delay = max(0, float(retry_after))
                        except ValueError:
                            try:
                                retry_date = parsedate_to_datetime(retry_after)
                                if retry_date.tzinfo is None:
                                    retry_date = retry_date.replace(tzinfo=UTC)
                                delay = max(0, (retry_date - datetime.now(UTC)).total_seconds())
                            except (TypeError, ValueError, OverflowError):
                                pass

                    if delay is None:
                        delay = min(2**attempt, 30)
                        delay += random.uniform(0, 0.5)

                    logging.warning(
                        "Riot API HTTP %s - retry %s/%s in %.1fs",
                        response.status_code,
                        attempt + 1,
                        max_attempts,
                        delay,
                    )

                    time.sleep(delay)
                    continue

                # 401, 403, 404... : pas de retry
                response.raise_for_status()
                return response.json()

            except (requests.Timeout, requests.ConnectionError):
                if attempt == max_attempts - 1:
                    raise

                delay = min(2**attempt, 30)
                delay += random.uniform(0, 0.5)

                logging.warning(
                    "Riot API network error - retry in %.1fs",
                    delay,
                )
                time.sleep(delay)

        raise RuntimeError("Riot API retries exhausted")

    def get_account(self, game_name: str, tag_line: str) -> dict:
        """Récupère le PUUID d'un compte Riot."""

        endpoint = (
            "/riot/account/v1/accounts/by-riot-id/"
            f"{quote(game_name, safe=' ')}/{quote(tag_line, safe=' ')}"
        )

        data = self._get(endpoint)

        if "puuid" not in data:
            raise ValueError("Missing PUUID in account response.")

        return data

    def get_match_ids(
        self, puuid: str, start: int = 0, count: int = 20, queue: int = 420
    ) -> list[str]:
        """Récupère une page de matchs calssés Solo/Duo."""

        if not 1 <= count <= 100:
            raise ValueError("Count must be between 1 and 100")
        endpoint = f"/lol/match/v5/matches/by-puuid/{quote(puuid, safe='')}/ids"

        return self._get(endpoint, params={"start": start, "count": count, "queue": queue})

    def get_match(self, match_id: str) -> dict:
        """Récupère les détails d'un match."""

        endpoint = f"/lol/match/v5/matches/{quote(match_id, safe='')}"

        return self._get(endpoint)

    def get_timeline(self, match_id: str) -> dict:
        """Récupère la timeline d'un match."""

        endpoint = f"/lol/match/v5/matches/{quote(match_id, safe='')}/timeline"

        return self._get(endpoint)

    def get_all_match_ids(
        self, puuid: str, max_matches: int = 100, page_size: int = 20, queue: int = 420
    ) -> list[str]:
        """Récupère plusieurs pages de Match IDs."""

        if max_matches < 1:
            raise ValueError("max_matches must be positive")

        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")

        match_ids = []
        start = 0

        while len(match_ids) < max_matches:
            count = min(page_size, max_matches - len(match_ids))

            page = self.get_match_ids(puuid=puuid, start=start, count=count, queue=queue)

            if not page:
                break

            match_ids.extend(page)
            start += len(page)

            if len(page) < count:
                break

        return match_ids
