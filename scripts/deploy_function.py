"""Déploie le MVP Functions Flex en réutilisant le stockage RAW existant."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import dotenv_values

from scripts.package_function import ROOT, package


def az(*args):
    result = subprocess.run(
        ["az", *args, "--only-show-errors", "-o", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        # Ne pas réimprimer les sorties de commandes manipulant des secrets.
        raise RuntimeError(
            f"Azure CLI a échoué : {' '.join(args[:3])}. Consulter les journaux Azure CLI locaux."
        )
    return json.loads(result.stdout) if result.stdout.strip() else None


def deploy(app_name, group, location, host_storage):
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    required = ("RIOT_API_KEY", "RIOT_GAME_NAME", "RIOT_TAG_LINE", "AZURE_STORAGE_ACCOUNT_NAME")
    if any(not values.get(key) for key in required):
        raise ValueError("Configurer les variables Riot et Azure dans .env avant le déploiement")
    account = az("account", "show")
    subscription = account["id"]
    prefix = f"/subscriptions/{subscription}/resourceGroups/{group}"
    resources = az("resource", "list", "-g", group)
    names = {r["name"] for r in resources}
    if host_storage not in names:
        print("Création du stockage interne Functions", flush=True)
        az(
            "storage",
            "account",
            "create",
            "-g",
            group,
            "-n",
            host_storage,
            "-l",
            location,
            "--sku",
            "Standard_LRS",
            "--kind",
            "StorageV2",
            "--allow-blob-public-access",
            "false",
            "--min-tls-version",
            "TLS1_2",
        )
    if app_name not in names:
        print("Création de la Function App Flex et de sa supervision", flush=True)
        az(
            "functionapp",
            "create",
            "-g",
            group,
            "-n",
            app_name,
            "--storage-account",
            host_storage,
            "--flexconsumption-location",
            location,
            "--runtime",
            "python",
            "--runtime-version",
            "3.12",
            "--functions-version",
            "4",
            "--instance-memory",
            "512",
            "--maximum-instance-count",
            "40",
            "--https-only",
            "true",
        )
    print("Configuration de l'identité managée et du rôle Blob", flush=True)
    identity = az("functionapp", "identity", "assign", "-g", group, "-n", app_name)
    raw_account = values["AZURE_STORAGE_ACCOUNT_NAME"]
    container = values.get("AZURE_STORAGE_CONTAINER_NAME", "riot-raw")
    scope = (
        f"{prefix}/providers/Microsoft.Storage/storageAccounts/{raw_account}"
        f"/blobServices/default/containers/{container}"
    )
    az(
        "role",
        "assignment",
        "create",
        "--assignee-object-id",
        identity["principalId"],
        "--assignee-principal-type",
        "ServicePrincipal",
        "--role",
        "Storage Blob Data Contributor",
        "--scope",
        scope,
    )
    with TemporaryDirectory(prefix="riftlab-deploy-") as directory:
        settings = {key: values[key] for key in required}
        settings.update(
            {
                "RIOT_REGION": values.get("RIOT_REGION", "europe"),
                "AZURE_STORAGE_CONTAINER_NAME": container,
            }
        )
        settings_path = Path(directory) / "settings.json"
        settings_path.touch(mode=0o600)
        settings_path.write_text(json.dumps(settings))
        print("Transfert des paramètres d'application sans affichage des secrets", flush=True)
        az(
            "functionapp",
            "config",
            "appsettings",
            "set",
            "-g",
            group,
            "-n",
            app_name,
            "--settings",
            f"@{settings_path}",
        )
        archive = Path(directory) / "function.zip"
        package(archive)
        print("Déploiement du code avec compilation distante Linux", flush=True)
        az(
            "functionapp",
            "deployment",
            "source",
            "config-zip",
            "-g",
            group,
            "-n",
            app_name,
            "--src",
            str(archive),
            "--build-remote",
            "true",
        )
    print("Déploiement terminé", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--host-storage", required=True)
    parser.add_argument("--resource-group", default="rg-riftlab-dev")
    parser.add_argument("--location", default="francecentral")
    options = parser.parse_args()
    deploy(options.app_name, options.resource_group, options.location, options.host_storage)
