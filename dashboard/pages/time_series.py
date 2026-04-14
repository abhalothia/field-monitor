"""Time series page: index charts over time."""

import sqlite3
from datetime import datetime, timedelta

import streamlit as st

from dashboard.components.index_chart import render_index_chart, render_multi_index_chart
from db.repository import get_alerts, get_readings
from src.indices import ALL_INDEX_NAMES, INDEX_CATALOG
from src.models import FieldPolygon


def render_time_series(conn: sqlite3.Connection, field: FieldPolygon) -> None:
    st.header("Index time series")

    # Controls
    col1, col2 = st.columns([1, 1])
    with col1:
        selected_index = st.selectbox(
            "Select index",
            ALL_INDEX_NAMES,
            format_func=lambda n: INDEX_CATALOG[n].display_name,
        )
    with col2:
        period = st.selectbox(
            "Period",
            ["3 months", "6 months", "12 months"],
            index=1,
        )

    period_days = {"3 months": 90, "6 months": 180, "12 months": 365}
    days = period_days[period]
    date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Single index chart
    readings = get_readings(
        conn, field.field_id, index_name=selected_index, date_from=date_from,
    )
    alerts = get_alerts(conn, field.field_id, limit=100)

    render_index_chart(readings, selected_index, alerts=alerts)

    # Statistics table
    if readings:
        means = [r.mean_value for r in readings if r.mean_value is not None]
        if means:
            st.subheader("Period statistics")
            cols = st.columns(4)
            import numpy as np
            cols[0].metric("Mean", f"{np.mean(means):.3f}")
            cols[1].metric("Std Dev", f"{np.std(means):.3f}")
            cols[2].metric("Min", f"{np.min(means):.3f}")
            cols[3].metric("Max", f"{np.max(means):.3f}")

    # Multi-index comparison
    st.subheader("Multi-index comparison")
    all_readings = {}
    for name in ALL_INDEX_NAMES:
        all_readings[name] = get_readings(
            conn, field.field_id, index_name=name, date_from=date_from,
        )
    render_multi_index_chart(all_readings)
