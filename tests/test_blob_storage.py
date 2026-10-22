from unittest.mock import Mock

import pytest
from azure.core.exceptions import ResourceExistsError

from ingestion.blob_storage import BlobStorage


@pytest.mark.parametrize("identical", [True, False])
def test_existing_blob_is_verified_before_skip(tmp_path, identical):
    path = tmp_path / "match.json"
    path.write_bytes(b'{"match": 1}')
    storage = BlobStorage.__new__(BlobStorage)
    storage.container = Mock()
    storage.container.upload_blob.side_effect = ResourceExistsError("exists")
    storage.container.download_blob.return_value.readall.return_value = (
        path.read_bytes() if identical else b'{"match": 2}'
    )

    if identical:
        assert storage.upload_file(path, "matches/match.json") is False
    else:
        with pytest.raises(ValueError, match="Contenu Azure différent"):
            storage.upload_file(path, "matches/match.json")

    assert storage.container.upload_blob.call_count == 1
    assert storage.container.upload_blob.call_args.kwargs["overwrite"] is False
    storage.container.download_blob.assert_called_once_with("matches/match.json")
