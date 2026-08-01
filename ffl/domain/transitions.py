WORK_TRANSITIONS = {
    "planned": {"in_progress", "blocked", "cancelled"},
    "in_progress": {"blocked", "submitted", "cancelled"},
    "blocked": {"in_progress", "cancelled"},
    "submitted": {"accepted", "rejected"},
    "rejected": {"in_progress", "cancelled"},
    "accepted": set(),
    "cancelled": set(),
}

EXCEPTION_TRANSITIONS = {
    "reported": {"triaged"},
    "triaged": {"owned", "accepted_risk"},
    "owned": {"mitigated", "accepted_risk"},
    "mitigated": {"monitoring"},
    "monitoring": {"resolved", "reopened"},
    "resolved": {"reopened"},
    "accepted_risk": {"reopened"},
    "reopened": {"triaged"},
}
