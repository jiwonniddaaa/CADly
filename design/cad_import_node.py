from __future__ import annotations

from design.state import CADlyGenerationState
from design.mcp_client import call_cad_import_tool

def cad_import_node(state: CADlyGenerationState) -> CADlyGenerationState:
    dxf_path = state.get("dxf_path")
    target_cad = state.get("target_cad", "rhino")

    if not dxf_path:
        return {
            **state,
            "status": "cad_import_failed",
            "message": "DXF path is missing.",
        }

    if target_cad == "autocad":
        result = call_cad_import_tool(
            "import_to_autocad",
            {
                "dxf_path": dxf_path,
            },
        )

    elif target_cad == "rhino":
        result = call_cad_import_tool(
            "import_to_rhino",
            {
                "dxf_path": dxf_path,
                "rhino_exe_path": state.get(
                    "rhino_exe_path",
                    "/Applications/Rhino 8.app",
                ),
            },
        )
    
    elif target_cad == "qcad":
        result = call_cad_import_tool(
            "import_to_qcad",
            {
                "dxf_path": dxf_path,
                "qcad_app_path": state.get(
                    "qcad_app_path",
                    "/Applications/QCAD.app",
                ),
            },
        )

    else:
        return {
            **state,
            "status": "cad_import_failed",
            "message": f"Unsupported CAD target: {target_cad}",
        }

    return {
        **state,
        "status": "cad_imported" if result.get("ok") else "cad_import_failed",
        "cad_import_result": result,
        "message": result.get("message", "CAD import completed."),
    }