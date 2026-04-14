"""Interactive polygon editor using click-to-place points on a map."""

import folium
import streamlit as st
from streamlit_folium import st_folium

# Default center: India
DEFAULT_LAT = 22.0
DEFAULT_LON = 78.0
DEFAULT_ZOOM = 5

SESSION_KEY = "polygon_points"


def render_polygon_editor(
    center_lat: float | None = None,
    center_lon: float | None = None,
    zoom: int | None = None,
    height: int = 500,
) -> list[tuple[float, float]] | None:
    """Render a map where the user clicks to place polygon vertices.

    Each click adds a numbered marker. Points are connected in order
    to form a polygon preview. Returns the polygon coordinates once
    3+ points are placed.

    Returns:
        List of (lon, lat) tuples forming the closed polygon, or None
        if fewer than 3 points have been placed.
    """
    # Initialize session state
    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = []

    points: list[tuple[float, float]] = st.session_state[SESSION_KEY]

    # --- Location search ---
    st.caption("Navigate to a location by entering coordinates:")
    search_col1, search_col2, search_col3 = st.columns([2, 2, 1])
    with search_col1:
        search_lat = st.number_input(
            "Latitude", value=center_lat or DEFAULT_LAT,
            min_value=-90.0, max_value=90.0,
            format="%.6f", key="search_lat",
        )
    with search_col2:
        search_lon = st.number_input(
            "Longitude", value=center_lon or DEFAULT_LON,
            min_value=-180.0, max_value=180.0,
            format="%.6f", key="search_lon",
        )
    with search_col3:
        st.write("")
        if st.button("Go", use_container_width=True):
            st.session_state["map_center"] = [search_lat, search_lon]
            st.session_state["map_zoom"] = 17
            st.rerun()

    # --- Controls ---
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 3])
    with ctrl_col1:
        if st.button("Undo last point", disabled=len(points) == 0):
            points.pop()
            st.session_state[SESSION_KEY] = points
            st.rerun()
    with ctrl_col2:
        if st.button("Clear all points", disabled=len(points) == 0):
            st.session_state[SESSION_KEY] = []
            st.rerun()
    with ctrl_col3:
        st.caption(f"{len(points)} point(s) placed. Click the map to add more.")

    # --- Determine map center ---
    if points:
        # Center on the last placed point
        last_lon, last_lat = points[-1]
        default_center = [last_lat, last_lon]
        default_zoom = 17
    else:
        default_center = [center_lat or DEFAULT_LAT, center_lon or DEFAULT_LON]
        default_zoom = zoom or DEFAULT_ZOOM

    map_center = st.session_state.get("map_center", default_center)
    map_zoom = st.session_state.get("map_zoom", default_zoom)

    # --- Build map ---
    m = folium.Map(
        location=map_center,
        zoom_start=map_zoom,
        tiles="Esri.WorldImagery",
        attr="Esri",
    )

    # Add existing points as numbered markers
    for i, (lon, lat) in enumerate(points):
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=f'<div style="background:#00ff00;color:#000;'
                     f'border-radius:50%;width:24px;height:24px;'
                     f'text-align:center;line-height:24px;'
                     f'font-weight:bold;font-size:12px;'
                     f'border:2px solid #fff;">{i + 1}</div>',
                icon_size=(24, 24),
                icon_anchor=(12, 12),
            ),
        ).add_to(m)

    # Draw polygon preview if 3+ points
    if len(points) >= 3:
        # Folium.Polygon expects [[lat, lon], ...]
        ring = [[lat, lon] for lon, lat in points]
        folium.Polygon(
            locations=ring,
            color="#00ff00",
            weight=3,
            fill=True,
            fill_color="#00ff00",
            fill_opacity=0.15,
        ).add_to(m)
    elif len(points) >= 2:
        # Draw lines connecting the points
        line = [[lat, lon] for lon, lat in points]
        folium.PolyLine(
            locations=line,
            color="#00ff00",
            weight=2,
            dash_array="5",
        ).add_to(m)

    # --- Render map and capture clicks ---
    output = st_folium(
        m,
        width=None,
        height=height,
        returned_objects=["last_clicked"],
    )

    # --- Handle new click ---
    if output and output.get("last_clicked"):
        clicked = output["last_clicked"]
        new_point = (clicked["lng"], clicked["lat"])  # store as (lon, lat)

        # Avoid duplicate if the same point is returned on rerender
        if not points or points[-1] != new_point:
            points.append(new_point)
            st.session_state[SESSION_KEY] = points
            st.rerun()

    # --- Return polygon if valid ---
    if len(points) >= 3:
        # Close the polygon (first point = last point)
        closed = points.copy()
        if closed[0] != closed[-1]:
            closed.append(closed[0])
        return closed

    return None
