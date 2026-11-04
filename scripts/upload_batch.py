import logging
from pathlib import Path

from azure.core.exceptions import AzureError

from ingestion.blob_storage import BlobStorage
from ingestion.extract_matches import is_valid_json

DATA_DIR = Path("data")


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("azure").setLevel(logging.WARNING)

    storage = BlobStorage()

    stats = {
        "uploaded": 0,
        "skipped": 0,
        "invalid": 0,
        "failed": 0,
    }

    for data_type, folder in (
        ("match", "matches"),
        ("timeline", "timelines"),
    ):
        directory = DATA_DIR / folder

        if not directory.is_dir():
            raise FileNotFoundError(directory)

        for path in sorted(directory.glob("*.json")):
            match_id = path.stem
            blob_name = f"{folder}/{path.name}"

            if not is_valid_json(path, match_id, data_type):
                logging.error("JSON invalide : %s", path)
                stats["invalid"] += 1
                continue

            try:
                uploaded = storage.upload_file(
                    local_path=path,
                    blob_name=blob_name,
                )

                if uploaded:
                    stats["uploaded"] += 1
                else:
                    stats["skipped"] += 1

            except (AzureError, OSError, ValueError) as error:
                stats["failed"] += 1
                logging.error(
                    "Échec upload %s : %s",
                    blob_name,
                    error,
                )

    print("\n===== BILAN AZURE BLOB STORAGE =====")
    print(f"Fichiers uploadés : {stats['uploaded']}")
    print(f"Fichiers ignorés : {stats['skipped']}")
    print(f"JSON invalides : {stats['invalid']}")
    print(f"Échecs : {stats['failed']}")

    return 1 if stats["failed"] or stats["invalid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
