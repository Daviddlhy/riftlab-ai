"""Pipeline séquentiel réutilisable : Riot, fichiers locaux, Blob, manifest."""

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import requests
from azure.core.exceptions import AzureError

from ingestion.extract_matches import extract_payload, save_json_atomic
from ingestion.observability import emit


def run_pipeline(
    storage,
    client=None,
    *,
    game_name=None,
    tag_line=None,
    match_ids=None,
    max_matches=50,
    data_dir=Path("data"),
) -> dict:
    """Chaque endpoint a une issue : written, skipped, failed ou not_processed.

    Un nouveau run reprend les objets validés, sans réutiliser un ancien manifest.
    Une interruption brutale peut laisser le checkpoint local à RUNNING.
    """
    data_dir = Path(data_dir)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex
    manifest_path = data_dir / "manifests" / run_id / "manifest.json"
    manifest_blob = f"manifests/run_id={run_id}/manifest.json"
    started = time.monotonic()
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "RUNNING",
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "discovered": 0,
        "operations": [],
        "failures": [],
        "counts": {},
        "interrupted": False,
    }

    def checkpoint():
        report["counts"] = {
            kind: {
                status: sum(
                    o["kind"] == kind and o["status"] == status for o in report["operations"]
                )
                for status in ("written", "skipped", "failed", "not_processed")
            }
            for kind in ("match", "timeline")
        }
        save_json_atomic(report, manifest_path)

    checkpoint()
    emit("run_started", run_id)
    run_stage = "discovery"
    try:
        if client is not None:
            client.run_id = run_id
        if match_ids is None:
            account = client.get_account(game_name=game_name, tag_line=tag_line)
            match_ids = client.get_all_match_ids(
                puuid=account["puuid"], max_matches=max_matches, page_size=20, queue=420
            )
        ids = list(dict.fromkeys(match_ids))
        if not ids or any(not re.fullmatch(r"[A-Z0-9]+_[0-9]+", mid) for mid in ids):
            raise ValueError("Empty or invalid match IDs")
        report["discovered"] = len(ids)
        report["operations"] = [
            {
                "match_id": mid,
                "kind": kind,
                "blob": f"{folder}/{mid}.json",
                "status": "not_processed",
            }
            for mid in ids
            for kind, folder in (("match", "matches"), ("timeline", "timelines"))
        ]
        checkpoint()
        run_stage = "processing"
        for operation in report["operations"]:
            mid, kind = operation["match_id"], operation["kind"]
            path = data_dir / operation["blob"]
            stage = "extract"
            operation_started = time.monotonic()
            stop = False
            error_fields = {}
            try:
                fetched = extract_payload(client, mid, kind, path)
                operation["local_status"] = "written" if fetched else "reused"
                stage = "upload"
                written = storage.upload_file(path, operation["blob"])
                stage = "verify"
                operation["sha256"] = storage.verify_file(path, operation["blob"])
                operation["status"] = "written" if written else "skipped"
            except (requests.RequestException, AzureError, OSError, ValueError, KeyError) as error:
                operation["status"] = "failed"
                failure = {
                    "match_id": mid,
                    "kind": kind,
                    "stage": stage,
                    "reason": type(error).__name__,
                }
                if isinstance(error, requests.HTTPError) and error.response is not None:
                    failure["status_code"] = error.response.status_code
                    stop = error.response.status_code in (401, 403, 429)
                report["failures"].append(failure)
                error_fields = {k: v for k, v in failure.items() if k in ("reason", "status_code")}
            operation["duration_ms"] = round((time.monotonic() - operation_started) * 1000)
            emit(
                f"{kind}_{operation['status']}",
                run_id,
                match_id=mid,
                stage=stage,
                status=operation["status"],
                duration_ms=operation["duration_ms"],
                **error_fields,
            )
            checkpoint()
            if stop:
                break
    except KeyboardInterrupt:
        report["interrupted"] = True
        report["failures"].append({"stage": "run", "reason": "KeyboardInterrupt"})
    except Exception as error:
        # Conserver la preuve locale même si la découverte ou le code échoue.
        failure = {"stage": run_stage, "reason": type(error).__name__}
        if isinstance(error, requests.HTTPError) and error.response is not None:
            failure["status_code"] = error.response.status_code
        report["failures"].append(failure)
        emit("run_failed", run_id, **failure)

    completed = sum(o["status"] in ("written", "skipped") for o in report["operations"])
    incomplete = any(o["status"] in ("failed", "not_processed") for o in report["operations"])
    report["status"] = (
        ("PARTIAL_SUCCESS" if completed else "FAILED")
        if report["failures"] or incomplete
        else "SUCCESS"
    )
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["duration_ms"] = round((time.monotonic() - started) * 1000)
    checkpoint()
    try:
        storage.upload_file(manifest_path, manifest_blob)
        storage.verify_file(manifest_path, manifest_blob)
        emit("manifest_saved", run_id, status=report["status"], blob=manifest_blob)
    except Exception as error:
        # Le résultat distant peut être absent ou indéterminé : le local fait foi.
        report["status"] = "FAILED"
        report["failures"].append({"stage": "manifest_publish", "reason": type(error).__name__})
        checkpoint()
        emit("manifest_publish_failed", run_id, reason=type(error).__name__)
    emit("run_finished", run_id, status=report["status"], duration_ms=report["duration_ms"])
    return report
