"""Streamlit dashboard entry point with sidebar navigation."""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH, FIELD_NAME, KML_PATH, get_sentinel_config
from db.schema import create_tables
from db.repository import get_all_fields, get_field, get_field_crop_type, upsert_field
from src.data_fetcher import fetch_and_analyze
from src.geometry import build_field_polygon
from src.kml_parser import parse_polygon_coordinates

from dashboard.pages.overview import render_overview
from dashboard.pages.time_series import render_time_series
from dashboard.pages.imagery import render_imagery
from dashboard.pages.alerts import render_alerts
from dashboard.pages.observations import render_observations
from dashboard.pages.fields import render_fields
from dashboard.pages.paddy_timeline import render_paddy_timeline


st.set_page_config(
    page_title="Field Monitor",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(DB_PATH), check_same_thread=False, timeout=30.0,
    )
    conn.row_factory = sqlite3.Row
    # WAL lets reads and writes coexist cleanly if the DB lives in a synced
    # folder (Dropbox/iCloud). busy_timeout makes the migration wait instead
    # of failing instantly if the sync client is holding a shared lock.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    create_tables(conn)
    return conn


def _load_kml_field_if_needed(conn: sqlite3.Connection) -> None:
    """Import the original KML field on first run (migration helper)."""
    try:
        if not get_all_fields(conn) and KML_PATH.exists():
            coords = parse_polygon_coordinates(KML_PATH, FIELD_NAME)
            field = build_field_polygon(FIELD_NAME, coords, field_id="mandi_field_01")
            upsert_field(conn, field)
    except Exception:
        pass  # KML not available or already imported


def _get_active_field(conn: sqlite3.Connection):
    """Return the currently selected field, or None if no fields exist."""
    fields = get_all_fields(conn)
    if not fields:
        return None

    active_id = st.session_state.get("active_field_id")
    if active_id:
        field = get_field(conn, active_id)
        if field:
            return field

    # Default to first field
    st.session_state["active_field_id"] = fields[0].field_id
    return fields[0]


# Pages that need a field selected
FIELD_PAGES = {
    "Overview": render_overview,
    "Time series": render_time_series,
    "Imagery": render_imagery,
    "Alerts": render_alerts,
    "Observations": render_observations,
}

ALL_PAGES = list(FIELD_PAGES.keys()) + ["Fields"]

PADDY_PAGES = ["Timeline map", "Fields"]


def main():
    conn = _get_connection()
    _load_kml_field_if_needed(conn)

    fields = get_all_fields(conn)
    field = _get_active_field(conn)

    # --- Sidebar ---
    with st.sidebar:
        st.title("Field Monitor")

        mode = st.radio(
            "Mode",
            ["Generic monitor", "Paddy Kharif 2025"],
            index=0,
            horizontal=False,
        )
        st.divider()

        # Field selector (shared across modes)
        if fields:
            field_options = {f.field_id: f.name for f in fields}
            selected_id = st.selectbox(
                "Active field",
                options=list(field_options.keys()),
                format_func=lambda fid: field_options[fid],
                index=(
                    list(field_options.keys()).index(field.field_id)
                    if field and field.field_id in field_options
                    else 0
                ),
            )
            if selected_id != st.session_state.get("active_field_id"):
                st.session_state["active_field_id"] = selected_id
                st.rerun()

            if field:
                crop = get_field_crop_type(conn, field.field_id)
                info_parts = [f"{field.area_hectares:.2f} ha"]
                if crop:
                    info_parts.append(crop)
                st.caption(" | ".join(info_parts))
                st.caption(
                    f"{field.center_lat:.4f}N, {field.center_lon:.4f}E"
                )
        else:
            st.info("No fields yet. Create one below.")

        st.divider()

        # If no fields, default to Fields page
        if mode == "Paddy Kharif 2025":
            pages_for_mode = PADDY_PAGES
            default_page = "Fields" if not fields else "Timeline map"
        else:
            pages_for_mode = ALL_PAGES
            default_page = "Fields" if not fields else "Overview"
        default_idx = pages_for_mode.index(default_page)

        page = st.radio(
            "Navigation",
            pages_for_mode,
            index=default_idx,
            label_visibility="collapsed",
        )

        st.divider()

        # Manual fetch button (only if a field is selected)
        if field:
            if st.button("Fetch latest data", use_container_width=True):
                with st.spinner("Fetching satellite data..."):
                    try:
                        config = get_sentinel_config()
                        summary = fetch_and_analyze(
                            conn, field, config, lookback_days=30,
                        )
                        st.success(
                            f"Done: {summary['readings_stored']} readings, "
                            f"{summary['images_saved']} images"
                        )
                        if summary["errors"]:
                            st.warning(
                                f"{len(summary['errors'])} errors occurred"
                            )
                    except Exception as exc:
                        st.error(f"Fetch failed: {exc}")

        st.divider()
        st.caption(
            f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    # --- Main content ---
    if mode == "Paddy Kharif 2025":
        if page == "Timeline map":
            render_paddy_timeline(conn)
        elif page == "Fields":
            render_fields(conn, field, mode="paddy")
        return

    if page == "Fields":
        render_fields(conn, field, mode="generic")
    elif page in FIELD_PAGES:
        if field is None:
            st.warning(
                "No field selected. Go to the **Fields** page to create one."
            )
        else:
            FIELD_PAGES[page](conn, field)


if __name__ == "__main__":
    main()
else:
    main()
