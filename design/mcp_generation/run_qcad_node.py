from __future__ import annotations

from pathlib import Path

from design.state import CADlyGenerationState
from design.mcp_generation.qcad_dxf_generator import generate_dxf_from_graph_data


def run_qcad_node(state: CADlyGenerationState) -> CADlyGenerationState:
    graph_data = state.get("graph_data")

    if not graph_data:
        return {
            **state,
            "status": "qcad_generation_failed",
            "message": "graph_data is missing. Cannot generate QCAD DXF.",
        }

    out_dir = Path(state.get("qcad_output_dir", "outputs/qcad"))
    name = state.get("name", "qcad_floorplan")
    dxf_path = out_dir / f"{name}.dxf"

    try:
        result = generate_dxf_from_graph_data(
            graph_data=graph_data,
            output_path=str(dxf_path),
        )

        if not result.get("ok"):
            return {
                **state,
                "status": "qcad_generation_failed",
                "message": result.get("message", "QCAD DXF generation failed."),
                "qcad_generation_result": result,
            }

        return {
            **state,
            "status": "qcad_generation_success",
            "message": "QCAD/ezdxf floorplan generated successfully.",
            "dxf_path": result["dxf_path"],
            "qcad_dxf_path": result["dxf_path"],
            "qcad_generation_result": result,
            "qcad_layout": result.get("layout"),
        }

    except Exception as e:
        return {
            **state,
            "status": "qcad_generation_failed",
            "message": f"QCAD generation failed: {e}",
        }