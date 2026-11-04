"""Lancement manuel protégé, traitement asynchrone et consultation du résultat."""

import json
import logging
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError

from ingestion.blob_storage import BlobStorage
from ingestion.extract_matches import save_json_atomic
from ingestion.observability import emit
from ingestion.pipeline import run_pipeline
from ingestion.riot_client import RiotClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
QUEUE_NAME = "riftlab-ingestion"


def response(body, status=200):
    return func.HttpResponse(json.dumps(body), status_code=status, mimetype="application/json")


def validate_request(payload):
    if not isinstance(payload, dict):
        raise ValueError("Expected an object")
    count = payload.get("max_matches", 3)
    if type(count) is not int or not 1 <= count <= 50:
        raise ValueError("max_matches must be an integer between 1 and 50")
    return count


@app.route(route="ingestion", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
@app.queue_output(arg_name="job", queue_name=QUEUE_NAME, connection="AzureWebJobsStorage")
def start_ingestion(req: func.HttpRequest, job: func.Out[str]) -> func.HttpResponse:
    try:
        count = validate_request(req.get_json())
    except ValueError:
        return response(
            {"error": "Un objet JSON avec max_matches entier entre 1 et 50 est requis"}, 400
        )
    request_id = uuid4().hex
    job.set(json.dumps({"request_id": request_id, "max_matches": count}))
    return response(
        {
            "request_id": request_id,
            "status": "QUEUED",
            "status_path": f"/api/ingestion/{request_id}",
        },
        202,
    )


@app.route(route="ingestion/{request_id}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def ingestion_status(req: func.HttpRequest) -> func.HttpResponse:
    request_id = req.route_params.get("request_id", "")
    if not re.fullmatch(r"[a-f0-9]{32}", request_id):
        return response({"error": "request_id invalide"}, 400)
    try:
        data = BlobStorage().container.download_blob(f"requests/{request_id}.json").readall()
        return response(json.loads(data))
    except ResourceNotFoundError:
        # Un ID inconnu est indiscernable d'une demande encore en attente.
        return response({"request_id": request_id, "status": "PENDING_OR_UNKNOWN"}, 202)
    except Exception:
        return response({"error": "Lecture du résultat indisponible"}, 503)


@app.queue_trigger(arg_name="message", queue_name=QUEUE_NAME, connection="AzureWebJobsStorage")
def ingest_worker(message: func.QueueMessage) -> None:
    logging.getLogger("azure").setLevel(logging.WARNING)
    payload = json.loads(message.get_body().decode())
    count = validate_request(payload)
    request_id = payload["request_id"]
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("Invalid request_id")
    storage = BlobStorage()
    result_blob = f"requests/{request_id}.json"
    try:
        # Une demande déjà terminée ne relance pas la collecte après redelivery.
        storage.container.get_blob_client(result_blob).get_blob_properties()
        return
    except ResourceNotFoundError:
        pass
    with TemporaryDirectory(prefix="riftlab-") as directory:
        try:
            report = run_pipeline(
                storage,
                RiotClient(),
                game_name=os.environ["RIOT_GAME_NAME"],
                tag_line=os.environ["RIOT_TAG_LINE"],
                max_matches=count,
                data_dir=Path(directory),
                request_id=request_id,
            )
            result = {
                "request_id": request_id,
                "run_id": report["run_id"],
                "status": report["status"],
                "counts": report["counts"],
                "failures": report["failures"],
                "manifest_blob": f"manifests/run_id={report['run_id']}/manifest.json",
            }
        except Exception as error:
            result = {"request_id": request_id, "status": "FAILED", "reason": type(error).__name__}
            emit("cloud_request_failed", request_id, reason=type(error).__name__)
        path = Path(directory) / "result.json"
        save_json_atomic(result, path)
        storage.upload_file(path, result_blob)
        storage.verify_file(path, result_blob)
        emit(
            "cloud_request_finished",
            result.get("run_id", request_id),
            request_id=request_id,
            status=result["status"],
        )
