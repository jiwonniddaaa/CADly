from __future__ import annotations
import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, TypedDict

from langgraph.graph import StateGraph, END


PROJECT_ROOT = Path(__file__).resolve().parents[1]   # CADly/
HD_ROOT = PROJECT_ROOT / "house_diffusion"            # CADly/house_diffusion


class CADlyGenerationState(TypedDict, total=False):
    graph_json_path: str
    model_path: str
    out_dir: str
    name: str

    graph_data: Dict[str, Any]
    validation_errors: List[str]
    verification_warnings: List[str]

    svg_path: str
    dxf_path: str
    room_label_path: str

    status: str
    message: str


def resolve_hd_path(path_value: str) -> Path:
    """
    Relative paths are interpreted from CADly/house_diffusion.
    Absolute paths are used as-is.
    """
    path = Path(path_value)
    if path.is_absolute():
        return path
    return HD_ROOT / path


def load_graph_json(state: CADlyGenerationState) -> CADlyGenerationState:
    graph_json_path = resolve_hd_path(state["graph_json_path"])

    if not graph_json_path.exists():
        return {
            "status": "error",
            "message": f"Graph JSON file not found: {graph_json_path}",
            "validation_errors": [f"Missing file: {graph_json_path}"],
        }

    try:
        with open(graph_json_path, "r", encoding="utf-8") as f:
            graph_data = json.load(f)

        return {
            "graph_json_path": str(graph_json_path),
            "graph_data": graph_data,
            "status": "loaded",
            "message": "Graph JSON loaded successfully.",
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to read graph JSON: {e}",
            "validation_errors": [str(e)],
        }


def validate_graph_json(state: CADlyGenerationState) -> CADlyGenerationState:
    graph_data = state.get("graph_data")
    errors: List[str] = []

    if not graph_data:
        return {
            "status": "validation_failed",
            "message": "graph_data is empty.",
            "validation_errors": ["graph_data is empty."],
        }

    rooms = graph_data.get("rooms", [])
    edges = graph_data.get("edges", [])

    if not isinstance(rooms, list) or len(rooms) == 0:
        errors.append("'rooms' must be a non-empty list.")

    if not isinstance(edges, list):
        errors.append("'edges' must be a list.")

    room_ids = set()

    for room in rooms:
        if not isinstance(room, dict):
            errors.append(f"Room must be an object: {room}")
            continue

        if "id" not in room:
            errors.append(f"Room missing id: {room}")
            continue

        room_id = str(room["id"])

        if room_id in room_ids:
            errors.append(f"Duplicate room id: {room_id}")

        room_ids.add(room_id)

        if "type" not in room:
            errors.append(f"Room {room_id} missing type.")
        else:
            try:
                room_type = int(room["type"])
                if room_type < 0 or room_type >= 25:
                    errors.append(f"Room {room_id} type must be between 0 and 24.")
            except Exception:
                errors.append(f"Room {room_id} type must be an integer.")

        if "corners" in room:
            try:
                corners = int(room["corners"])
                if corners < 3:
                    errors.append(f"Room {room_id} corners must be >= 3.")
                if corners >= 32:
                    errors.append(f"Room {room_id} corners must be < 32.")
            except Exception:
                errors.append(f"Room {room_id} corners must be an integer.")

    for edge in edges:
        if isinstance(edge, dict):
            source = edge.get("source")
            target = edge.get("target")
        elif isinstance(edge, list) and len(edge) == 2:
            source, target = edge
        else:
            errors.append(f"Invalid edge format: {edge}")
            continue

        if str(source) not in room_ids:
            errors.append(f"Edge source does not exist: {source}")

        if str(target) not in room_ids:
            errors.append(f"Edge target does not exist: {target}")

        if str(source) == str(target):
            errors.append(f"Self-edge is not allowed: {edge}")

    if errors:
        return {
            "status": "validation_failed",
            "message": "Graph JSON validation failed.",
            "validation_errors": errors,
        }

    return {
        "status": "validated",
        "message": "Graph JSON validation passed.",
        "validation_errors": [],
    }


def check_housediffusion_input(state: CADlyGenerationState) -> CADlyGenerationState:
    """
    Checks whether the graph JSON can be converted by:
    CADly/house_diffusion/house_diffusion/single_graph_dataset.py
    """
    try:
        if str(HD_ROOT) not in sys.path:
            sys.path.insert(0, str(HD_ROOT))

        from house_diffusion.single_graph_dataset import SingleGraphDataset

        dataset = SingleGraphDataset(
            graph_json=state["graph_json_path"],
            analog_bit=False,
        )

        data_sample, model_kwargs = dataset[0]

        if data_sample is None or model_kwargs is None:
            raise ValueError("SingleGraphDataset returned empty data.")

        return {
            "status": "converted",
            "message": "Graph JSON can be converted to HouseDiffusion input.",
        }

    except Exception as e:
        return {
            "status": "conversion_failed",
            "message": f"Failed to convert graph JSON to HouseDiffusion input: {e}",
            "validation_errors": [str(e)],
        }


