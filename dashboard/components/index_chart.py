"""Plotly time-series chart for vegetation indices."""

import plotly.graph_objects as go
import streamlit as st

from src.indices import INDEX_CATALOG
from src.models import AnomalyAlert, IndexReading


def render_index_chart(
    readings: list[IndexReading],
    index_name: str,
    alerts: list[AnomalyAlert] | None = None,
    show_thresholds: bool = True,
    height: int = 400,
) -> None:
    """Render a Plotly time-series chart for one index."""
    if not readings:
        st.info(f"No data available for {index_name}")
        return

    info = INDEX_CATALOG.get(index_name)
    dates = [r.reading_date for r in readings]
    means = [r.mean_value for r in readings]
    mins = [r.min_value for r in readings]
    maxs = [r.max_value for r in readings]

    fig = go.Figure()

    # Min/max band
    if any(v is not None for v in mins) and any(v is not None for v in maxs):
        fig.add_trace(go.Scatter(
            x=dates + dates[::-1],
            y=[v if v is not None else 0 for v in maxs]
            + [v if v is not None else 0 for v in mins][::-1],
            fill="toself",
            fillcolor=f"rgba(100,100,100,0.1)",
            line=dict(color="rgba(0,0,0,0)"),
            name="Min/Max range",
            hoverinfo="skip",
        ))

    # Mean line
    color = info.color if info else "#1f77b4"
    fig.add_trace(go.Scatter(
        x=dates, y=means,
        mode="lines+markers",
        name=f"{index_name} (mean)",
        line=dict(color=color, width=2),
        marker=dict(size=5),
    ))

    # Threshold lines
    if show_thresholds and info:
        fig.add_hline(
            y=info.thresholds.healthy, line_dash="dash",
            line_color="green", opacity=0.5,
            annotation_text="Healthy",
            annotation_position="bottom right",
        )
        fig.add_hline(
            y=info.thresholds.stress, line_dash="dash",
            line_color="orange", opacity=0.5,
            annotation_text="Stress",
            annotation_position="bottom right",
        )
        fig.add_hline(
            y=info.thresholds.severe, line_dash="dash",
            line_color="red", opacity=0.5,
            annotation_text="Severe",
            annotation_position="bottom right",
        )

    # Anomaly markers
    if alerts:
        alert_dates = [a.alert_date for a in alerts if a.index_name == index_name]
        alert_values = [a.current_value for a in alerts if a.index_name == index_name]
        alert_msgs = [a.message for a in alerts if a.index_name == index_name]

        if alert_dates:
            fig.add_trace(go.Scatter(
                x=alert_dates, y=alert_values,
                mode="markers",
                name="Anomalies",
                marker=dict(color="red", size=10, symbol="diamond"),
                text=alert_msgs,
                hoverinfo="text",
            ))

    title = info.display_name if info else index_name
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Index value",
        height=height,
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)


def render_multi_index_chart(
    all_readings: dict[str, list[IndexReading]],
    height: int = 400,
) -> None:
    """Render all indices overlaid on one chart (normalized 0-1)."""
    fig = go.Figure()

    for index_name, readings in all_readings.items():
        if not readings:
            continue

        info = INDEX_CATALOG.get(index_name)
        dates = [r.reading_date for r in readings]
        means = [r.mean_value for r in readings if r.mean_value is not None]
        valid_dates = [
            r.reading_date for r in readings if r.mean_value is not None
        ]

        if not means:
            continue

        # Normalize to 0-1 range
        vmin, vmax = min(means), max(means)
        span = vmax - vmin if vmax > vmin else 1.0
        normalized = [(v - vmin) / span for v in means]

        color = info.color if info else "#999"
        fig.add_trace(go.Scatter(
            x=valid_dates, y=normalized,
            mode="lines",
            name=index_name,
            line=dict(color=color, width=2),
        ))

    fig.update_layout(
        title="All indices (normalized)",
        xaxis_title="Date",
        yaxis_title="Normalized value (0-1)",
        height=height,
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        template="plotly_white",
    )

    st.plotly_chart(fig, use_container_width=True)
