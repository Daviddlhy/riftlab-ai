"""Audit en lecture seule : inventaire, JSON locaux et intégrité des blobs."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from azure.core.exceptions import AzureError

from ingestion.blob_storage import BlobStorage
from ingestion.extract_matches import is_valid_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    storage = BlobStorage()
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "container": storage.container.container_name,
        "public_access": storage.container.get_container_properties().get("public_access"),
        "files": [],
        "errors": [],
    }
    if report["public_access"]:
        report["errors"].append("Accès public activé sur le conteneur")

    inventories = {}
    for kind, folder in (("match", "matches"), ("timeline", "timelines")):
        paths = sorted((Path("data") / folder).glob("*.json"))
        inventories[folder] = {p.stem for p in paths}
        expected = {f"{folder}/{p.name}" for p in paths}
        actual = {b.name for b in storage.container.list_blobs(name_starts_with=f"{folder}/")}
        if not paths:
            report["errors"].append(f"Aucun fichier local : {folder}")
        for name in sorted(actual - expected):
            report["errors"].append(f"Blob sans fichier local correspondant : {name}")
        for path in paths:
            name = f"{folder}/{path.name}"
            if not is_valid_json(path, path.stem, kind):
                report["errors"].append(f"JSON local invalide : {name}")
                continue
            if name not in actual:
                report["errors"].append(f"Blob manquant : {name}")
                continue
            try:
                digest = storage.verify_file(path, name)
                report["files"].append({"blob": name, "sha256": digest})
            except (AzureError, OSError, ValueError) as error:
                report["errors"].append(f"{name}: {error}")

    if inventories["matches"] != inventories["timelines"]:
        report["errors"].append("Les matchs et timelines locaux ne sont pas appariés")
    report["status"] = "FAILED" if report["errors"] else "SUCCESS"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        f"{report['status']} : {len(report['files'])} fichiers identiques, "
        f"{len(report['errors'])} erreurs"
    )
    print(f"Rapport : {args.report}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
