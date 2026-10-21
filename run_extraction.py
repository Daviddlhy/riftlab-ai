import logging
import os

import requests
from dotenv import load_dotenv

from ingestion.extract_matches import (
    DATA_DIR,
    extract_match,
    is_valid_json,
)
from ingestion.riot_client import RiotClient

MAX_MATCHES = 50  # Premier test, puis 50


def main():
    load_dotenv()

    client = RiotClient()

    account = client.get_account(
        game_name=os.environ["RIOT_GAME_NAME"],
        tag_line=os.environ["RIOT_TAG_LINE"],
    )

    match_ids = client.get_all_match_ids(
        puuid=account["puuid"],
        max_matches=MAX_MATCHES,
        page_size=20,
        queue=420,
    )

    stats = {
        "processed": 0,
        "skipped": 0,
        "failed": 0,
    }

    print(f"\nMatchs trouvés : {len(match_ids)}")

    for index, match_id in enumerate(match_ids, start=1):
        print(f"\n[{index}/{len(match_ids)}] {match_id}")

        match_path = DATA_DIR / "matches" / f"{match_id}.json"
        timeline_path = DATA_DIR / "timelines" / f"{match_id}.json"

        already_complete = is_valid_json(match_path, match_id, "match") and is_valid_json(
            timeline_path, match_id, "timeline"
        )

        try:
            extract_match(client, match_id)

            if already_complete:
                stats["skipped"] += 1
            else:
                stats["processed"] += 1

        except requests.HTTPError as error:
            stats["failed"] += 1
            logging.error("Échec HTTP %s : %s", match_id, error)

            status = error.response.status_code if error.response is not None else None
            if status in (401, 403, 429):
                print("Arrêt : problème d'accès ou quota Riot !")
                break

        except (requests.RequestException, ValueError, KeyError, OSError) as error:
            stats["failed"] += 1
            logging.error("Échec %s : %s", match_id, error)

    print("\n===== BILAN EXTRACTION =====")
    print(f"Matchs traités : {stats['processed.']}")
    print(f"Matchs ignorés : {stats['skipped.']}")
    print(f"Matchs échoués : {stats['failed.']}")


if __name__ == "__main__":
    main()
