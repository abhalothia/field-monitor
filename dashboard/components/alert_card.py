"""Alert display components."""

import streamlit as st

from src.models import AnomalyAlert


SEVERITY_ICONS = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
}


def render_alert_card(alert: AnomalyAlert) -> None:
    """Render a single alert as a styled card."""
    icon = SEVERITY_ICONS.get(alert.severity, "")
    severity_upper = alert.severity.upper()

    st.markdown(
        f"**{icon} [{severity_upper}]** {alert.alert_date} -- "
        f"**{alert.index_name}** ({alert.alert_type.replace('_', ' ')})"
    )
    st.caption(alert.message)


def render_alert_list(
    alerts: list[AnomalyAlert],
    max_display: int = 5,
) -> None:
    """Render a list of recent alerts."""
    if not alerts:
        st.success("No active alerts")
        return

    for alert in alerts[:max_display]:
        render_alert_card(alert)
        st.divider()

    if len(alerts) > max_display:
        st.caption(f"... and {len(alerts) - max_display} more alerts")
