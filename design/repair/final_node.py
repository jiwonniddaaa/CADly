from __future__ import annotations

from design.state import CADlyGenerationState


def final_node(state: CADlyGenerationState) -> CADlyGenerationState:
    status = state.get("status")

    if status in {
        "repair_success",
        "repair_success_with_warnings",
    }:
        return {
            **state,
            "status": status,
            "repair_route": "end",
            "message": state.get(
                "message",
                "Floorplan verification passed.",
            ),
        }

    if status in {
        "repair_failed",
        "verification_failed",
        "postprocess_failed",
        "resample_failed",
        "resampling_failed",
        "sampling_failed",
        "error",
    }:
        return {
            **state,
            "status": "repair_failed",
            "repair_route": "end",
            "message": state.get(
                "message",
                "Floorplan repair failed.",
            ),
        }

    return {
        **state,
        "status": "repair_failed",
        "repair_route": "end",
        "message": state.get(
            "message",
            f"Repair agent ended with unexpected status: {status}",
        ),
    }