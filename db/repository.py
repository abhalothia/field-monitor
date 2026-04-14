"""Database CRUD operations for all tables."""

import json
import sqlite3

from src.models import (
    AnomalyAlert,
    FieldPolygon,
    GroundObservation,
    ImageryRecord,
    IndexReading,
    RiskAssessment,
)


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------

def upsert_field(conn: sqlite3.Connection, fp: FieldPolygon) -> None:
    conn.execute(
        """INSERT INTO fields (field_id, name, polygon_wkt, polygon_geojson,
           center_lat, center_lon, area_hectares)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(field_id) DO UPDATE SET
             name=excluded.name,
             polygon_wkt=excluded.polygon_wkt,
             polygon_geojson=excluded.polygon_geojson,
             center_lat=excluded.center_lat,
             center_lon=excluded.center_lon,
             area_hectares=excluded.area_hectares""",
        (
            fp.field_id, fp.name, fp.polygon_wkt,
            json.dumps(fp.polygon_geojson),
            fp.center_lat, fp.center_lon, fp.area_hectares,
        ),
    )
    conn.commit()


def get_field(conn: sqlite3.Connection, field_id: str) -> FieldPolygon | None:
    row = conn.execute(
        "SELECT * FROM fields WHERE field_id = ?", (field_id,),
    ).fetchone()
    if row is None:
        return None
    return FieldPolygon(
        field_id=row["field_id"],
        name=row["name"],
        coordinates=[],  # not stored separately; use geojson
        center_lon=row["center_lon"],
        center_lat=row["center_lat"],
        area_hectares=row["area_hectares"],
        polygon_wkt=row["polygon_wkt"],
        polygon_geojson=json.loads(row["polygon_geojson"]),
    )


