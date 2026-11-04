"""Déclenche une collecte cloud et attend le résultat sans afficher de clé Functions."""

import argparse
import json
import time

import requests

from scripts.deploy_function import az


def invoke(app_name, group, count, wait_seconds):
    app = az("functionapp", "show", "-g", group, "-n", app_name)
    keys = az("functionapp", "keys", "list", "-g", group, "-n", app_name)
    details = app.get("properties", app)
    base = f"https://{details['defaultHostName']}"
    headers = {"x-functions-key": keys["functionKeys"]["default"]}
    unsigned = requests.post(f"{base}/api/ingestion", json={"max_matches": count}, timeout=60)
    if unsigned.status_code != 401:
        raise RuntimeError(f"Contrôle d'accès inattendu : HTTP {unsigned.status_code}")
    result = requests.post(
        f"{base}/api/ingestion", headers=headers, json={"max_matches": count}, timeout=60
    )
    if result.status_code != 202:
        raise RuntimeError(f"Lancement refusé : HTTP {result.status_code}")
    job = result.json()
    print(f"Requête acceptée : {job['request_id']} ; appel sans clé refusé (401)", flush=True)
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        status = requests.get(f"{base}{job['status_path']}", headers=headers, timeout=60)
        if status.status_code == 200:
            report = status.json()
            print(json.dumps(report, indent=2), flush=True)
            return 0 if report["status"] == "SUCCESS" else 1
        if status.status_code != 202:
            raise RuntimeError(f"Consultation refusée : HTTP {status.status_code}")
        time.sleep(5)
    raise TimeoutError(f"Résultat encore en attente pour {job['request_id']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--resource-group", default="rg-riftlab-dev")
    parser.add_argument("--max-matches", type=int, default=3)
    parser.add_argument("--wait-seconds", type=int, default=240)
    options = parser.parse_args()
    if not 1 <= options.max_matches <= 50:
        parser.error("--max-matches doit être entre 1 et 50")
    raise SystemExit(
        invoke(options.app_name, options.resource_group, options.max_matches, options.wait_seconds)
    )
