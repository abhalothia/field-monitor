"""Inspect-plot diagnostic page.

Gives the extension agent everything needed to triage one plot:
  - A three-row signal stack (optical indices, SAR backscatter, RVI)
    with phenology windows shaded and detected events marked.
  - A within-field NDVI band histogram classified from the latest
    ndvi_overlay PNG -- high / medium / low hectares inside the field.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from PIL import Image
from plotly.subplots import make_subplots

from dashboard.pages.paddy_timeline import EVENT_MARKER
from src.models import FieldPolygon
from src.paddy_kharif.config import (
    HARVEST_WINDOW,
    PADDY_THRESHOLDS,
    REPRODUCTIVE_OFFSET_DAYS,
    TRANSPLANT_WINDOW,
    VEGETATIVE_OFFSET_DAYS,
)
from src.paddy_kharif.repository_paddy import (
    get_paddy_events,
    get_season_readings,
    list_overlays,
)


_OPTICAL_TRACES = [
    ("NDVI", "#2a9d8f"),
    ("NDRE", "#457b9d"),
    ("NDWI", "#1d3557"),
    ("LSWI", "#8ac6d1"),
]
_SAR_DB_TRACES = [
    ("S1_VV", "#6a5acd"),
    ("S1_VH", "#b8860b"),
]

_NDVI_THRESHOLD_LINES = [
    ("healthy", "#2a9d8f"),
    ("stress", "#d97b00"),
    ("severe", "#d94848"),
]

# NDVI overlay RGB ramp from evalscripts_paddy.imagery_paddy_ndvi_overlay.
# Scaled to 0-255 to match PIL's RGBA byte buffer.
_RAMP = np.array(
    [
        [0.05, 0.05, 0.05],  # dark gray  NDVI < 0.0
        [0.75, 0.15, 0.15],  # red        0.0-0.2
        [0.90, 0.50, 0.15],  # orange     0.2-0.4
        [0.95, 0.90, 0.20],  # yellow     0.4-0.6
        [0.40, 0.80, 0.20],  # light grn  0.6-0.8
        [0.10, 0.50, 0.10],  # dark grn   >= 0.8
    ],
    dtype=np.float32,
) * 255.0
_BAND_FOR_RAMP = ("low", "low", "low", "medium", "high", "high")


def render_inspect(conn: sqlite3.Connection, field: FieldPolygon | None) -> None:
    """Streamlit entry point: render the inspect-plot page."""
    if field is None:
        st.info("No field selected. Add one on the Fields page.")
        return

    st.header(f"Inspect: {field.name}")
    st.caption(
        f"{field.area_hectares:.2f} ha | "
        f"{field.center_lat:.4f}N, {field.center_lon:.4f}E | "
        f"field_id = {field.field_id}"
    )

    _render_signal_stack(conn, field)
    st.divider()
    _render_ndvi_histogram(conn, field)


# ---------------------------------------------------------------------------
# Section A: Plotly signal stack
# ---------------------------------------------------------------------------

def _render_signal_stack(conn: sqlite3.Connection, field: FieldPolygon) -> None:
    st.subheader("Signal stack")

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.45, 0.30, 0.25],
        subplot_titles=(
            "Optical indices (Sentinel-2 L2A)",
            "SAR backscatter (Sentinel-1, dB)",
            "SAR Radar Vegetation Index",
        ),
    )

    _plot_traces(fig, conn, field, _OPTICAL_TRACES, row=1)
    _plot_traces(fig, conn, field, _SAR_DB_TRACES, row=2)
    _plot_traces(fig, conn, field, [("S1_RVI", "#2f4f4f")], row=3)

    _add_ndvi_threshold_lines(fig)
    _shade_phenology_windows(fig, conn, field)
    _annotate_events(fig, conn, field)

    fig.update_yaxes(range=[-0.2, 1.0], row=1, col=1, title_text="Index value")
    fig.update_yaxes(range=[-25.0, -5.0], row=2, col=1, title_text="dB")
    fig.update_yaxes(range=[0.0, 1.0], row=3, col=1, title_text="RVI")
    fig.update_xaxes(
        range=[str(TRANSPLANT_WINDOW[0]), str(HARVEST_WINDOW[1])],
        row=3, col=1,
    )

    fig.update_layout(
        height=720,
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.12, x=0.0),
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def _plot_traces(
    fig: go.Figure,
    conn: sqlite3.Connection,
    field: FieldPolygon,
    traces: list[tuple[str, str]],
    row: int,
) -> None:
    for index_name, color in traces:
        readings = get_season_readings(
            conn, field.field_id, index_name=index_name,
        )
        readings = [r for r in readings if r.mean_value is not None]
        if not readings:
            continue
        fig.add_trace(
            go.Scatter(
                x=[r.reading_date for r in readings],
                y=[r.mean_value for r in readings],
                mode="lines+markers",
                name=index_name,
                line=dict(color=color, width=2),
                marker=dict(size=5),
            ),
            row=row, col=1,
        )


def _add_ndvi_threshold_lines(fig: go.Figure) -> None:
    ndvi = PADDY_THRESHOLDS["NDVI"]
    for attr, color in _NDVI_THRESHOLD_LINES:
        fig.add_hline(
            y=getattr(ndvi, attr),
            line_dash="dash", line_color=color, line_width=1,
            annotation_text=f"NDVI {attr}", annotation_position="right",
            annotation_font_size=10, annotation_font_color=color,
            row=1, col=1,
        )


def _shade_phenology_windows(
    fig: go.Figure,
    conn: sqlite3.Connection,
    field: FieldPolygon,
) -> None:
    transplant_date = _first_transplant_date(conn, field)

    if transplant_date is not None:
        veg_start = transplant_date + timedelta(days=VEGETATIVE_OFFSET_DAYS[0])
        veg_end = transplant_date + timedelta(days=VEGETATIVE_OFFSET_DAYS[1])
        rep_start = transplant_date + timedelta(days=REPRODUCTIVE_OFFSET_DAYS[0])
        rep_end = transplant_date + timedelta(days=REPRODUCTIVE_OFFSET_DAYS[1])
    else:
        veg_start, veg_end = date(2025, 7, 20), date(2025, 8, 20)
        rep_start, rep_end = date(2025, 8, 15), date(2025, 10, 15)

    _shade(fig, TRANSPLANT_WINDOW[0], TRANSPLANT_WINDOW[1], "#2a78b0", 0.08)
    _shade(fig, veg_start, veg_end, "#2a9d8f", 0.05)
    _shade(fig, rep_start, rep_end, "#d97b00", 0.08)
    _shade(fig, HARVEST_WINDOW[0], HARVEST_WINDOW[1], "#8b5a2b", 0.08)


def _shade(
    fig: go.Figure, x0: date, x1: date, color: str, alpha: float,
) -> None:
    fig.add_vrect(
        x0=str(x0), x1=str(x1),
        fillcolor=color, opacity=alpha,
        layer="below", line_width=0,
    )


def _first_transplant_date(
    conn: sqlite3.Connection, field: FieldPolygon,
) -> date | None:
    events = get_paddy_events(
        conn, field.field_id, event_type="transplanting",
    )
    if not events:
        return None
    try:
        return date.fromisoformat(events[0].event_date)
    except (TypeError, ValueError):
        return None


def _annotate_events(
    fig: go.Figure, conn: sqlite3.Connection, field: FieldPolygon,
) -> None:
    ndvi_readings = get_season_readings(
        conn, field.field_id, index_name="NDVI",
    )
    ndvi_by_date = {
        r.reading_date: r.mean_value
        for r in ndvi_readings if r.mean_value is not None
    }

    for ev in get_paddy_events(conn, field.field_id):
        if ev.event_type not in EVENT_MARKER:
            continue
        marker, color = EVENT_MARKER[ev.event_type]
        y = ndvi_by_date.get(ev.event_date, 0.5)
        fig.add_annotation(
            x=ev.event_date, y=y,
            text=f"<b>{marker}</b>",
            showarrow=False,
            font=dict(color=color, size=16),
            bgcolor="rgba(255,255,255,0.75)",
            bordercolor=color, borderwidth=1,
            row=1, col=1,
        )


# ---------------------------------------------------------------------------
# Section B: Within-field NDVI band histogram
# ---------------------------------------------------------------------------

def _render_ndvi_histogram(
    conn: sqlite3.Connection, field: FieldPolygon,
) -> None:
    st.subheader("Within-field NDVI distribution")

    overlays = [
        o for o in list_overlays(conn, field.field_id)
        if o.image_type == "ndvi_overlay"
    ]
    if not overlays:
        st.info(
            "No NDVI overlay available yet. Run "
            f"`python -m scripts.fetch_paddy_kharif "
            f"--field-id {field.field_id} --year 2025` on a machine "
            "with Sentinel Hub credentials to populate."
        )
        return

    latest = max(overlays, key=lambda o: o.image_date)
    path = Path(latest.file_path)
    if not path.exists():
        st.warning(
            f"Overlay record points to missing file: `{path}`. "
            "Re-run the fetcher to regenerate."
        )
        return

    img = Image.open(path).convert("RGBA")
    arr = np.asarray(img, dtype=np.float32)
    valid_mask = arr[..., 3] > 0
    rgb = arr[valid_mask][:, :3]
    if rgb.size == 0:
        st.info(
            "Latest overlay has no cloud-free pixels inside the field "
            "boundary. Try an earlier date or wait for the next revisit."
        )
        return

    dists = np.linalg.norm(rgb[:, None, :] - _RAMP[None, :, :], axis=2)
    ramp_idx = dists.argmin(axis=1)

    totals = {"high": 0, "medium": 0, "low": 0}
    for i in range(len(_RAMP)):
        totals[_BAND_FOR_RAMP[i]] += int((ramp_idx == i).sum())
    n_valid = sum(totals.values())
    ha = field.area_hectares

    def pct(band: str) -> float:
        return 100.0 * totals[band] / n_valid

    def ha_for(band: str) -> float:
        return ha * totals[band] / n_valid

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "High (NDVI >= 0.6)",
        f"{ha_for('high'):.2f} ha",
        f"{pct('high'):.0f}% of field",
    )
    c2.metric(
        "Medium (0.4-0.6)",
        f"{ha_for('medium'):.2f} ha",
        f"{pct('medium'):.0f}% of field",
    )
    c3.metric(
        "Low / bare (< 0.4)",
        f"{ha_for('low'):.2f} ha",
        f"{pct('low'):.0f}% of field",
    )

    bar = go.Figure()
    bar.add_trace(go.Bar(
        x=[pct("high")], y=[""], orientation="h",
        marker_color="#2a9d8f",
        text=[f"High {pct('high'):.0f}%"],
        textposition="inside", hoverinfo="x", name="High",
    ))
    bar.add_trace(go.Bar(
        x=[pct("medium")], y=[""], orientation="h",
        marker_color="#d97b00",
        text=[f"Medium {pct('medium'):.0f}%"],
        textposition="inside", hoverinfo="x", name="Medium",
    ))
    bar.add_trace(go.Bar(
        x=[pct("low")], y=[""], orientation="h",
        marker_color="#d94848",
        text=[f"Low {pct('low'):.0f}%"],
        textposition="inside", hoverinfo="x", name="Low",
    ))
    bar.update_layout(
        barmode="stack",
        height=70,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(range=[0, 100], visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    st.plotly_chart(bar, use_container_width=True)

    st.caption(
        f"Classified from overlay dated {latest.image_date} -- "
        f"{n_valid:,} valid pixels inside field boundary."
    )
