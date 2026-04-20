"""Streamlit dashboard entry point — paddy kharif 2025 monitor."""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH
from db.schema import create_tables
from db.repository import get_all_fields, get_field, get_field_crop_type

from dashboard.pages.fields import render_fields
from dashboard.pages.inspect import render_inspect
from dashboard.pages.paddy_timeline import render_paddy_timeline
from src.paddy_kharif.seed_fields import seed_fields_if_empty


st.set_page_config(
    page_title="Paddy Monitor",
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
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # Another process briefly held the DB; journal mode is optional.
    create_tables(conn)
    seed_fields_if_empty(conn)
    return conn


def _get_active_field(conn: sqlite3.Connection):
    fields = get_all_fields(conn)
    if not fields:
        return None
    active_id = st.session_state.get("active_field_id")
    if active_id:
        field = get_field(conn, active_id)
        if field:
            return field
    st.session_state["active_field_id"] = fields[0].field_id
    return fields[0]


PAGES = ["Timeline map", "Inspect plot", "Fields"]


def main():
    conn = _get_connection()
    fields = get_all_fields(conn)
    field = _get_active_field(conn)

    # --- Sidebar ---
    with st.sidebar:
        st.title("Paddy Monitor")
        st.caption("PB1 kharif 2025 · Aligarh / Bulandshahr")
        st.divider()

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
            st.info("No fields yet. Create one on the Fields page.")

        st.divider()

        default_page = "Fields" if not fields else "Timeline map"
        page = st.radio(
            "Navigation",
            PAGES,
            index=PAGES.index(default_page),
            label_visibility="collapsed",
        )

        st.divider()
        st.caption(
            f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    # --- Main content ---
    if page == "Timeline map":
        render_paddy_timeline(conn)
    elif page == "Inspect plot":
        render_inspect(conn, field)
    elif page == "Fields":
        render_fields(conn, field, mode="paddy")


if __name__ == "__main__":
    main()
else:
    main()
