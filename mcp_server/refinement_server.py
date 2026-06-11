from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from mcp_server.tools import summarize_dxf, validate_dxf, apply_plan_python, render_svg_python

SERVER_DIR = Path(__file__).resolve().parent
SCRIPT_TEMPLATE = SERVER_DIR / "scripts" / "refinement_plan_template.js"

mcp = FastMCP("qcad-refinement-mcp")


def _run_qcad_script(input_dxf: str, output_dxf: str, room_label_json: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    qcad_bin = os.environ.get("QCAD_BIN")
    if not qcad_bin:
        raise RuntimeError("QCAD_BIN is not set. Set it to your QCAD executable path or use backend='python'.")
    if not Path(qcad_bin).exists():
        raise RuntimeError(f"QCAD_BIN does not exist: {qcad_bin}")

    template = SCRIPT_TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "__INPUT_DXF__": json.dumps(str(Path(input_dxf).resolve())),
        "__OUTPUT_DXF__": json.dumps(str(Path(output_dxf).resolve())),
        "__ROOM_LABEL_JSON__": json.dumps(str(Path(room_label_json).resolve())),
        "__PLAN_JSON__": json.dumps(json.dumps(plan)),
    }
    script = template
    for key, value in replacements.items():
        script = script.replace(key, value)

    Path(output_dxf).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        temp_script = f.name

    cmd = [qcad_bin, "-no-gui", "-allow-multiple-instances", "-autostart", temp_script]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    return {
        "backend": "qcad",
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "output_dxf": str(Path(output_dxf).resolve()),
        "success": proc.returncode == 0 and Path(output_dxf).exists(),
    }


@mcp.tool()
def inspect_dxf(input_dxf: str) -> Dict[str, Any]:
    """Inspect a DXF text file and return entity/layer/bbox summary."""
    return summarize_dxf(input_dxf)


@mcp.tool()
def validate_geometry(input_dxf: str, room_label_json: Optional[str] = None) -> Dict[str, Any]:
    """Validate the current DXF enough for refinement-loop testing."""
    return validate_dxf(input_dxf, room_label_json)


@mcp.tool()
def apply_refinement_plan(
    input_dxf: str,
    output_dxf: str,
    room_label_json: str,
    plan_json: str,
    backend: str = "qcad",
) -> Dict[str, Any]:
    """
    Apply a refinement plan to a DXF floorplan.

    The plan_json must be a JSON object with an "actions" list.

    This tool can be used for:
    1. broad rule-based CAD-style enhancement
    2. small cleanup and geometry repair

    Important pipeline policy:
    - If the DXF already contains CAD-style helper layers such as WALL, DOOR, WINDOW, or DIMENSION,
      do not call enhance_cad_style again.
    - Do not add title blocks.
    - Do not add room area labels.
    - Do not add fixtures unless explicitly requested.
    - Do not duplicate room labels, doors, windows, or dimensions.

    Supported actions:
    - enhance_cad_style:
      Adds CAD-style wall outlines, simple doors, simple windows, and basic dimensions.
      Use this only when the drawing is still a simple HouseDiffusion-style layout.

    - normalize_layers:
      Safely normalize helper layers.
      Do not destroy meaningful room layers such as living_room, kitchen, bedroom, bathroom.

    - align_walls:
      Align nearly horizontal or vertical LINE entities when off-axis wall issues are detected.

    - add_room_labels:
      Add room labels only when room labels are missing.

    - add_wall_outline:
      Add wall-like outline lines.

    - add_simple_doors:
      Add simple door symbols.

    - add_simple_windows:
      Add simple window symbols.

    - add_basic_dimensions:
      Add basic exterior dimensions.

    - add_basic_fixtures:
      Add simple fixtures only when explicitly requested.

    - remove_tiny_lines:
      Remove zero-length or nearly zero-length LINE entities.

    - normalize_text_size:
      Normalize text height for readability.

    - clean_cad_layers:
      Clean helper entity layers without changing room-type layers.

    - remove_duplicate_elements:
      Remove exact duplicate LINE entities.

    Recommended plan for an already enhanced DXF with no repair needed:
    {
      "actions": []
    }

    Recommended cleanup plan for an already enhanced DXF:
    {
      "actions": [
        {"tool": "remove_tiny_lines", "params": {"min_length": 0.5}},
        {"tool": "normalize_text_size", "params": {}},
        {"tool": "clean_cad_layers", "params": {}},
        {"tool": "remove_duplicate_elements", "params": {}}
      ]
    }

    backend="qcad" executes QCAD autostart JS.
    backend="python" uses the Python fallback implementation.
    """
    plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
    if backend == "qcad":
        result = _run_qcad_script(input_dxf, output_dxf, room_label_json, plan)
        result["validation"] = validate_dxf(output_dxf, room_label_json) if result.get("success") else None
        return result
    if backend == "python":
        result = apply_plan_python(
            input_dxf=input_dxf,
            output_dxf=output_dxf,
            refinement_plan=plan,
            room_label_json=room_label_json,
        )
        result["backend"] = "python"
        result["success"] = Path(output_dxf).exists()
        return result
    raise ValueError("backend must be 'qcad' or 'python'")


@mcp.tool()
def render_preview(input_dxf: str, output_svg: str) -> Dict[str, Any]:
    """Render a simple SVG preview from DXF entities. This is a lightweight preview for agent loop testing."""
    return render_svg_python(input_dxf, output_svg)


if __name__ == "__main__":
    mcp.run(transport="stdio")