def run_housediffusion_sampling(state: CADlyGenerationState) -> CADlyGenerationState:
    """
    Runs:
    CADly/house_diffusion/scripts/sample_single_graph.py

    sample_single_graph.py already performs:
    sampling + export_prediction(svg/dxf/room labels)
    """
    graph_json_path = Path(state["graph_json_path"])
    model_path = resolve_hd_path(state["model_path"])
    out_dir = resolve_hd_path(state.get("out_dir", "outputs/cadly"))
    name = state.get("name", "floorplan")

    out_dir.mkdir(parents=True, exist_ok=True)

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
    ]

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(HD_ROOT)

        subprocess.run(
            command,
            cwd=str(HD_ROOT),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    except subprocess.CalledProcessError as e:
        return {
            **state,
            "status": "sampling_failed",
            "message": e.stderr or e.stdout or str(e),
            "validation_errors": [e.stderr or e.stdout or str(e)],
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
    }


def verify_generated_floorplan(state: CADlyGenerationState) -> CADlyGenerationState:
    """
    Verifies generated output files after HouseDiffusion sampling.

    Current verification:
    1. SVG file exists
    2. DXF file exists
    3. Room label JSON exists
    4. Room label JSON is readable, if present

    This node can later be expanded to check:
    - room count consistency
    - room type consistency
    - adjacency satisfaction
    - area ratio
    - overlap / invalid geometry
    """
    errors: List[str] = []
    warnings: List[str] = []

    if state.get("status") != "completed":
        return state

    svg_path = Path(state.get("svg_path", ""))
    dxf_path = Path(state.get("dxf_path", ""))
    room_label_path = Path(state.get("room_label_path", ""))

    if not svg_path.exists():
        errors.append(f"SVG file not found: {svg_path}")

    if not dxf_path.exists():
        errors.append(f"DXF file not found: {dxf_path}")

    if not room_label_path.exists():
        warnings.append(f"Room label file not found: {room_label_path}")
    else:
        try:
            with open(room_label_path, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            warnings.append(f"Room label JSON exists but cannot be parsed: {e}")

    if errors:
        return {
            **state,
            "status": "verification_failed",
            "message": "Generated floorplan verification failed.",
            "validation_errors": errors,
            "verification_warnings": warnings,
        }

    return {
        **state,
        "status": "verified",
        "message": "Generated floorplan verification passed.",
        "validation_errors": [],
        "verification_warnings": warnings,
    }


def should_continue_after_validation(state: CADlyGenerationState) -> str:
    if state.get("status") in ["validation_failed", "error"]:
        return "end"
    return "continue"


def should_continue_after_conversion(state: CADlyGenerationState) -> str:
    if state.get("status") in ["conversion_failed", "error"]:
        return "end"
    return "continue"


def should_continue_after_sampling(state: CADlyGenerationState) -> str:
    if state.get("status") in ["sampling_failed", "error"]:
        return "end"
    return "continue"


def build_design_orchestrator():
    graph = StateGraph(CADlyGenerationState)

    graph.add_node("load_graph_json", load_graph_json)
    graph.add_node("validate_graph_json", validate_graph_json)
    graph.add_node("check_housediffusion_input", check_housediffusion_input)
    graph.add_node("run_housediffusion_sampling", run_housediffusion_sampling)
    graph.add_node("verify_generated_floorplan", verify_generated_floorplan)

    graph.set_entry_point("load_graph_json")

    graph.add_edge("load_graph_json", "validate_graph_json")

    graph.add_conditional_edges(
        "validate_graph_json",
        should_continue_after_validation,
        {
            "continue": "check_housediffusion_input",
            "end": END,
        },
    )

    graph.add_conditional_edges(
        "check_housediffusion_input",
        should_continue_after_conversion,
        {
            "continue": "run_housediffusion_sampling",
            "end": END,
        },
    )

    graph.add_conditional_edges(
        "run_housediffusion_sampling",
        should_continue_after_sampling,
        {
            "continue": "verify_generated_floorplan",
            "end": END,
        },
    )

    graph.add_edge("verify_generated_floorplan", END)

    return graph.compile()


if __name__ == "__main__":
    app = build_design_orchestrator()

    result = app.invoke(
        {
            # relative paths are based on CADly/house_diffusion
            "graph_json_path": "examples/single_graph_example.json",
            "model_path": "ckpts/exp/model250000.pt",
            "out_dir": "outputs/cadly",
            "name": "test_001",
        }
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))