"""Health score gauge visualization."""

import plotly.graph_objects as go
import streamlit as st


def render_health_gauge(
    score: float,
    title: str = "Field health risk",
    height: int = 250,
) -> None:
    """Render a gauge chart showing 0-100 risk score."""
    if score < 25:
        color = "#2ca02c"
        label = "LOW"
    elif score < 50:
        color = "#f0ad4e"
        label = "MODERATE"
    elif score < 75:
        color = "#d9534f"
        label = "HIGH"
    else:
        color = "#8b0000"
        label = "CRITICAL"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": f"  {label}", "font": {"size": 24}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 25], "color": "rgba(44, 160, 44, 0.15)"},
                {"range": [25, 50], "color": "rgba(240, 173, 78, 0.15)"},
                {"range": [50, 75], "color": "rgba(217, 83, 79, 0.15)"},
                {"range": [75, 100], "color": "rgba(139, 0, 0, 0.15)"},
            ],
            "threshold": {
                "line": {"color": "black", "width": 2},
                "thickness": 0.75,
                "value": score,
            },
        },
    ))

    fig.update_layout(
        title={"text": title, "font": {"size": 16}},
        height=height,
        margin=dict(l=30, r=30, t=50, b=10),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_risk_breakdown(
    pest: float,
    disease: float,
    water: float,
    nutrient: float,
) -> None:
    """Render a horizontal bar chart of risk categories."""

    def _severity_label(val: float) -> str:
        if val < 25:
            return "LOW"
        elif val < 50:
            return "MODERATE"
        elif val < 75:
            return "HIGH"
        return "CRITICAL"

    def _color(val: float) -> str:
        if val < 25:
            return "#2ca02c"
        elif val < 50:
            return "#f0ad4e"
        elif val < 75:
            return "#d9534f"
        return "#8b0000"

    categories = ["Pest", "Disease", "Water stress", "Nutrient"]
    values = [pest, disease, water, nutrient]

    cols = st.columns(4)
    for col, cat, val in zip(cols, categories, values):
        with col:
            st.metric(cat, f"{val:.0f}", _severity_label(val))
