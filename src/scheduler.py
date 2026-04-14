"""Background scheduler for periodic data fetching."""

import logging
import sqlite3
import threading

import schedule

from config.settings import DB_PATH, FETCH_INTERVAL_HOURS, get_sentinel_config
from db.schema import create_tables
from src.data_fetcher import fetch_and_analyze
from src.models import FieldPolygon

logger = logging.getLogger(__name__)


def start_scheduler(field: FieldPolygon) -> threading.Event:
    """Start a background thread that fetches data on a schedule.

    Returns a threading.Event that can be set to stop the scheduler.
    """
    stop_event = threading.Event()

    def _job():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            create_tables(conn)
            config = get_sentinel_config()
            fetch_and_analyze(conn, field, config)
            conn.close()
        except Exception as exc:
            logger.error("Scheduled fetch failed: %s", exc)

    schedule.every(FETCH_INTERVAL_HOURS).hours.do(_job)

    def _run():
        while not stop_event.is_set():
            schedule.run_pending()
            stop_event.wait(60)

    thread = threading.Thread(target=_run, daemon=True, name="field-monitor-scheduler")
    thread.start()
    logger.info("Scheduler started: fetching every %d hours", FETCH_INTERVAL_HOURS)

    return stop_event
