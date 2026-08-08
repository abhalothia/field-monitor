"""Small, explainable checks that power the manager-facing Agents page."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ffl.persistence import repository
from ffl.services.trackwick_ingest import SOURCE_KEY


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def default_agents(conn) -> list[dict]:
    """Return the two live, source-backed notifications the team can act on now."""
    source = repository.get_source_registry_by_key(conn, SOURCE_KEY)
    if source is None:
        return [
            {"id": "farmer-no-update-7d", "name": "No update in 7 days", "count": 0,
             "summary": "No farmers are waiting for an update.", "status": "live"},
            {"id": "disease-watch", "name": "Disease reports", "count": 0,
             "summary": "No disease reports need review.", "status": "live"},
        ]

    source_id = source.id
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
    stale_cutoff = latest - timedelta(days=7) if latest is not None else None
    farmers_without_update = sum(
        activity is None or (stale_cutoff is not None and activity < stale_cutoff)
        for activity in activity_times
    )
    disease_watch = conn.execute(
        """SELECT COUNT(*) AS total FROM trackwick_visit_findings
           WHERE source_id = ? AND finding_kind = 'disease' AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchone()["total"]
    return [
        {"id": "farmer-no-update-7d", "name": "No update in 7 days", "count": int(farmers_without_update),
         "summary": f"{farmers_without_update:,} farmers have no update in the last 7 days of recorded activity.", "status": "live"},
        {"id": "disease-watch", "name": "Disease reports", "count": int(disease_watch),
         "summary": f"{int(disease_watch):,} disease reports need review.", "status": "live"},
    ]


def board(conn) -> dict:
    return {
        "agents": default_agents(conn),
        "custom_agents": [
            {
                "id": item.id, "name": item.name, "instruction": item.natural_language_rule,
                "enabled": item.enabled, "status": "live" if item.enabled else "in_review", "updated_at": item.updated_at,
            }
            for item in repository.list_agent_notifications(conn)
        ],
    }
