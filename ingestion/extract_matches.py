
import json
import os
import tempfile
from pathlib import Path

from ingestion.riot_client import RiotClient


DATA_DIR = Path("data")


def is_valid_json(
    path: Path,
    match_id: str,
    data_type: str
) -> bool:
    """Vérifie l'intégrité minimale d'un JSON Riot."""

    if not path.is_file():
        return False

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if data["metadata"]["matchId"] != match_id:
            return False

        if data_type == "match":
            return (
                isinstance(data["info"]["participants"], list)
                and len(data["info"]["participants"]) > 0
            )

        if data_type == "timeline":
            return (
                isinstance(data["info"]["frames"], list)
                and len(data["info"]["frames"]) > 0
            )

        return False

    except (OSError, ValueError, KeyError, TypeError):
        return False


def save_json_atomic(data: dict, path: Path) -> None:
    """Écrit un JSON temporaire puis le remplace atomiquement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.stem}-",
            suffix=".tmp",
            delete=False
        ) as file:
            temporary_path = Path(file.name)

            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, path)

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def extract_match(client: RiotClient, match_id: str) -> None:
    """Extrait et sauvegarde un match et sa timeline."""

    targets = (
        (
            "match",
            DATA_DIR / "matches" / f"{match_id}.json",
            client.get_match
        ),
        (
            "timeline",
            DATA_DIR / "timelines" / f"{match_id}.json",
            client.get_timeline
        )
    )

    for data_type, path, fetch in targets:
        if is_valid_json(path, match_id, data_type):
            print(f"SKIP {data_type} : {match_id}")
            continue

        if path.exists():
            print(f"JSON invalide, remplacement : {path}")

        data = fetch(match_id)

        if data["metadata"]["matchId"] != match_id:
            raise ValueError(
                f"{data_type} match ID mismatch: {match_id}"
            )

        if data_type == "match":
            if not isinstance(data["info"]["participants"], list):
                raise ValueError("Missing participants")

        if data_type == "timeline":
            if not isinstance(data["info"]["frames"], list):
                raise ValueError("Missing frames")

        save_json_atomic(data, path)
        print(f"Sauvegardé : {path}")


def is_valid_json(
    path: Path,
    match_id: str,
    data_type: str
) -> bool:
    """Vérifie l'intégrité minimale d'un JSON Riot."""

    if not path.is_file():
        return False

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if data["metadata"]["matchId"] != match_id:
            return False

        if data_type == "match":
            return (
                isinstance(data["info"]["participants"], list)
                and len(data["info"]["participants"]) > 0
            )

        if data_type == "timeline":
            return (
                isinstance(data["info"]["frames"], list)
                and len(data["info"]["frames"]) > 0
            )

        return False

    except (OSError, ValueError, KeyError, TypeError):
        return False
