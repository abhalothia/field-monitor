"""Private, schedulable communications maintenance worker.

This module is deliberately a local command, not an HTTP route.  It consumes
sealed receipts, retains authenticated provider media as FFL evidence, and
reconciles ambiguous outbound sends without issuing a resend.
"""

import argparse
import json
import os
import sys
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import httpx

from ffl.communications.loopmessage import LoopMessageProvider
from ffl.communications.service import (
    process_pending_communication_media,
    process_pending_communications,
    reconcile_outbound_messages,
)
from ffl.config import FFL_DATABASE_PATH
from ffl.communications import persistence
from ffl.persistence.database import database_target, open_connection
from ffl.persistence.schema import create_schema


AlertSender = Callable[[Dict[str, Any]], None]


def run_once(conn, provider, receipt_key: str, alert_sender: Optional[AlertSender] = None) -> Dict[str, int]:
    if not receipt_key:
        raise ValueError("FFL_COMMUNICATION_RECEIPT_KEY is required for the communications worker")
    receipts = process_pending_communications(conn, provider, receipt_key)
    media = process_pending_communication_media(conn, provider, receipt_key)
    reconciled = reconcile_outbound_messages(conn, provider)
    health = persistence.health(conn)
    result = {
        "receipts_processed": receipts,
        "media_retained": media["retained"],
        "media_retryable": media["retryable"],
        "media_failed": media["failed"],
        "outbounds_reconciled": reconciled,
        "unknown_delivery_count": health["unknown_delivery_count"],
        "retryable_receipt_count": health["retryable_receipt_count"],
        "failed_media_count": health["failed_media_count"],
    }
    if _needs_alert(result) and alert_sender is not None:
        # Intentionally no contact, message, URL, or error text is emitted.
        alert_sender({"service": "ffl-communications-worker", "state": "attention", **result})
    return result


def _needs_alert(result: Dict[str, int]) -> bool:
    return any(result[key] > 0 for key in ("unknown_delivery_count", "retryable_receipt_count", "failed_media_count"))


def _configured_alert_sender() -> Optional[AlertSender]:
    url = os.environ.get("FFL_COMMUNICATION_ALERT_WEBHOOK_URL")
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("FFL_COMMUNICATION_ALERT_WEBHOOK_URL must be an HTTPS URL without credentials")
    authorization = os.environ.get("FFL_COMMUNICATION_ALERT_AUTHORIZATION")

    def send(payload: Dict[str, Any]) -> None:
        headers = {"Authorization": authorization} if authorization else None
        response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        response.raise_for_status()

    return send


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run one private FFL communications maintenance cycle")
    parser.add_argument("--once", action="store_true", help="Run one bounded cycle (the only supported mode)")
    parser.parse_args(argv)
    # Use the same target resolver as the API.  If a future production DSN is
    # set before its repository adapter exists, fail closed rather than letting
    # this worker quietly process private communications in a local SQLite DB.
    conn = open_connection(
        database_target(sqlite_path=os.environ.get("FFL_DATABASE_PATH", FFL_DATABASE_PATH))
    )
    try:
        create_schema(conn)
        persistence.create_communications_schema(conn)
        result = run_once(
            conn,
            LoopMessageProvider.from_environment(),
            os.environ.get("FFL_COMMUNICATION_RECEIPT_KEY", ""),
            _configured_alert_sender(),
        )
    except Exception:
        # Avoid putting any protected provider material into systemd/journal logs.
        print("ffl communications worker failed", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
