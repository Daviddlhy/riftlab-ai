import json
import os
import tempfile
from pathlib import Path

from ingestion.riot_client import RiotClient

DATA_DIR = Path("data")


def validate_payload(data: dict, match_id: str, data_type: str) -> None:
    """Contrat minimal commun aux réponses Riot et aux fichiers locaux."""
    field = {"match": "participants", "timeline": "frames"}[data_type]
    try:
        valid = (
            data["metadata"]["matchId"] == match_id
            and isinstance(data["info"][field], list)
            and bool(data["info"][field])
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise ValueError(f"Invalid {data_type} payload")


def extract_payload(client, match_id: str, data_type: str, path: Path) -> bool:
    """Réutilise un fichier valide ou récupère et valide un endpoint Riot."""
    if is_valid_json(path, match_id, data_type):
        return False
    if client is None:
        raise ValueError("Missing or invalid local payload")
    fetch = client.get_match if data_type == "match" else client.get_timeline
    data = fetch(match_id)
    validate_payload(data, match_id, data_type)
    save_json_atomic(data, path)
    return True


def is_valid_json(path: Path, match_id: str, data_type: str) -> bool:
    """Vérifie l'intégrité minimale d'un JSON Riot."""

    if not path.is_file():
        return False

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        validate_payload(data, match_id, data_type)
        return True

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
            delete=False,
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
        ("match", DATA_DIR / "matches" / f"{match_id}.json", client.get_match),
        ("timeline", DATA_DIR / "timelines" / f"{match_id}.json", client.get_timeline),
    )

    for data_type, path, _fetch in targets:
        if not extract_payload(client, match_id, data_type, path):
            print(f"SKIP {data_type} : {match_id}")
            continue
        print(f"Sauvegardé : {path}")
