"""Field management page: create new fields and manage existing ones."""

import sqlite3
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config.settings import get_sentinel_config
from dashboard.components.polygon_editor import render_polygon_editor
from db.repository import (
    delete_field,
    get_all_fields,
    get_field,
    get_latest_crop_detection,
    insert_crop_detection,
    upsert_field,
)
from src.crop_detector import CropDetector
from src.data_fetcher import fetch_and_analyze
from src.geometry import build_field_polygon
from src.models import FieldPolygon


def render_fields(conn: sqlite3.Connection, field: FieldPolygon | None) -> None:
    st.header("Field management")

    tab_create, tab_manage = st.tabs(["Create new field", "Manage fields"])

    with tab_create:
        _render_create_field(conn)

    with tab_manage:
        _render_manage_fields(conn)


def _render_create_field(conn: sqlite3.Connection) -> None:
    """Draw a polygon on the map to create a new field."""
    # Center on existing field if available, else default
    fields = get_all_fields(conn)
    center_lat = fields[0].center_lat if fields else None
    center_lon = fields[0].center_lon if fields else None

    drawn_coords = render_polygon_editor(
        center_lat=center_lat,
        center_lon=center_lon,
    )

    if drawn_coords and len(drawn_coords) >= 3:
        # Preview the drawn polygon
        preview = build_field_polygon("Preview", drawn_coords)

        st.success(
            f"Polygon drawn: {len(drawn_coords) - 1} points, "
            f"{preview.area_hectares:.2f} hectares"
        )
        st.caption(
            f"Center: {preview.center_lat:.6f}N, "
            f"{preview.center_lon:.6f}E"
        )

        # Name input and save
        field_name = st.text_input(
            "Field name",
            placeholder="e.g. North wheat plot, Ravi's farm...",
        )

        lookback = st.slider(
            "Fetch historical data (days)",
            min_value=30, max_value=365, value=90,
        )

        if st.button(
            "Save field and fetch data",
            disabled=not field_name.strip(),
            use_container_width=True,
            type="primary",
        ):
            new_field = build_field_polygon(field_name.strip(), drawn_coords)
            upsert_field(conn, new_field)

            # Set as active field
            st.session_state["active_field_id"] = new_field.field_id

            # Fetch satellite data
            with st.spinner(
                f"Fetching {lookback} days of satellite data for "
                f"{field_name}..."
            ):
                try:
                    config = get_sentinel_config()
                    summary = fetch_and_analyze(
                        conn, new_field, config, lookback_days=lookback,
                    )
                    st.success(
                        f"Field saved. Fetched {summary['readings_stored']} "
                        f"readings, {summary['images_saved']} images."
                    )
                except Exception as exc:
                    st.warning(
                        f"Field saved but data fetch failed: {exc}. "
                        f"You can retry from the sidebar."
                    )

            st.rerun()

    elif drawn_coords is not None and len(drawn_coords) < 3:
        st.warning("A polygon needs at least 3 points.")


