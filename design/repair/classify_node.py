from __future__ import annotations

from typing import List

from design.state import CADlyGenerationState


def _has_any_keyword(messages: List[str], keywords: List[str]) -> bool:
    joined = "\n".join(messages).lower()
    return any(keyword.lower() in joined for keyword in keywords)


def _append_repair_history(
    state: CADlyGenerationState,
    *,
    action: str,
    reason: str,
) -> List[dict]:
    repair_history = state.get("repair_history", []) or []

    repair_history.append(
        {
            "action": action,
            "reason": reason,
            "status_before": state.get("status"),
            "errors": state.get("validation_errors", []) or [],
            "warnings": state.get("verification_warnings", []) or [],
            "resample_count": state.get("resample_count", 0),
            "postprocess_count": state.get("postprocess_count", 0),
        }
    )

    return repair_history


def classify_node(state: CADlyGenerationState) -> CADlyGenerationState:
    status = state.get("status")
    errors = state.get("validation_errors", []) or []
    warnings = state.get("verification_warnings", []) or []

    resample_count = int(state.get("resample_count", 0))
    max_resamples = int(state.get("max_resamples", 2))

    postprocess_count = int(state.get("postprocess_count", 0))
    max_postprocesses = int(state.get("max_postprocesses", 1))

    all_messages = errors + warnings

    # 1. Verification passed.
    if status == "verified":
        return {
            **state,
            "status": "repair_success",
            "repair_route": "final_node",
            "message": "Generated floorplan verification passed.",
            "repair_history": _append_repair_history(
                state,
                action="ACCEPT",
                reason="verification_passed",
            ),
        }

    # 2. Unexpected status.
    if status != "verification_failed":
        return {
            **state,
            "status": "repair_failed",
            "repair_route": "final_node",
            "message": f"Unexpected verification status: {status}",
            "repair_history": _append_repair_history(
                state,
                action="FAILED",
                reason=f"unexpected_status:{status}",
            ),
        }

    # 3. File/export-level errors usually require resampling.
    file_level_error = _has_any_keyword(
        errors,
        [
            "file not found",
            "file is empty",
            "cannot be parsed",
            "contains no drawable geometry",
            "modelspace contains no entities",
            "contains no geometric entities",
        ],
    )

    if file_level_error:
        if resample_count < max_resamples:
            return {
                **state,
                "status": "needs_resample",
                "repair_route": "resample_node",
                "message": "Generated files are invalid. Resampling will be attempted.",
                "repair_history": _append_repair_history(
                    state,
                    action="RESAMPLE",
                    reason="file_or_export_level_error",
                ),
            }

        return {
            **state,
            "status": "repair_failed",
            "repair_route": "final_node",
            "message": "Generated files are still invalid after maximum resampling attempts.",
            "repair_history": _append_repair_history(
                state,
                action="FAILED",
                reason="max_retries_exceeded:file_or_export_level_error",
            ),
        }

    # 4. Geometry-level serious errors also require resampling.
    geometry_error = _has_any_keyword(
        all_messages,
        [
            "invalid polygon",
            "fewer than 3 polygon points",
            "invalid bbox",
            "bbox contains non-finite values",
            "bbox area is zero",
            "polygon area is zero",
            "marked as degenerate",
            "missing coordinate attributes",
        ],
    )

    if geometry_error:
        if resample_count < max_resamples:
            return {
                **state,
                "status": "needs_resample",
                "repair_route": "resample_node",
                "message": "Generated room geometry is invalid. Resampling will be attempted.",
                "repair_history": _append_repair_history(
                    state,
                    action="RESAMPLE",
                    reason="room_geometry_error",
                ),
            }

        return {
            **state,
            "status": "repair_failed",
            "repair_route": "final_node",
            "message": "Room geometry remains invalid after maximum resampling attempts.",
            "repair_history": _append_repair_history(
                state,
                action="FAILED",
                reason="max_retries_exceeded:room_geometry_error",
            ),
        }

    # 5. Label, text, SVG attribute, minor metadata issues can be postprocessed.
    postprocessable_issue = _has_any_keyword(
        all_messages,
        [
            "room label",
            "missing input room ids",
            "missing input room types",
            "contains no text",
            "neither viewbox nor width/height",
        ],
    )

    if postprocessable_issue:
        if postprocess_count < max_postprocesses:
            return {
                **state,
                "status": "needs_postprocess",
                "repair_route": "postprocess_node",
                "message": "Minor drawing metadata issues found. Postprocessing will be attempted.",
                "repair_history": _append_repair_history(
                    state,
                    action="POSTPROCESS",
                    reason="postprocessable_issue",
                ),
         }
        
        return {
            **state,
            "status": "repair_failed",
            "repair_route": "final_node",
            "message": "Minor drawing metadata issues remain after maximum postprocessing attempts.",
            "repair_history": _append_repair_history(
                state,
                action="FAILED",
                reason="max_retries_exceeded:postprocessable_issue",
            ),
        }
    


    # 6. Warnings only can be accepted or postprocessed.
    if not errors and warnings:
        return {
            **state,
            "status": "repair_success_with_warnings",
            "repair_route": "final_node",
            "message": "Generated floorplan accepted with warnings.",
            "repair_history": _append_repair_history(
                state,
                action="ACCEPT",
                reason="warnings_only",
            ),
        }

    # 7. Unknown failure: resample first, then fail.
    if resample_count < max_resamples:
        return {
            **state,
            "status": "needs_resample",
            "repair_route": "resample_node",
            "message": "Unknown verification failure. Resampling will be attempted.",
            "repair_history": _append_repair_history(
                state,
                action="RESAMPLE",
                reason="unknown_failure",
            ),
        }

    return {
        **state,
        "status": "repair_failed",
        "repair_route": "final_node",
        "message": "Verification failed after maximum repair attempts.",
        "repair_history": _append_repair_history(
            state,
            action="FAILED",
            reason="max_retries_exceeded:unknown_failure",
        ),  
    }