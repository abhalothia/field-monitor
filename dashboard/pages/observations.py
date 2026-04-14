"""Ground truth observations page: logging form and history."""

import sqlite3
from datetime import date, datetime

import pandas as pd
import streamlit as st

from db.repository import get_observations, insert_observation
from src.models import FieldPolygon, GroundObservation


CATEGORIES = ["pest", "disease", "weed", "nutrient", "water", "other"]
SEVERITIES = ["none", "low", "medium", "high"]


def render_observations(conn: sqlite3.Connection, field: FieldPolygon) -> None:
    st.header("Ground truth observations")

    # --- Log new observation ---
    st.subheader("Log new observation")

    with st.form("observation_form"):
        col1, col2 = st.columns(2)
        with col1:
            obs_date = st.date_input("Date", value=date.today())
            category = st.selectbox("Category", CATEGORIES)
            severity = st.selectbox("Severity", SEVERITIES, index=1)

        with col2:
            description = st.text_area(
                "Description",
                placeholder="Describe what you observed on the field...",
            )
            affected_pct = st.slider("Affected area (%)", 0, 100, 10)

        submitted = st.form_submit_button("Save observation")

        if submitted:
            if not description.strip():
                st.error("Please provide a description.")
            else:
                obs = GroundObservation(
                    field_id=field.field_id,
                    observation_date=obs_date.isoformat(),
                    category=category,
                    severity=severity,
                    description=description.strip(),
                    affected_area_pct=float(affected_pct),
                )
                insert_observation(conn, obs)
                st.success("Observation saved successfully.")
                st.rerun()

    # --- Observation history ---
    st.subheader("Observation history")

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        cat_filter = st.selectbox(
            "Filter by category", ["All"] + CATEGORIES, key="obs_cat",
        )
    with filter_col2:
        date_range = st.date_input(
            "Date range",
            value=(date.today().replace(month=1, day=1), date.today()),
            key="obs_dates",
        )

    cat = cat_filter if cat_filter != "All" else None
    date_from = date_range[0].isoformat() if len(date_range) >= 1 else None
    date_to = date_range[1].isoformat() if len(date_range) >= 2 else None

    observations = get_observations(
        conn, field.field_id, category=cat,
        date_from=date_from, date_to=date_to,
    )

    if not observations:
        st.info("No observations recorded yet.")
        return

    rows = []
    for o in observations:
        rows.append({
            "Date": o.observation_date,
            "Category": o.category.capitalize(),
            "Severity": o.severity.upper(),
            "Description": o.description,
            "Affected %": f"{o.affected_area_pct:.0f}%" if o.affected_area_pct else "-",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
