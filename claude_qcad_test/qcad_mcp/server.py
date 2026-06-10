from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from qcad_mcp.dxf_text_tools import summarize_dxf, validate_dxf, apply_plan_python, render_svg_python

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_TEMPLATE = ROOT / "scripts" / "qcad_apply_refinement_plan_template.js"

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
    """Apply a refinement plan to DXF. backend='qcad' executes QCAD autostart JS; backend='python' is a fallback."""
    plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
    if backend == "qcad":
        result = _run_qcad_script(input_dxf, output_dxf, room_label_json, plan)
        result["validation"] = validate_dxf(output_dxf, room_label_json) if result.get("success") else None
        return result
    if backend == "python":
        result = apply_plan_python(input_dxf, output_dxf, room_label_json, plan)
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
