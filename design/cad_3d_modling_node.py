from __future__ import annotations

from design.state import CADlyGenerationState
from design.mcp_client import call_cad_import_tool


def model3d_node(state: CADlyGenerationState) -> CADlyGenerationState:
    cadly_schema = state.get("cadly_schema")
    target_3d = state.get("target_3d", "rhino")
    enable_3d_modeling = state.get("enable_3d_modeling", False)

    if not enable_3d_modeling:
        return {
            **state,
            "status": "model3d_skipped",
            "message": "3D modeling was skipped.",
        }

    if not cadly_schema:
        return {
            **state,
            "status": "model3d_failed",
            "message": "cadly_schema is missing.",
        }

    if target_3d != "rhino":
        return {
            **state,
            "status": "model3d_failed",
            "message": f"Unsupported 3D target: {target_3d}",
        }

    result = call_cad_import_tool(
        "create_rhino_3d_model",
        {
            "cadly_schema": cadly_schema,
            "output_path": state.get(
                "model3d_output_path",
                "outputs/model3d/generated_model.3dm",
            ),
            "wall_height": state.get("wall_height", 3000),
            "floor_thickness": state.get("floor_thickness", 200),
        },
    )

    return {
        **state,
        "status": "model3d_generated" if result.get("ok") else "model3d_failed",
        "model3d_result": result,
        "model3d_path": result.get("output_path"),
        "message": result.get("message", "3D modeling completed."),
    }