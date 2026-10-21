
from unittest.mock import Mock, patch

from ingestion.riot_client import RiotClient


def test_retry_on_429():
    """Vérifie le retry après une réponse HTTP 429."""

    client = RiotClient()

    response_429 = Mock()
    response_429.status_code = 429
    response_429.headers = {"Retry-After": "1"}

    response_200 = Mock()
    response_200.status_code = 200
    response_200.json.return_value = {
        "status": "success"
    }

    with patch.object(
        client.session,
        "get",
        side_effect=[response_429, response_200]
    ) as mock_get:
        with patch.object(client, "_wait_for_rate_limit"):
            with patch(
                "ingestion.riot_client.time.sleep"
            ) as mock_sleep:
                result = client._get("/test")

    assert result == {"status": "success"}
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(1.0)


def test_rate_limiting():
    """Vérifie l'espacement minimal des requêtes."""

    client = RiotClient()
    client.min_request_interval = 1.5

    with patch(
        "ingestion.riot_client.time.monotonic"
    ) as clock:
        with patch(
            "ingestion.riot_client.time.sleep"
        ) as sleep:

            clock.side_effect = [
                100.0,
                100.0,
                100.5,
                101.5
            ]

            client._wait_for_rate_limit()
            client._wait_for_rate_limit()

    sleep.assert_called_once_with(1.0)
