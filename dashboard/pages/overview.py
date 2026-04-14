"""Overview page: map, health score, sparklines, recent alerts."""

import sqlite3

import streamlit as st

from dashboard.components.alert_card import render_alert_list
from dashboard.components.field_map import render_field_map
from dashboard.components.health_gauge import render_health_gauge, render_risk_breakdown
from db.repository import get_alerts, get_field_crop_type, get_latest_risk, get_readings
from src.indices import ALL_INDEX_NAMES, INDEX_CATALOG
from src.models import FieldPolygon


def render_overview(conn: sqlite3.Connection, field: FieldPolygon) -> None:
    # Crop type badge
    crop_type = get_field_crop_type(conn, field.field_id)
    if crop_type:
        st.header(f"Field health overview -- {crop_type}")
    else:
        st.header("Field health overview")

    risk = get_latest_risk(conn, field.field_id)
    overall_score = risk.overall_score if risk else 0.0

    col_map, col_health = st.columns([1, 1])

    with col_map:
        render_field_map(
            field.center_lat, field.center_lon,
            field.polygon_geojson, field.name,
            health_score=overall_score,
        )

    with col_health:
        render_health_gauge(overall_score)
        if risk:
            render_risk_breakdown(
                risk.pest_risk, risk.disease_risk,
                risk.water_stress, risk.nutrient_stress,
            )

    # Latest index values
    st.subheader("Latest index values")
    cols = st.columns(len(ALL_INDEX_NAMES))
    for col, name in zip(cols, ALL_INDEX_NAMES):
        with col:
            readings = get_readings(conn, field.field_id, index_name=name)
            if readings and readings[-1].mean_value is not None:
                val = readings[-1].mean_value
                info = INDEX_CATALOG[name]
                # Compute delta from previous reading
                delta = None
                if len(readings) >= 2 and readings[-2].mean_value is not None:
                    delta = f"{val - readings[-2].mean_value:+.3f}"
                st.metric(name, f"{val:.3f}", delta)
            else:
                st.metric(name, "N/A")

    # Contributing factors
    if risk and risk.contributing_factors:
        st.subheader("Contributing factors")
        for factor in risk.contributing_factors[:5]:
            st.markdown(f"- {factor}")

    # Recent alerts
    st.subheader("Recent alerts")
    alerts = get_alerts(conn, field.field_id, acknowledged=False, limit=5)
    render_alert_list(alerts)
