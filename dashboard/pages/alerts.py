"""Alerts page: filterable alert table with acknowledge/export."""

import sqlite3

import pandas as pd
import streamlit as st

from db.repository import acknowledge_alert, get_alerts
from src.models import FieldPolygon


def render_alerts(conn: sqlite3.Connection, field: FieldPolygon) -> None:
    st.header("Anomaly alerts")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox(
            "Status", ["Active", "Acknowledged", "All"],
        )
    with col2:
        severity_filter = st.selectbox(
            "Severity", ["All", "critical", "high", "medium", "low"],
        )
    with col3:
        limit = st.number_input("Max results", 10, 500, 50)

    # Map filters
    acknowledged = None
    if status_filter == "Active":
        acknowledged = False
    elif status_filter == "Acknowledged":
        acknowledged = True

    severity = severity_filter if severity_filter != "All" else None

    alerts = get_alerts(
        conn, field.field_id,
        severity=severity, acknowledged=acknowledged, limit=limit,
    )

    if not alerts:
        st.success("No alerts match the selected filters.")
        return

    st.caption(f"Showing {len(alerts)} alerts")

    # Build dataframe
    rows = []
    for a in alerts:
        rows.append({
            "ID": a.id,
            "Date": a.alert_date,
            "Index": a.index_name,
            "Type": a.alert_type.replace("_", " "),
            "Severity": a.severity.upper(),
            "Value": f"{a.current_value:.3f}",
            "Baseline": f"{a.baseline_value:.3f}" if a.baseline_value else "-",
            "Message": a.message,
            "Ack": "Yes" if a.is_acknowledged else "No",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Acknowledge action
    col_ack, col_export = st.columns(2)
    with col_ack:
        alert_id = st.number_input(
            "Alert ID to acknowledge", min_value=1, step=1,
        )
        if st.button("Acknowledge"):
            acknowledge_alert(conn, alert_id)
            st.success(f"Alert #{alert_id} acknowledged")
            st.rerun()

    with col_export:
        csv = df.to_csv(index=False)
        st.download_button(
            "Export CSV", csv, "alerts.csv", "text/csv",
        )
