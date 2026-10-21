
import json

from ingestion.extract_matches import is_valid_json
from ingestion.extract_matches import save_json_atomic

def test_valid_match_json(tmp_path):
    path = tmp_path / "match.json"

    data = {
        "metadata": {"matchId": "EUW1_123"},
        "info": {"participants": [{"puuid": "test"}]}
    }

    path.write_text(json.dumps(data), encoding="utf-8")

    assert is_valid_json(
        path, "EUW1_123", "match"
    ) is True


def test_corrupted_json(tmp_path):
    path = tmp_path / "match.json"
    path.write_text("{invalid json", encoding="utf-8")

    assert is_valid_json(
        path, "EUW1_123", "match"
    ) is False


def test_wrong_match_id(tmp_path):
    path = tmp_path / "match.json"

    data = {
        "metadata": {"matchId": "EUW1_999"},
        "info": {"participants": [{"puuid": "test"}]}
    }

    path.write_text(json.dumps(data), encoding="utf-8")

    assert is_valid_json(
        path, "EUW1_123", "match"
    ) is False



def test_save_json_atomic(tmp_path):
    """Vérifie la sauvegarde et le remplacement atomique."""

    path = tmp_path / "match.json"

    original_data = {
        "metadata": {"matchId": "EUW1_123"},
        "info": {"participants": [{"puuid": "player1"}]}
    }

    save_json_atomic(original_data, path)

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == original_data

    updated_data = {
        "metadata": {"matchId": "EUW1_123"},
        "info": {"participants": [{"puuid": "player2"}]}
    }

    save_json_atomic(updated_data, path)

    assert json.loads(path.read_text(encoding="utf-8")) == updated_data

    # Aucun fichier temporaire ne doit subsister
    assert list(tmp_path.glob("*.tmp")) == []
