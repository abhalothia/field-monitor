"""Paddy kharif 2025 timeline page.

Weekly slider (June 1 2025 → Jan 15 2026, ~33 stops) drives a Folium map
that renders the NDVI (or RVI fallback) overlay PNG stored for that week,
plus per-field phenology event markers (T/H/! on a Plotly strip below).

The overlay PNG is the one the fetcher generated and wrote to
`data/overlays/<field_id>/<YYYY-MM-DD>_<kind>.png`. If no overlay exists
within ±7 days of the chosen week (e.g. fetcher hasn't run yet, or the
week was both cloud-covered AND had no SAR slot), the field shows a bare
polygon outline.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from db.repository import get_all_fields
from src.paddy_kharif.config import (
    SEASON_END,
    SEASON_START,
    SEASON_TAG,
    SLIDER_STEP_DAYS,
)
from src.paddy_kharif.overlay_renderer import (
    build_image_overlay_kwargs,
    folium_bounds_for_field,
    pick_overlay_for_week,
)
from src.paddy_kharif.repository_paddy import (
    get_paddy_events,
    get_season_readings,
)


EVENT_MARKER = {
    "transplanting": ("T", "#2a78b0"),
    "harvesting":    ("H", "#d97b00"),
    "stress":        ("!", "#d94848"),
    "flood":         ("~", "#1f77b4"),
    "drought":       ("x", "#8a3b3b"),
}


def _weekly_slider_dates() -> list[date]:
    start = datetime.strptime(SEASON_START, "%Y-%m-%d").date()
    end = datetime.strptime(SEASON_END, "%Y-%m-%d").date()
    out: list[date] = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=SLIDER_STEP_DAYS)
    return out


def _render_map(
    conn: sqlite3.Connection,
    fields,
    target_date: date,
) -> None:
    if not fields:
        st.info("No fields selected.")
        return

    # Centre on mean of centroids.
    lat = sum(f.center_lat for f in fields) / len(fields)
    lon = sum(f.center_lon for f in fields) / len(fields)

    m = folium.Map(
        location=[lat, lon], zoom_start=14,
        tiles="Esri.WorldImagery", attr="Esri",
    )

    any_overlay = False
    for field in fields:
        # Polygon outline
        folium.GeoJson(
            {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": field.polygon_geojson,
                    "properties": {"name": field.name},
                }],
            },
            style_function=lambda _: {
                "fillColor": "#ffffff", "color": "#ffffff",
                "weight": 2, "fillOpacity": 0.0,
            },
            tooltip=field.name,
        ).add_to(m)

        overlay = pick_overlay_for_week(
            conn, field.field_id, target_date.isoformat(), SEASON_TAG,
        )
        if overlay is None:
            continue
        kwargs = build_image_overlay_kwargs(field, overlay)
        if kwargs is None:
            continue
        folium.raster_layers.ImageOverlay(**kwargs).add_to(m)
        any_overlay = True

        # Small centroid marker with NDVI mean if we have a reading for this week
        readings = get_season_readings(
            conn, field.field_id, season_tag=SEASON_TAG, index_name="NDVI",
        )
        same_week = [r for r in readings if r.reading_date[:10] == target_date.isoformat()]
        if same_week and same_week[0].mean_value is not None:
            mean_val = same_week[0].mean_value
            folium.CircleMarker(
                location=[field.center_lat, field.center_lon],
                radius=6, color="#000", weight=1, fill=True,
                fill_color="#ffffff", fill_opacity=0.85,
                tooltip=f"{field.name}: NDVI {mean_val:.2f} ({overlay.image_type})",
            ).add_to(m)
        else:
            folium.CircleMarker(
                location=[field.center_lat, field.center_lon],
                radius=4, color="#666", weight=1, fill=True,
                fill_color="#ddd", fill_opacity=0.6,
                tooltip=f"{field.name}: no optical this week ({overlay.image_type})",
            ).add_to(m)

    if not any_overlay:
        st.caption(
            "No overlay tiles stored for this week yet. "
            "Run `python -m scripts.fetch_paddy_kharif --field-id <id>`."
        )

    # Fit bounds to union of selected fields
    all_bounds = []
    for f in fields:
        b = folium_bounds_for_field(f)
        all_bounds.extend(b)
    if all_bounds:
        lats = [b[0] for b in all_bounds]
        lons = [b[1] for b in all_bounds]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, width=None, height=600, returned_objects=[])


def _render_event_strip(conn: sqlite3.Connection, fields) -> None:
    """Horizontal event strip per field: T/H/! markers on a time axis."""
    rows = []
    for f in fields:
        events = get_paddy_events(conn, f.field_id, season_tag=SEASON_TAG)
        for e in events:
            marker, color = EVENT_MARKER.get(e.event_type, ("?", "#888"))
            rows.append({
                "field": f.name,
                "date": e.event_date,
                "event_type": e.event_type,
                "marker": marker,
                "color": color,
                "confidence": e.confidence,
                "evidence": ", ".join(
                    f"{k}={v}" for k, v in e.evidence.items()
                    if k not in ("rule",)
                )[:180],
            })
    if not rows:
        st.caption("No paddy events detected yet for the selected fields.")
        return

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    fig = px.scatter(
        df, x="date", y="field", symbol="event_type",
        color="event_type", text="marker",
        hover_data=["confidence", "evidence"],
        color_discrete_map={k: v[1] for k, v in EVENT_MARKER.items()},
    )
    fig.update_traces(marker=dict(size=16), textposition="middle center",
                      textfont=dict(color="white", size=10))
    fig.update_layout(
        height=max(140, 80 + 40 * len(df["field"].unique())),
        xaxis=dict(
            range=[
                pd.Timestamp(SEASON_START) - pd.Timedelta(days=3),
                pd.Timestamp(SEASON_END) + pd.Timedelta(days=3),
            ],
            title=None,
        ),
        yaxis=dict(title=None),
        margin=dict(l=20, r=20, t=20, b=30),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_paddy_timeline(conn: sqlite3.Connection) -> None:
    st.header("Paddy kharif 2025 -- timeline")
    st.caption(
        "Weekly slider from June 1 2025 to January 15 2026. "
        "NDVI overlays in clear weeks, RVI (SAR) overlays in monsoon weeks."
    )

    all_fields = get_all_fields(conn)
    if not all_fields:
        st.warning(
            "No fields registered. Add polygons via the **Fields** page first."
        )
        return

    field_options = {f.field_id: f.name for f in all_fields}
    selected_ids = st.multiselect(
        "Fields",
        options=list(field_options.keys()),
        default=list(field_options.keys())[:3],
        format_func=lambda fid: field_options[fid],
    )
    selected_fields = [f for f in all_fields if f.field_id in selected_ids]

    weeks = _weekly_slider_dates()
    slider_date = st.select_slider(
        "Week of",
        options=weeks,
        value=weeks[len(weeks) // 2],
        format_func=lambda d: d.strftime("%b %d, %Y"),
    )

    _render_map(conn, selected_fields, slider_date)
    st.divider()
    st.subheader("Phenology events")
    _render_event_strip(conn, selected_fields)
