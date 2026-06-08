from __future__ import annotations

from design.state import CADlyGenerationState
from design.sampling_node import run_sampling


def resample_node(state: CADlyGenerationState) -> CADlyGenerationState:
    resample_count = int(state.get("resample_count", 0)) + 1

    previous_seed = int(state.get("seed", 42))
    next_seed = previous_seed + resample_count

    base_name = state.get("name", "floorplan")
    resample_name = f"{base_name}_resample_{resample_count:02d}"

    sampling_state = {
        **state,
        "base_name": base_name,
        "name": resample_name,

        "seed": next_seed,
        "resample_count": resample_count,
        "status": "ready_for_sampling",

        # 이전 검증 결과는 새 샘플링에 섞이지 않게 초기화
        "validation_errors": [],
        "verification_warnings": [],
    }

    result = run_sampling(sampling_state)

    if result.get("status") != "completed":
        return {
            **result,
            "status": "resample_failed",
            "resample_count": resample_count,
            "message": result.get("message", "Resampling failed before verification."),
            "repair_route": "final_node",
            "seed": next_seed,
            "validation_errors": result.get("validation_errors", ["Resampling failed before verification."]),
            "verification_warnings": result.get("verification_warnings", []),
        }

    return {
        **result,
        "status": "completed",
        "resample_count": resample_count,
        "message": "Resampling completed. Verification will run again.",
        "repair_route": "verification_node",
        "seed": next_seed,
        "validation_errors": [],
        "verification_warnings": [],
    }