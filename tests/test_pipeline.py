import hashlib
import json
import logging
from unittest.mock import Mock

import pytest
import requests

from ingestion.pipeline import run_pipeline


class MemoryStorage:
    """Stockage de test conservé entre runs, sans réseau ni secrets."""

    def __init__(self):
        self.blobs = {}

    def upload_file(self, path, name):
        content = path.read_bytes()
        if name in self.blobs:
            if self.blobs[name] != content:
                raise ValueError("different content")
            return False
        self.blobs[name] = content
        return True

    def verify_file(self, path, name):
        assert path.read_bytes() == self.blobs[name]
        return hashlib.sha256(self.blobs[name]).hexdigest()


def client_for_match():
    client = Mock()
    client.get_account.return_value = {"puuid": "private-puuid"}
    client.get_all_match_ids.return_value = ["EUW1_123", "EUW1_123"]
    client.get_match.return_value = {
        "metadata": {"matchId": "EUW1_123"},
        "info": {"participants": [{}]},
    }
    client.get_timeline.return_value = {
        "metadata": {"matchId": "EUW1_123"},
        "info": {"frames": [{}]},
    }
    return client


def assert_counts(report):
    for kind in ("match", "timeline"):
        assert sum(report["counts"][kind].values()) == report["discovered"]


def test_nominal_and_replay(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="riftlab.ingestion")
    storage, client = MemoryStorage(), client_for_match()
    first = run_pipeline(storage, client, data_dir=tmp_path)
    second = run_pipeline(storage, client, data_dir=tmp_path)
    assert first["status"] == second["status"] == "SUCCESS"
    assert first["run_id"] != second["run_id"]
    for kind in ("match", "timeline"):
        assert first["counts"][kind]["written"] == 1
        assert second["counts"][kind]["skipped"] == 1
    client.get_match.assert_called_once()
    client.get_timeline.assert_called_once()
    assert len(storage.blobs) == 4  # deux payloads + deux manifests
    for report in (first, second):
        assert_counts(report)
        saved = json.loads(storage.blobs[f"manifests/run_id={report['run_id']}/manifest.json"])
        assert saved == report
    assert "private-puuid" not in caplog.text
    for record in caplog.records:
        assert json.loads(record.message)["run_id"] in (first["run_id"], second["run_id"])


def test_interruption_and_resume(tmp_path):
    storage, client = MemoryStorage(), client_for_match()
    client.get_timeline.side_effect = KeyboardInterrupt
    first = run_pipeline(storage, client, data_dir=tmp_path)
    assert first["status"] == "PARTIAL_SUCCESS"
    assert first["interrupted"] is True
    assert first["counts"]["match"]["written"] == 1
    assert first["counts"]["timeline"]["not_processed"] == 1
    assert_counts(first)

    client.get_timeline.side_effect = None
    resumed = run_pipeline(storage, client, data_dir=tmp_path)
    assert resumed["status"] == "SUCCESS"
    assert resumed["counts"]["match"]["skipped"] == 1
    assert resumed["counts"]["timeline"]["written"] == 1
    client.get_match.assert_called_once()


@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_auth_or_exhausted_quota_stops_batch(tmp_path, status_code):
    client = client_for_match()
    response = requests.Response()
    response.status_code = status_code
    client.get_match.side_effect = requests.HTTPError("secret", response=response)
    report = run_pipeline(MemoryStorage(), client, data_dir=tmp_path)
    assert report["status"] == "FAILED"
    assert report["counts"]["match"]["failed"] == 1
    assert report["counts"]["timeline"]["not_processed"] == 1
    client.get_timeline.assert_not_called()
    assert "secret" not in json.dumps(report)
    assert_counts(report)


def test_invalid_payload_not_saved_or_uploaded(tmp_path):
    client, storage = client_for_match(), MemoryStorage()
    client.get_timeline.return_value["info"]["frames"] = []
    report = run_pipeline(storage, client, data_dir=tmp_path)
    assert report["status"] == "PARTIAL_SUCCESS"
    assert report["counts"]["timeline"]["failed"] == 1
    assert not (tmp_path / "timelines" / "EUW1_123.json").exists()
    assert "timelines/EUW1_123.json" not in storage.blobs
    assert_counts(report)


def test_manifest_upload_failure_is_not_success(tmp_path):
    storage = MemoryStorage()
    original = storage.upload_file

    def upload(path, name):
        if name.startswith("manifests/"):
            raise OSError("sensitive details")
        return original(path, name)

    storage.upload_file = upload
    report = run_pipeline(storage, client_for_match(), data_dir=tmp_path)
    assert report["status"] == "FAILED"
    assert report["failures"][-1]["stage"] == "manifest_publish"
    local = json.loads((tmp_path / "manifests" / report["run_id"] / "manifest.json").read_text())
    assert local == report


def test_discovery_failure_has_manifest(tmp_path):
    client, storage = client_for_match(), MemoryStorage()
    client.get_account.side_effect = requests.Timeout("secret")
    report = run_pipeline(storage, client, data_dir=tmp_path)
    assert report["status"] == "FAILED"
    assert report["discovered"] == 0
    assert len(storage.blobs) == 1
    assert_counts(report)


def test_existing_different_blob_is_preserved(tmp_path):
    storage = MemoryStorage()
    storage.blobs["matches/EUW1_123.json"] = b"different"
    report = run_pipeline(storage, client_for_match(), data_dir=tmp_path)
    assert report["status"] == "PARTIAL_SUCCESS"
    assert report["counts"]["match"]["failed"] == 1
    assert report["failures"][0]["stage"] == "upload"
    assert storage.blobs["matches/EUW1_123.json"] == b"different"
    assert_counts(report)


def test_cli_resumes_exact_batch_without_discovery(tmp_path, monkeypatch):
    import run_pipeline as cli

    monkeypatch.chdir(tmp_path)
    storage, client = MemoryStorage(), client_for_match()
    client.get_timeline.side_effect = KeyboardInterrupt
    first = run_pipeline(storage, client, data_dir=tmp_path / "data")
    client.get_timeline.side_effect = None
    client.get_account.reset_mock()
    client.get_all_match_ids.reset_mock()
    monkeypatch.setattr(cli, "BlobStorage", lambda: storage)
    monkeypatch.setattr(cli, "RiotClient", lambda: client)
    manifest = tmp_path / "data" / "manifests" / first["run_id"] / "manifest.json"
    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--resume-manifest", str(manifest)])
    assert cli.main() == 0
    client.get_account.assert_not_called()
    client.get_all_match_ids.assert_not_called()
    client.get_match.assert_called_once()
