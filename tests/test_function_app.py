import json
from unittest.mock import Mock

import azure.functions as func
import pytest
from azure.core.exceptions import ResourceNotFoundError

import function_app as cloud


def user_function(name):
    return getattr(cloud, name).build().get_user_function()


@pytest.mark.parametrize(
    "body",
    [{"max_matches": 0}, {"max_matches": 51}, {"max_matches": True}, {"max_matches": "3"}, []],
)
def test_invalid_job_not_queued(body):
    request = func.HttpRequest("POST", "/api/ingestion", body=json.dumps(body).encode())
    queue = Mock()
    assert user_function("start_ingestion")(request, queue).status_code == 400
    queue.set.assert_not_called()


def test_routes_require_function_auth_and_return_async_job():
    for name in ("start_ingestion", "ingestion_status"):
        bindings = getattr(cloud, name).build().get_bindings_dict()["bindings"]
        trigger = next(b for b in bindings if b["type"] == "httpTrigger")
        assert trigger["authLevel"] == func.AuthLevel.FUNCTION
    request = func.HttpRequest("POST", "/api/ingestion", body=b'{"max_matches": 3}')
    queue = Mock()
    result = user_function("start_ingestion")(request, queue)
    assert result.status_code == 202
    queued = json.loads(queue.set.call_args.args[0])
    assert queued["request_id"] == json.loads(result.get_body())["request_id"]
    assert queued["max_matches"] == 3


def test_worker_publishes_correlated_result_and_uses_temporary_directory(monkeypatch):
    storage = Mock()
    storage.container.get_blob_client.return_value.get_blob_properties.side_effect = (
        ResourceNotFoundError("missing")
    )
    monkeypatch.setattr(cloud, "BlobStorage", lambda: storage)
    monkeypatch.setattr(cloud, "RiotClient", Mock())
    monkeypatch.setenv("RIOT_GAME_NAME", "private")
    monkeypatch.setenv("RIOT_TAG_LINE", "private")
    pipeline = Mock(
        return_value={"run_id": "run-test", "status": "SUCCESS", "counts": {}, "failures": []}
    )
    monkeypatch.setattr(cloud, "run_pipeline", pipeline)
    request_id = "a" * 32
    message = Mock()
    message.get_body.return_value = json.dumps(
        {"request_id": request_id, "max_matches": 3}
    ).encode()
    user_function("ingest_worker")(message)
    options = pipeline.call_args.kwargs
    assert options["request_id"] == request_id
    assert not options["data_dir"].exists()  # Nettoyage même après publication
    assert storage.upload_file.call_args.args[1] == f"requests/{request_id}.json"


def test_managed_identity_selected_in_azure(monkeypatch):
    import ingestion.blob_storage as module

    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://identity")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "example")
    credential, sdk = Mock(), Mock()
    monkeypatch.setattr(module, "ManagedIdentityCredential", credential)
    monkeypatch.setattr(module, "BlobServiceClient", sdk)
    module.BlobStorage()
    credential.assert_called_once_with()
    assert sdk.call_args.kwargs["credential"] == credential.return_value


def test_completed_request_is_not_processed_twice(monkeypatch):
    storage, pipeline = Mock(), Mock()
    monkeypatch.setattr(cloud, "BlobStorage", lambda: storage)
    monkeypatch.setattr(cloud, "run_pipeline", pipeline)
    message = Mock()
    message.get_body.return_value = json.dumps({"request_id": "b" * 32, "max_matches": 3}).encode()
    user_function("ingest_worker")(message)
    pipeline.assert_not_called()
    storage.upload_file.assert_not_called()


def test_worker_initialization_error_publishes_failure_without_secret(monkeypatch):
    storage = Mock()
    storage.container.get_blob_client.return_value.get_blob_properties.side_effect = (
        ResourceNotFoundError("missing")
    )
    monkeypatch.setattr(cloud, "BlobStorage", lambda: storage)
    monkeypatch.setattr(cloud, "RiotClient", Mock(side_effect=ValueError("private secret")))
    summaries = []
    storage.upload_file.side_effect = lambda path, name: summaries.append(
        json.loads(path.read_text())
    )
    message = Mock()
    message.get_body.return_value = json.dumps({"request_id": "c" * 32, "max_matches": 3}).encode()
    user_function("ingest_worker")(message)
    assert summaries[0]["status"] == "FAILED"
    assert summaries[0]["reason"] == "ValueError"
    assert "private secret" not in json.dumps(summaries[0])


def test_package_contains_only_runtime_sources(tmp_path):
    from zipfile import ZipFile

    from scripts.package_function import package

    destination = tmp_path / "function.zip"
    package(destination)
    with ZipFile(destination) as archive:
        names = archive.namelist()
    assert {"host.json", "function_app.py", "requirements.txt"} <= set(names)
    assert all(
        n in {"host.json", "function_app.py", "requirements.txt"}
        or (n.startswith("ingestion/") and n.endswith(".py"))
        for n in names
    )


def test_invocation_accepts_arm_envelope_without_exposing_key(monkeypatch, capsys):
    from scripts import invoke_function as cli

    monkeypatch.setattr(
        cli,
        "az",
        Mock(
            side_effect=[
                {"properties": {"defaultHostName": "example.azurewebsites.net"}},
                {"functionKeys": {"default": "private-key"}},
            ]
        ),
    )
    unsigned = Mock(status_code=401)
    accepted = Mock(status_code=202)
    accepted.json.return_value = {
        "request_id": "test-request",
        "status_path": "/api/ingestion/test",
    }
    post = Mock(side_effect=[unsigned, accepted])
    monkeypatch.setattr(cli.requests, "post", post)
    done = Mock(status_code=200)
    done.json.return_value = {"status": "SUCCESS"}
    monkeypatch.setattr(cli.requests, "get", Mock(return_value=done))
    assert cli.invoke("app", "group", 3, 10) == 0
    assert "headers" not in post.call_args_list[0].kwargs
    assert post.call_args_list[1].kwargs["headers"]["x-functions-key"] == "private-key"
    assert "private-key" not in capsys.readouterr().out