def _render_manage_fields(conn: sqlite3.Connection) -> None:
    """List, select, and delete existing fields."""
    fields = get_all_fields(conn)

    if not fields:
        st.info("No fields registered yet. Use the 'Create new field' tab to add one.")
        return

    # Fields table
    rows = []
    for f in fields:
        is_active = (
            st.session_state.get("active_field_id") == f.field_id
        )
        rows.append({
            "Active": "Yes" if is_active else "",
            "Name": f.name,
            "Area (ha)": f"{f.area_hectares:.2f}",
            "Latitude": f"{f.center_lat:.4f}",
            "Longitude": f"{f.center_lon:.4f}",
            "ID": f.field_id,
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    # Actions
    field_names = {f.field_id: f.name for f in fields}
    field_map = {f.field_id: f for f in fields}

    col_select, col_fetch, col_delete = st.columns(3)

    with col_select:
        selected_id = st.selectbox(
            "Switch active field",
            options=[f.field_id for f in fields],
            format_func=lambda fid: field_names[fid],
            key="manage_field_select",
        )
        if st.button("Set as active", use_container_width=True):
            st.session_state["active_field_id"] = selected_id
            st.rerun()

    with col_fetch:
        fetch_id = st.selectbox(
            "Fetch more data for",
            options=[f.field_id for f in fields],
            format_func=lambda fid: field_names[fid],
            key="manage_field_fetch",
        )
        lookback = st.slider(
            "Lookback (days)", 30, 365, 90, key="manage_lookback",
        )
        if st.button("Fetch data", use_container_width=True, type="primary"):
            target = field_map[fetch_id]
            with st.spinner(
                f"Fetching {lookback} days for '{target.name}'..."
            ):
                try:
                    config = get_sentinel_config()
                    summary = fetch_and_analyze(
                        conn, target, config, lookback_days=lookback,
                    )
                    st.success(
                        f"{summary['readings_stored']} readings, "
                        f"{summary['images_saved']} images fetched."
                    )
                except Exception as exc:
                    st.error(f"Fetch failed: {exc}")

    with col_delete:
        delete_id = st.selectbox(
            "Delete a field",
            options=[f.field_id for f in fields],
            format_func=lambda fid: field_names[fid],
            key="manage_field_delete",
        )
        delete_name = field_names.get(delete_id, "")
        if st.button(
            f"Delete '{delete_name}'",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state["confirm_delete"] = delete_id

        if st.session_state.get("confirm_delete") == delete_id:
            st.warning(
                f"This will permanently delete '{delete_name}' "
                f"and all its data."
            )
            if st.button("Confirm delete", type="primary"):
                delete_field(conn, delete_id)
                st.session_state.pop("confirm_delete", None)
                if st.session_state.get("active_field_id") == delete_id:
                    remaining = get_all_fields(conn)
                    if remaining:
                        st.session_state["active_field_id"] = remaining[0].field_id
                    else:
                        st.session_state.pop("active_field_id", None)
                st.success(f"Deleted '{delete_name}'.")
                st.rerun()

    # --- Crop type detection ---
    st.divider()
    st.subheader("Crop type detection (ESA WorldCereal)")

    detect_col1, detect_col2 = st.columns([1, 1])

    with detect_col1:
        detect_id = st.selectbox(
            "Detect crop for",
            options=[f.field_id for f in fields],
            format_func=lambda fid: field_names[fid],
            key="manage_field_detect",
        )

        # AGERA5 meteorological data lags ~2 months behind real-time.
        # Default to a complete past season for reliable results.
        safe_end = date(2024, 4, 30)
        safe_start = date(2023, 5, 1)
        st.caption(
            "Tip: Use a completed past season (e.g. May 2023 - Apr 2024). "
            "Recent dates may fail if weather data is not yet available."
        )
        season_range = st.date_input(
            "Growing season",
            value=(safe_start, safe_end),
            key="crop_season",
        )

        if st.button("Run crop detection", type="primary", use_container_width=True):
            target = field_map[detect_id]
            s_start = season_range[0].isoformat() if len(season_range) >= 1 else default_start.isoformat()
            s_end = season_range[1].isoformat() if len(season_range) >= 2 else today.isoformat()

            with st.spinner(
                f"Running WorldCereal crop detection for '{target.name}' "
                f"({s_start} to {s_end}). This may take 5-15 minutes..."
            ):
                try:
                    config = get_sentinel_config()
                    detector = CropDetector(config.client_id, config.client_secret)
                    result = detector.detect(
                        target.polygon_geojson, s_start, s_end,
                    )

                    insert_crop_detection(
                        conn, target.field_id, today.isoformat(),
                        s_start, s_end,
                        crop_type=result["crop_type"],
                        confidence=result["confidence"],
                        pixel_counts=result["pixel_counts"],
                        geotiff_path=result.get("geotiff_path"),
                    )

                    st.success(
                        f"Detected: **{result['crop_type']}** "
                        f"({result['confidence']:.0%} confidence)"
                    )
                except Exception as exc:
                    st.error(f"Crop detection failed: {exc}")

    with detect_col2:
        # Show latest detection result
        detection = get_latest_crop_detection(conn, detect_id)
        if detection:
            st.metric("Detected crop", detection["crop_type"])
            st.caption(
                f"Confidence: {detection['confidence']:.0%} | "
                f"Season: {detection['season_start']} to {detection['season_end']} | "
                f"Detected: {detection['detection_date']}"
            )
            if detection["pixel_counts"]:
                st.caption("Pixel breakdown:")
                for label, count in sorted(
                    detection["pixel_counts"].items(),
                    key=lambda x: x[1], reverse=True,
                ):
                    st.caption(f"  {label}: {count} pixels")
        else:
            st.info("No crop detection yet. Run detection to identify the crop.")
