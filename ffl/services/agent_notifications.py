"""Small, explainable checks that power the manager-facing Agents page."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ffl.persistence import repository
from ffl.services.trackwick_ingest import SOURCE_KEY


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def default_agents(conn) -> list[dict]:
    """Return four current counts without exposing source records to the browser."""
    source = repository.get_source_registry_by_key(conn, SOURCE_KEY)
    if source is None:
        return [
            {"id": "paddy-no-visits", "name": "Paddy — no visits", "count": 0, "summary": "No farm visits need attention."},
            {"id": "farmer-no-visits", "name": "Farmer — no visits", "count": 0, "summary": "No farmers need a first visit."},
            {"id": "farmer-no-update", "name": "Farmer — no update", "count": 0, "summary": "No farmers are waiting for an update."},
            {"id": "disease-watch", "name": "Disease watch", "count": 0, "summary": "No disease reports need review."},
        ]

    source_id = source.id
    paddy_no_visits = conn.execute(
        """SELECT COUNT(*) AS total
           FROM trackwick_registrations AS registration
           WHERE registration.source_id = ? AND registration.registration_status = 'completed'
             AND registration.data_quality_status = 'valid'
             AND NOT EXISTS (
                SELECT 1 FROM trackwick_tasks AS task
                JOIN trackwick_visits AS visit ON visit.task_id = task.id
                 AND visit.data_quality_status = 'valid'
                WHERE task.source_id = registration.source_id
                  AND task.farmer_party_id = registration.farmer_party_id
                  AND task.data_quality_status = 'valid'
             )""",
        (source_id,),
    ).fetchone()["total"]
    farmer_no_visits = conn.execute(
        """SELECT COUNT(*) AS total
           FROM trackwick_parties AS farmer
           WHERE farmer.source_id = ? AND farmer.party_kind = 'farmer'
             AND farmer.data_quality_status = 'valid'
             AND NOT EXISTS (
                SELECT 1 FROM trackwick_tasks AS task
                JOIN trackwick_visits AS visit ON visit.task_id = task.id
                 AND visit.data_quality_status = 'valid'
                WHERE task.source_id = farmer.source_id
                  AND task.farmer_party_id = farmer.id
                  AND task.data_quality_status = 'valid'
             )""",
        (source_id,),
    ).fetchone()["total"]
    rows = conn.execute(
        """SELECT farmer.id, MAX(COALESCE(task.provider_completed_at, task.provider_started_at,
                task.provider_created_at, task.last_seen_at)) AS latest_activity
           FROM trackwick_parties AS farmer
           LEFT JOIN trackwick_tasks AS task ON task.farmer_party_id = farmer.id
             AND task.source_id = farmer.source_id AND task.data_quality_status = 'valid'
           WHERE farmer.source_id = ? AND farmer.party_kind = 'farmer'
             AND farmer.data_quality_status = 'valid'
           GROUP BY farmer.id""",
        (source_id,),
    ).fetchall()
    activity_times = [_parse_time(row["latest_activity"]) for row in rows]
    latest = max((item for item in activity_times if item is not None), default=None)
    stale_cutoff = latest - timedelta(days=14) if latest is not None else None
    farmer_no_update = sum(
        activity is None or (stale_cutoff is not None and activity < stale_cutoff)
        for activity in activity_times
    )
    disease_watch = conn.execute(
        """SELECT COUNT(*) AS total FROM trackwick_visit_findings
           WHERE source_id = ? AND finding_kind = 'disease' AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchone()["total"]
    return [
        {"id": "paddy-no-visits", "name": "Paddy — no visits", "count": int(paddy_no_visits),
         "summary": f"{int(paddy_no_visits):,} paddy records have no visit yet."},
        {"id": "farmer-no-visits", "name": "Farmer — no visits", "count": int(farmer_no_visits),
         "summary": f"{int(farmer_no_visits):,} farmers have no visit yet."},
        {"id": "farmer-no-update", "name": "Farmer — no update", "count": int(farmer_no_update),
         "summary": f"{farmer_no_update:,} farmers have no update in the last 14 days of available activity."},
        {"id": "disease-watch", "name": "Disease watch", "count": int(disease_watch),
         "summary": f"{int(disease_watch):,} disease reports need attention."},
    ]


def board(conn) -> dict:
    return {
        "agents": default_agents(conn),
        "custom_agents": [
            {
                "id": item.id, "name": item.name, "instruction": item.natural_language_rule,
                "enabled": item.enabled, "updated_at": item.updated_at,
            }
            for item in repository.list_agent_notifications(conn)
        ],
    }
