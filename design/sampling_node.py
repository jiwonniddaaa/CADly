from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from design.state import CADlyGenerationState
from design.path_utils import HD_ROOT, resolve_hd_path


def run_sampling(state: CADlyGenerationState) -> CADlyGenerationState:
    graph_json_path_value = state.get("graph_json_path")

    if not graph_json_path_value:
        return {
            **state,
            "status": "sampling_failed",
            "message": "graph_json_path is missing. Cannot run HouseDiffusion sampling.",
            "validation_errors": ["graph_json_path is missing."],
        }

    graph_json_path = Path(graph_json_path_value)
    model_path = resolve_hd_path(state.get("model_path", "/workspace/ckpts/exp/model250000.pt"))
    out_dir = resolve_hd_path(state.get("out_dir", "outputs/cadly"))
    name = state.get("name", "floorplan")

    dataset = state.get("dataset", "rplan")
    set_name = state.get("set_name", "eval")
    target_set = state.get("target_set", 8)

    out_dir.mkdir(parents=True, exist_ok=True)

    if not graph_json_path.exists():
        return {
            **state,
            "status": "sampling_failed",
            "message": f"Graph JSON file not found: {graph_json_path}",
            "validation_errors": [f"Graph JSON file not found: {graph_json_path}"],
        }

    if not model_path.exists():
        return {
            **state,
            "status": "sampling_failed",
            "message": f"HouseDiffusion model file not found: {model_path}",
            "validation_errors": [f"HouseDiffusion model file not found: {model_path}"],
        }

    command = [
        sys.executable,
        "scripts/sample_single_graph.py",
        "--graph_json",
        str(graph_json_path),
        "--model_path",
        str(model_path),
        "--out_dir",
        str(out_dir),
        "--name",
        name,
        "--dataset",
        str(dataset),
        "--set_name",
        str(set_name),
        "--target_set",
        str(target_set),
    ]

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(HD_ROOT)

        result = subprocess.run(
            command,
            cwd=str(HD_ROOT),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout or str(e)

        return {
            **state,
            "status": "sampling_failed",
            "message": error_message,
            "validation_errors": [error_message],
        }

    svg_path = out_dir / f"{name}.svg"
    dxf_path = out_dir / f"{name}.dxf"
    room_label_path = out_dir / f"{name}_rooms.json"

    return {
        **state,
        "status": "completed",
        "message": "HouseDiffusion sampling and export completed.",
        "svg_path": str(svg_path),
        "dxf_path": str(dxf_path),
        "room_label_path": str(room_label_path),
        "sampling_stdout": result.stdout,
    }