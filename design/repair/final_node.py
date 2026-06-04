from __future__ import annotations

from design.state import CADlyGenerationState


def final_node(state: CADlyGenerationState) -> CADlyGenerationState:
    repair_action = state.get("repair_action")

    if repair_action == "ACCEPT":
        return {
            **state,
            "status": "repair_success",
            "repair_status": "repair_success",
            "message": "Floorplan passed verification and is ready for final output.",
        }

    if state.get("repair_status") == "repair_success":
        return {
            **state,
            "status": "repair_success",
            "message": "Floorplan repaired and verified successfully.",
        }

    return {
        **state,
        "status": "repair_failed",
        "repair_status": "repair_failed",
        "message": state.get(
            "message",
            "Floorplan repair failed after verification and retry attempts.",
        ),
    }