def get_all_fields(conn: sqlite3.Connection) -> list[FieldPolygon]:
    rows = conn.execute("SELECT * FROM fields").fetchall()
    return [
        FieldPolygon(
            field_id=r["field_id"], name=r["name"], coordinates=[],
            center_lon=r["center_lon"], center_lat=r["center_lat"],
            area_hectares=r["area_hectares"], polygon_wkt=r["polygon_wkt"],
            polygon_geojson=json.loads(r["polygon_geojson"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Index readings
# ---------------------------------------------------------------------------

def upsert_reading(conn: sqlite3.Connection, r: IndexReading) -> None:
    conn.execute(
        """INSERT INTO index_readings
           (field_id, index_name, reading_date, mean_value, min_value,
            max_value, stdev_value, sample_count, cloud_cover_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(field_id, index_name, reading_date) DO UPDATE SET
             mean_value=excluded.mean_value,
             min_value=excluded.min_value,
             max_value=excluded.max_value,
             stdev_value=excluded.stdev_value,
             sample_count=excluded.sample_count,
             cloud_cover_pct=excluded.cloud_cover_pct""",
        (
            r.field_id, r.index_name, r.reading_date,
            r.mean_value, r.min_value, r.max_value,
            r.stdev_value, r.sample_count, r.cloud_cover_pct,
        ),
    )
    conn.commit()


def get_readings(
    conn: sqlite3.Connection,
    field_id: str,
    index_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[IndexReading]:
    query = "SELECT * FROM index_readings WHERE field_id = ?"
    params: list = [field_id]

    if index_name:
        query += " AND index_name = ?"
        params.append(index_name)
    if date_from:
        query += " AND reading_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND reading_date <= ?"
        params.append(date_to)

    query += " ORDER BY reading_date ASC"

    rows = conn.execute(query, params).fetchall()
    return [
        IndexReading(
            field_id=r["field_id"], index_name=r["index_name"],
            reading_date=r["reading_date"], mean_value=r["mean_value"],
            min_value=r["min_value"], max_value=r["max_value"],
            stdev_value=r["stdev_value"], sample_count=r["sample_count"],
            cloud_cover_pct=r["cloud_cover_pct"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Imagery
# ---------------------------------------------------------------------------

def upsert_imagery(conn: sqlite3.Connection, img: ImageryRecord) -> None:
    conn.execute(
        """INSERT INTO imagery
           (field_id, image_date, image_type, file_path, width_px, height_px)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(field_id, image_date, image_type) DO UPDATE SET
             file_path=excluded.file_path,
             width_px=excluded.width_px,
             height_px=excluded.height_px""",
        (
            img.field_id, img.image_date, img.image_type,
            img.file_path, img.width_px, img.height_px,
        ),
    )
    conn.commit()


def get_imagery(
    conn: sqlite3.Connection,
    field_id: str,
    image_type: str | None = None,
) -> list[ImageryRecord]:
    query = "SELECT * FROM imagery WHERE field_id = ?"
    params: list = [field_id]
    if image_type:
        query += " AND image_type = ?"
        params.append(image_type)
    query += " ORDER BY image_date DESC"

    rows = conn.execute(query, params).fetchall()
    return [
        ImageryRecord(
            field_id=r["field_id"], image_date=r["image_date"],
            image_type=r["image_type"], file_path=r["file_path"],
            width_px=r["width_px"], height_px=r["height_px"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def insert_alert(conn: sqlite3.Connection, a: AnomalyAlert) -> int:
    cursor = conn.execute(
        """INSERT INTO alerts
           (field_id, alert_date, index_name, alert_type, severity,
            current_value, baseline_value, deviation, message)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            a.field_id, a.alert_date, a.index_name, a.alert_type,
            a.severity, a.current_value, a.baseline_value,
            a.deviation, a.message,
        ),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def get_alerts(
    conn: sqlite3.Connection,
    field_id: str,
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = 50,
) -> list[AnomalyAlert]:
    query = "SELECT * FROM alerts WHERE field_id = ?"
    params: list = [field_id]
    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if acknowledged is not None:
        query += " AND is_acknowledged = ?"
        params.append(1 if acknowledged else 0)
    query += " ORDER BY alert_date DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [
        AnomalyAlert(
            id=r["id"], field_id=r["field_id"],
            alert_date=r["alert_date"], index_name=r["index_name"],
            alert_type=r["alert_type"], severity=r["severity"],
            current_value=r["current_value"],
            baseline_value=r["baseline_value"],
            deviation=r["deviation"], message=r["message"],
            is_acknowledged=bool(r["is_acknowledged"]),
        )
        for r in rows
    ]


def acknowledge_alert(conn: sqlite3.Connection, alert_id: int) -> None:
    conn.execute(
        "UPDATE alerts SET is_acknowledged = 1 WHERE id = ?", (alert_id,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Risk assessments
# ---------------------------------------------------------------------------

def upsert_risk_assessment(conn: sqlite3.Connection, ra: RiskAssessment) -> None:
    conn.execute(
        """INSERT INTO risk_assessments
           (field_id, assessment_date, overall_score, pest_risk,
            disease_risk, water_stress, nutrient_stress, contributing_factors)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(field_id, assessment_date) DO UPDATE SET
             overall_score=excluded.overall_score,
             pest_risk=excluded.pest_risk,
             disease_risk=excluded.disease_risk,
             water_stress=excluded.water_stress,
             nutrient_stress=excluded.nutrient_stress,
             contributing_factors=excluded.contributing_factors""",
        (
            ra.field_id, ra.assessment_date, ra.overall_score,
            ra.pest_risk, ra.disease_risk, ra.water_stress,
            ra.nutrient_stress, json.dumps(ra.contributing_factors),
        ),
    )
    conn.commit()


def get_latest_risk(
    conn: sqlite3.Connection, field_id: str,
) -> RiskAssessment | None:
    row = conn.execute(
        """SELECT * FROM risk_assessments WHERE field_id = ?
           ORDER BY assessment_date DESC LIMIT 1""",
        (field_id,),
    ).fetchone()
    if row is None:
        return None
    return RiskAssessment(
        field_id=row["field_id"],
        assessment_date=row["assessment_date"],
        overall_score=row["overall_score"],
        pest_risk=row["pest_risk"],
        disease_risk=row["disease_risk"],
        water_stress=row["water_stress"],
        nutrient_stress=row["nutrient_stress"],
        contributing_factors=json.loads(row["contributing_factors"]),
    )


def get_risk_history(
    conn: sqlite3.Connection, field_id: str,
) -> list[RiskAssessment]:
    rows = conn.execute(
        """SELECT * FROM risk_assessments WHERE field_id = ?
           ORDER BY assessment_date ASC""",
        (field_id,),
    ).fetchall()
    return [
        RiskAssessment(
            field_id=r["field_id"],
            assessment_date=r["assessment_date"],
            overall_score=r["overall_score"],
            pest_risk=r["pest_risk"],
            disease_risk=r["disease_risk"],
            water_stress=r["water_stress"],
            nutrient_stress=r["nutrient_stress"],
            contributing_factors=json.loads(r["contributing_factors"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Ground observations
# ---------------------------------------------------------------------------

def insert_observation(
    conn: sqlite3.Connection, obs: GroundObservation,
) -> int:
    cursor = conn.execute(
        """INSERT INTO observations
           (field_id, observation_date, category, severity, description,
            affected_area_pct, photo_path)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            obs.field_id, obs.observation_date, obs.category,
            obs.severity, obs.description, obs.affected_area_pct,
            obs.photo_path,
        ),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def get_observations(
    conn: sqlite3.Connection,
    field_id: str,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[GroundObservation]:
    query = "SELECT * FROM observations WHERE field_id = ?"
    params: list = [field_id]
    if category:
        query += " AND category = ?"
        params.append(category)
    if date_from:
        query += " AND observation_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND observation_date <= ?"
        params.append(date_to)
    query += " ORDER BY observation_date DESC"

    rows = conn.execute(query, params).fetchall()
    return [
        GroundObservation(
            id=r["id"], field_id=r["field_id"],
            observation_date=r["observation_date"],
            category=r["category"], severity=r["severity"],
            description=r["description"],
            affected_area_pct=r["affected_area_pct"],
            photo_path=r["photo_path"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Fetch log
# ---------------------------------------------------------------------------

def insert_fetch_log(
    conn: sqlite3.Connection,
    field_id: str,
    fetch_type: str,
    date_from: str,
    date_to: str,
    status: str,
    error_message: str | None = None,
    scenes_found: int | None = None,
    records_stored: int | None = None,
    duration_secs: float | None = None,
) -> None:
    conn.execute(
        """INSERT INTO fetch_log
           (field_id, fetch_type, date_from, date_to, status,
            error_message, scenes_found, records_stored, duration_secs)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            field_id, fetch_type, date_from, date_to, status,
            error_message, scenes_found, records_stored, duration_secs,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Field deletion (cascade)
# ---------------------------------------------------------------------------

def delete_field(conn: sqlite3.Connection, field_id: str) -> None:
    """Delete a field and all its associated data."""
    tables = [
        "index_readings", "imagery", "alerts",
        "risk_assessments", "observations", "fetch_log",
        "crop_detections",
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table} WHERE field_id = ?", (field_id,))
    conn.execute("DELETE FROM fields WHERE field_id = ?", (field_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Crop detections
# ---------------------------------------------------------------------------

def insert_crop_detection(
    conn: sqlite3.Connection,
    field_id: str,
    detection_date: str,
    season_start: str,
    season_end: str,
    crop_type: str,
    confidence: float | None = None,
    pixel_counts: dict | None = None,
    geotiff_path: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO crop_detections
           (field_id, detection_date, season_start, season_end,
            crop_type, confidence, pixel_counts, geotiff_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            field_id, detection_date, season_start, season_end,
            crop_type, confidence,
            json.dumps(pixel_counts) if pixel_counts else None,
            geotiff_path,
        ),
    )
    # Also update the field's crop_type
    conn.execute(
        "UPDATE fields SET crop_type = ?, crop_confidence = ? WHERE field_id = ?",
        (crop_type, confidence, field_id),
    )
    conn.commit()


def get_latest_crop_detection(
    conn: sqlite3.Connection, field_id: str,
) -> dict | None:
    row = conn.execute(
        """SELECT * FROM crop_detections WHERE field_id = ?
           ORDER BY detection_date DESC LIMIT 1""",
        (field_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "field_id": row["field_id"],
        "detection_date": row["detection_date"],
        "season_start": row["season_start"],
        "season_end": row["season_end"],
        "crop_type": row["crop_type"],
        "confidence": row["confidence"],
        "pixel_counts": json.loads(row["pixel_counts"]) if row["pixel_counts"] else {},
        "geotiff_path": row["geotiff_path"],
    }


def get_field_crop_type(conn: sqlite3.Connection, field_id: str) -> str | None:
    """Return the detected crop type for a field, or None."""
    row = conn.execute(
        "SELECT crop_type FROM fields WHERE field_id = ?", (field_id,),
    ).fetchone()
    if row is None:
        return None
    return row["crop_type"]
