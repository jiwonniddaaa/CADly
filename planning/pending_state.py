# planning/pending_state.py
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

PendingAction = Literal[
    "none",
    "area_decision",
    "area_mode",
    "manual_area_input",
    "concept_confirmation",
]

PENDING_NONE: PendingAction = "none"

VALID_PENDING_ACTIONS = frozenset(
    {
        "none",
        "area_decision",
        "area_mode",
        "manual_area_input",
        "concept_confirmation",
    }
)

# 레거시 bool → enum (우선순위: 라우터와 동일)
_LEGACY_BOOL_TO_PENDING: tuple[tuple[str, PendingAction], ...] = (
    ("awaiting_manual_area_input", "manual_area_input"),
    ("area_decision_pending", "area_decision"),
    ("area_mode_pending", "area_mode"),
    ("awaiting_concept_confirmation", "concept_confirmation"),
)

_LEGACY_PENDING_KEYS = frozenset(key for key, _ in _LEGACY_BOOL_TO_PENDING)


def normalize_pending_action(state: Dict[str, Any]) -> PendingAction:
    action = state.get("pending_action")
    if action in VALID_PENDING_ACTIONS:
        return action  # type: ignore[return-value]

    for legacy_key, pending_value in _LEGACY_BOOL_TO_PENDING:
        if state.get(legacy_key):
            return pending_value
    return PENDING_NONE


def is_pending(state: Dict[str, Any], *actions: PendingAction) -> bool:
    current = normalize_pending_action(state)
    if not actions:
        return current != PENDING_NONE
    return current in actions


def set_pending(action: PendingAction) -> Dict[str, PendingAction]:
    return {"pending_action": action}


def clear_pending() -> Dict[str, PendingAction]:
    return {"pending_action": PENDING_NONE}


def strip_legacy_pending_keys(state: Dict[str, Any]) -> None:
    for key in _LEGACY_PENDING_KEYS:
        state.pop(key, None)
    state.pop("design_confirmation", None)


def migrate_pending_fields(state: Dict[str, Any]) -> Dict[str, Any]:
    """세션 blob의 레거시 bool을 pending_action으로 정규화합니다."""
    migrated = dict(state)
    migrated["pending_action"] = normalize_pending_action(migrated)
    strip_legacy_pending_keys(migrated)
    return migrated


def route_for_pending(state: Dict[str, Any]) -> Optional[str]:
    action = normalize_pending_action(state)
    if action == "manual_area_input":
        return "extract_requirements"
    if action in ("area_decision", "area_mode"):
        return "planning_agent"
    if action == "concept_confirmation":
        return "reference_agent"
    return None


def reference_awaiting_from_pending(state: Dict[str, Any]) -> bool:
    return normalize_pending_action(state) == "concept_confirmation"


def pending_from_reference_awaiting(awaiting: bool) -> PendingAction:
    return "concept_confirmation" if awaiting else PENDING_NONE


def resolve_pending_after_planning_agent(
    result: Dict[str, Any],
    state: Dict[str, Any],
) -> PendingAction:
    if result.get("next_step") == "build_design_payload":
        return PENDING_NONE

    if "pending_action" in result:
        action = result.get("pending_action", PENDING_NONE)
        return action if action in VALID_PENDING_ACTIONS else PENDING_NONE

    if result.get("awaiting_manual_area_input"):
        return "manual_area_input"
    if result.get("area_decision_pending"):
        return "area_decision"
    if result.get("area_mode_pending"):
        return "area_mode"
    return normalize_pending_action(state)
