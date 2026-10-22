"""Lancement manuel du pipeline complet ou rejeu du lot local vers Azure."""

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from ingestion.blob_storage import BlobStorage
from ingestion.pipeline import run_pipeline
from ingestion.riot_client import RiotClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local", action="store_true", help="Rejouer le lot local sans appeler Riot"
    )
    parser.add_argument("--max-matches", type=int, default=50)
    parser.add_argument("--resume-manifest", type=Path, help="Reprendre les IDs d'un ancien lot")
    args = parser.parse_args()
    if args.max_matches < 1:
        parser.error("--max-matches doit être positif")
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    ids = None
    client = None
    if args.local:
        ids = sorted(
            {
                p.stem
                for folder in ("matches", "timelines")
                for p in (Path("data") / folder).glob("*.json")
            }
        )
    else:
        client = RiotClient()
    if args.resume_manifest:
        try:
            previous = json.loads(args.resume_manifest.read_text())
            ids = list(dict.fromkeys(o["match_id"] for o in previous["operations"]))
        except (OSError, ValueError, KeyError, TypeError):
            parser.error("Manifest de reprise illisible ou invalide")
    report = run_pipeline(
        BlobStorage(),
        client,
        match_ids=ids,
        max_matches=args.max_matches,
        game_name=os.getenv("RIOT_GAME_NAME"),
        tag_line=os.getenv("RIOT_TAG_LINE"),
    )
    print(f"{report['status']} : {report['run_id']}")
    print(f"Manifest local : data/manifests/{report['run_id']}/manifest.json")
    return 0 if report["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
