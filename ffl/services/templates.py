import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from ffl.domain.models import SignalTemplate
from ffl.persistence import repository


def publish_signal_template(
    conn: sqlite3.Connection, name: str, version: int, fields: List[Dict[str, Any]], owner_id: str
) -> SignalTemplate:
    """Publish an immutable, versioned signal template."""
    published_at = datetime.now(timezone.utc).isoformat()
    return repository.create_signal_template(
        conn, name, version, "published", json.dumps(fields), owner_id, published_at
    )


def validate_signal_payload(template: SignalTemplate, payload: dict) -> dict:
    """Validate a signal payload and retain only fields declared by its template."""
    validated = {}
    for field in template.fields:
        key = field["key"]
        if field.get("required") and key not in payload:
            raise ValueError("{0} is required".format(key))
        if key not in payload:
            continue
        value = payload[key]
        if field.get("type") == "choice" and value not in field.get("options", []):
            raise ValueError("{0} must be one of {1}".format(key, field.get("options", [])))
        validated[key] = value
    return validated
