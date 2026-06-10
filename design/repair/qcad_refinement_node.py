from __future__ import annotations

from pathlib import Path

from design.qcad_repair.orchestrator import run_qcad_repair_sync
from mcp_server.tools import apply_plan_python


def qcad_refinement_node(state):
    dxf_path = state.get("dxf_path")
    room_label_path = state.get("room_label_path")

    output_dir = (
        state.get("qcad_output_dir")
        or state.get("out_dir")
    )

    if not output_dir and dxf_path:
        output_dir = str(Path(dxf_path).resolve().parent)

    if not dxf_path:
        return {
            **state,
            "status": "repair_failed",
            "repair_route": "end",
            "message": "QCAD refinement skipped: dxf_path is missing.",
            "validation_errors": ["QCAD refinement skipped: dxf_path is missing."],
            "qcad_repair_error": "dxf_path is missing.",
        }

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    name = state.get("name") or Path(dxf_path).stem

    # 1. Rule-based CAD style enhancement 먼저 강제 실행
    enhanced_dxf_path = output_dir_path / f"{name}_cad_enhanced.dxf"

    enhance_plan = {
        "actions": [
            {
                "tool": "enhance_cad_style",
                "params": {
                    "scale_factor": 100,
                    "title": "FLOOR PLAN",
                    "scale": "1:60",
                    "drawing_no": "A-001",
                    "add_fixtures": False,
                },
                "wall_offset": 1.2,
                "dimension_offset": 7.0,
                "dimension_text_height": 2.5,
                "title_text_height": 2.5,
            }
        ]
    }

    enhance_result = apply_plan_python(
        input_dxf=dxf_path,
        output_dxf=str(enhanced_dxf_path),
        refinement_plan=enhance_plan,
        room_label_json=room_label_path,
    )

    repair_history = state.get("repair_history", []) or []

    repair_history.append(
        {
            "action": "RULE_BASED_CAD_ENHANCEMENT",
            "status": "success" if enhanced_dxf_path.exists() else "failed",
            "input_dxf": dxf_path,
            "output_dxf": str(enhanced_dxf_path),
            "changed": enhance_result.get("changed"),
            "validation": enhance_result.get("validation"),
        }
    )

    # rule-based enhancement가 실패하면 여기서 종료
    if not enhanced_dxf_path.exists():
        return {
            **state,
            "status": "repair_failed",
            "repair_route": "end",
            "message": "Rule-based CAD enhancement failed.",
            "repair_history": repair_history,
            "validation_errors": ["Rule-based CAD enhancement failed."],
            "qcad_repair_error": "Rule-based CAD enhancement failed.",
        }

    # 2. Claude-MCP refinement는 enhanced DXF를 대상으로 실행
    result = run_qcad_repair_sync(
        input_dxf=str(enhanced_dxf_path),
        room_label_json=room_label_path,
        output_dir=str(output_dir_path),
        backend="python",
    )

    repair_history.append(
        {
            "action": "QCAD_REFINEMENT",
            "status": result.get("status"),
            "refined_dxf_path": result.get("refined_dxf_path"),
            "refined_svg_path": result.get("refined_svg_path"),
            "report": result.get("qcad_repair_report"),
        }
    )

    if result.get("status") == "qcad_repair_failed":
        return {
            **state,
            "status": "repair_failed",
            "repair_route": "end",
            "message": result.get("message", "QCAD refinement failed."),
            "repair_history": repair_history,
            "validation_errors": [result.get("message", "QCAD refinement failed.")],
            "qcad_repair_error": result.get("message", "QCAD refinement failed."),
        }

    refined_dxf_path = result.get("refined_dxf_path") or str(enhanced_dxf_path)
    refined_svg_path = result.get("refined_svg_path") or state.get("svg_path")

    return {
        **state,
        "status": "repair_success",
        "repair_route": "end",
        "message": "Rule-based CAD enhancement and QCAD refinement completed.",
        "repair_history": repair_history,

        # 최종 결과 경로를 최신 refined 결과로 교체
        "dxf_path": refined_dxf_path,
        "svg_path": refined_svg_path,

        "qcad_output_dir": str(output_dir_path),
        "qcad_dxf_path": refined_dxf_path,

        "validation_errors": [],
        "verification_warnings": state.get("verification_warnings", []),
    }