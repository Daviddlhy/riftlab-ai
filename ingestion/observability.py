"""Événements JSON sans payload ni message d'exception potentiellement sensible."""

import json
import logging
from datetime import UTC, datetime


def emit(event: str, run_id: str, **fields) -> None:
    logging.getLogger("riftlab.ingestion").info(
        json.dumps(
            {"timestamp": datetime.now(UTC).isoformat(), "event": event, "run_id": run_id, **fields}
        )
    )
