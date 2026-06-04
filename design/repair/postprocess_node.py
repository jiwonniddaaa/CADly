from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

from design.state import CADlyGenerationState


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_rooms_from_label_data(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ["rooms", "room_meta", "labels", "room_labels"]:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def _extract_input_rooms(state: CADlyGenerationState) -> List[Dict[str, Any]]:
    graph_data = state.get("graph_data")

    if isinstance(graph_data, dict):
        rooms = graph_data.get("rooms", [])
        return rooms if isinstance(rooms, list) else []

    graph_json_path = state.get("graph_json_path")
    if not graph_json_path:
        return []

    path = Path(graph_json_path)
    if not path.exists():
        return []

    try:
        graph = _read_json(path)
    except Exception:
        return []

    rooms = graph.get("rooms", [])
    return rooms if isinstance(rooms, list) else []


def _ensure_svg_size_and_viewbox(svg_path: Path) -> bool:
    if not svg_path.exists() or svg_path.stat().st_size == 0:
        return False

    tree = ET.parse(svg_path)
    root = tree.getroot()

    changed = False

    has_viewbox = "viewBox" in root.attrib
    has_size = "width" in root.attrib and "height" in root.attrib

    if not has_size:
        root.set("width", "1024")
        root.set("height", "1024")
        changed = True

    if not has_viewbox:
        width = root.attrib.get("width", "1024").replace("px", "")
        height = root.attrib.get("height", "1024").replace("px", "")

        try:
            w = float(width)
            h = float(height)
        except Exception:
            w, h = 1024, 1024

        root.set("viewBox", f"0 0 {w:g} {h:g}")
        changed = True

    if changed:
        tree.write(svg_path, encoding="utf-8", xml_declaration=True)

    return changed


def _remove_empty_svg_geometry(svg_path: Path) -> bool:
    """
    Remove clearly empty drawable elements.

    This handles warnings like:
    SVG contains N geometry elements with missing coordinate attributes.

    Important:
    This should only remove empty elements, not reconstruct geometry.
    If too many geometry elements are empty, resampling is better.
    """
    if not svg_path.exists() or svg_path.stat().st_size == 0:
        return False

    tree = ET.parse(svg_path)
    root = tree.getroot()

    shape_requirements = {
        "path": ["d"],
        "polygon": ["points"],
        "polyline": ["points"],
        "rect": ["x", "y", "width", "height"],
        "line": ["x1", "y1", "x2", "y2"],
    }

    removed = False

    for parent in list(root.iter()):
        for child in list(parent):
            tag = _local_name(child.tag).lower()

            if tag not in shape_requirements:
                continue

            required = shape_requirements[tag]
            if not all(child.attrib.get(key) for key in required):
                parent.remove(child)
                removed = True

    if removed:
        tree.write(svg_path, encoding="utf-8", xml_declaration=True)

    return removed


def _normalize_and_repair_room_label_json(
    state: CADlyGenerationState,
    room_label_path: Path,
) -> bool:
    """
    Normalize room_label JSON and fill missing id/type if possible.

    This handles:
    - room label JSON shape issues
    - missing input room ids
    - missing input room types
    """
    if not room_label_path.exists() or room_label_path.stat().st_size == 0:
        return False

    data = _read_json(room_label_path)
    output_rooms = _extract_rooms_from_label_data(data)

    if not output_rooms:
        return False

    input_rooms = _extract_input_rooms(state)
    changed = False

    # Normalize to {"rooms": [...]}
    normalized = {"rooms": output_rooms}

    # Fill missing id/type by index if counts match.
    # This is safe only when output count equals input count.
    if input_rooms and len(input_rooms) == len(output_rooms):
        for i, output_room in enumerate(output_rooms):
            input_room = input_rooms[i]

            if output_room.get("id") is None and input_room.get("id") is not None:
                output_room["id"] = input_room["id"]
                changed = True

            if output_room.get("room_id") is None and output_room.get("id") is not None:
                output_room["room_id"] = output_room["id"]
                changed = True

            if output_room.get("type") is None and input_room.get("type") is not None:
                output_room["type"] = input_room["type"]
                changed = True

            if output_room.get("room_type") is None and output_room.get("type") is not None:
                output_room["room_type"] = output_room["type"]
                changed = True

            if output_room.get("label") is None and input_room.get("label") is not None:
                output_room["label"] = input_room["label"]
                changed = True

    # Even if nothing changed inside room items, normalize wrapper shape.
    if not (isinstance(data, dict) and isinstance(data.get("rooms"), list)):
        changed = True

    if changed:
        _write_json(room_label_path, normalized)

    return changed


def _add_dxf_room_text_labels(
    state: CADlyGenerationState,
    dxf_path: Path,
    room_label_path: Path,
) -> bool:
    """
    Add TEXT labels to DXF from room_label JSON.

    This handles:
    - DXF contains no TEXT/MTEXT room label entities.
    """
    if not dxf_path.exists() or not room_label_path.exists():
        return False

    try:
        import ezdxf
    except ImportError:
        return False

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception:
        return False

    existing_text_count = sum(
        1 for entity in msp if entity.dxftype() in {"TEXT", "MTEXT"}
    )

    if existing_text_count > 0:
        return False

    try:
        data = _read_json(room_label_path)
    except Exception:
        return False

    rooms = _extract_rooms_from_label_data(data)

    changed = False

    for room in rooms:
        label = (
            room.get("label")
            or room.get("name")
            or room.get("id")
            or room.get("room_id")
        )

        if not label:
            continue

        bbox = room.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            try:
                x1, y1, x2, y2 = [float(v) for v in bbox]
                x = (x1 + x2) / 2
                y = (y1 + y2) / 2
            except Exception:
                continue
        else:
            continue

        msp.add_text(
            str(label),
            dxfattribs={
                "height": 250,
                "layer": "ROOM_LABELS",
            },
        ).set_placement((x, y))

        changed = True

    if changed:
        doc.saveas(dxf_path)

    return changed


def postprocess_node(state: CADlyGenerationState) -> CADlyGenerationState:
    svg_path = Path(state.get("svg_path", ""))
    dxf_path = Path(state.get("dxf_path", ""))
    room_label_path = Path(state.get("room_label_path", ""))

    postprocess_count = int(state.get("postprocess_count", 0))

    repair_steps: List[str] = []

    try:
        if _ensure_svg_size_and_viewbox(svg_path):
            repair_steps.append("svg_viewbox_added")

        if _remove_empty_svg_geometry(svg_path):
            repair_steps.append("empty_svg_geometry_removed")

        if _normalize_and_repair_room_label_json(state, room_label_path):
            repair_steps.append("room_label_json_repaired")

        if _add_dxf_room_text_labels(state, dxf_path, room_label_path):
            repair_steps.append("dxf_room_text_labels_added")

        repair_history = state.get("repair_history", []) or []
        repair_history.append(
            {
                "action": "POSTPROCESS",
                "steps": repair_steps,
                "before_errors": state.get("validation_errors", []),
                "before_warnings": state.get("verification_warnings", []),
            }
        )

        return {
            **state,
            "status": "completed",
            "repair_route": "verification_node",
            "message": "Postprocessing completed. Verification will run again.",
            "repair_history": repair_history,
            "postprocess_count": postprocess_count + 1,
            "validation_errors": [],
            "verification_warnings": [],
        }

    except Exception as e:
        repair_history = state.get("repair_history", []) or []
        repair_history.append(
            {
                "action": "POSTPROCESS_FAILED",
                "error": str(e),
            }
        )

        return {
            **state,
            "status": "postprocess_failed",
            "message": f"Postprocessing failed: {e}",
            "repair_history": repair_history,
            "validation_errors": [f"Postprocessing failed: {e}"],
            "verification_warnings": [],
            "repair_route": "final_node",
        }