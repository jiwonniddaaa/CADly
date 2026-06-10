from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_lines(path: str | Path) -> List[str]:
    return Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()


def _write_lines(path: str | Path, lines: List[str]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _parse_entities(lines: List[str]) -> List[Dict[str, Any]]:
    entities: List[Dict[str, Any]] = []

    i = 0
    while i < len(lines) - 1:
        code = lines[i].strip()
        value = lines[i + 1].strip()

        if code == "0" and value in {"LINE", "TEXT", "MTEXT"}:
            entity_type = value
            start_i = i
            i += 2

            data: Dict[str, Any] = {
                "type": entity_type,
                "start_index": start_i,
                "end_index": None,
                "layer": "0",
            }

            while i < len(lines) - 1:
                next_code = lines[i].strip()
                next_value = lines[i + 1].strip()

                if next_code == "0":
                    break

                if next_code == "8":
                    data["layer"] = next_value

                if entity_type == "LINE":
                    if next_code == "10":
                        data["x1"] = float(next_value)
                    elif next_code == "20":
                        data["y1"] = float(next_value)
                    elif next_code == "11":
                        data["x2"] = float(next_value)
                    elif next_code == "21":
                        data["y2"] = float(next_value)

                elif entity_type in {"TEXT", "MTEXT"}:
                    if next_code == "10":
                        data["x"] = float(next_value)
                    elif next_code == "20":
                        data["y"] = float(next_value)
                    elif next_code == "1":
                        data["value"] = next_value
                    elif next_code == "40":
                        data["height"] = float(next_value)

                i += 2

            data["end_index"] = i
            entities.append(data)
            continue

        i += 2

    return entities


def summarize_dxf(path: str) -> Dict[str, Any]:
    dxf_path = Path(path)
    lines_raw = _read_lines(dxf_path)
    entities = _parse_entities(lines_raw)

    line_entities = []
    text_entities = []
    layers: Dict[str, int] = {}
    all_x: List[float] = []
    all_y: List[float] = []
    off_axis_lines = []

    for entity in entities:
        layer = entity.get("layer", "0")
        layers[layer] = layers.get(layer, 0) + 1

        if entity["type"] == "LINE":
            if not all(k in entity for k in ["x1", "y1", "x2", "y2"]):
                continue

            item = {
                "index": len(line_entities),
                "layer": layer,
                "x1": float(entity["x1"]),
                "y1": float(entity["y1"]),
                "x2": float(entity["x2"]),
                "y2": float(entity["y2"]),
            }
            line_entities.append(item)

            all_x.extend([item["x1"], item["x2"]])
            all_y.extend([item["y1"], item["y2"]])

            dx = abs(item["x2"] - item["x1"])
            dy = abs(item["y2"] - item["y1"])

            # Nearly horizontal/vertical but slightly tilted.
            if dx > dy and 0 < dy <= 20:
                off_axis_lines.append(
                    {
                        "index": item["index"],
                        "start": [item["x1"], item["y1"]],
                        "end": [item["x2"], item["y2"]],
                    }
                )
            elif dy > dx and 0 < dx <= 20:
                off_axis_lines.append(
                    {
                        "index": item["index"],
                        "start": [item["x1"], item["y1"]],
                        "end": [item["x2"], item["y2"]],
                    }
                )

        elif entity["type"] in {"TEXT", "MTEXT"}:
            item = {
                "index": len(text_entities),
                "layer": layer,
                "x": float(entity.get("x", 0)),
                "y": float(entity.get("y", 0)),
                "value": str(entity.get("value", "")),
                "height": float(entity.get("height", 250)),
            }
            text_entities.append(item)
            all_x.append(item["x"])
            all_y.append(item["y"])

    if all_x and all_y:
        bbox = [min(all_x), min(all_y), max(all_x), max(all_y)]
    else:
        bbox = [0.0, 0.0, 0.0, 0.0]

    return {
        "path": str(dxf_path),
        "entity_count": len(line_entities) + len(text_entities),
        "line_count": len(line_entities),
        "text_count": len(text_entities),
        "layers": layers,
        "bbox": bbox,
        "off_axis_line_count": len(off_axis_lines),
        "off_axis_lines_preview": off_axis_lines[:10],
        "lines": line_entities,
        "texts": text_entities,
        "entities": entities,
    }


def _load_room_labels(room_label_json: str | None) -> List[Dict[str, Any]]:
    if not room_label_json:
        return []

    path = Path(room_label_json)
    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        rooms = data
    elif isinstance(data, dict):
        rooms = data.get("rooms", [])
    else:
        rooms = []

    normalized = []

    for idx, room in enumerate(rooms):
        label = (
            room.get("label")
            or room.get("name")
            or room.get("room_name")
            or room.get("id")
            or f"room_{idx + 1}"
        )

        if "center" in room and isinstance(room["center"], list) and len(room["center"]) >= 2:
            cx, cy = float(room["center"][0]), float(room["center"][1])
        elif all(k in room for k in ["x", "y"]):
            cx, cy = float(room["x"]), float(room["y"])
        elif "bbox" in room and isinstance(room["bbox"], list) and len(room["bbox"]) >= 4:
            x1, y1, x2, y2 = map(float, room["bbox"][:4])
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        else:
            cx, cy = 800 + idx * 1200, 800 + idx * 800

        normalized.append(
            {
                "label": str(label),
                "x": cx,
                "y": cy,
            }
        )

    return normalized


def validate_dxf(path: str, room_label_json: str | None = None) -> Dict[str, Any]:
    summary = summarize_dxf(path)

    errors: List[str] = []
    warnings: List[str] = []

    if summary["line_count"] == 0:
        errors.append("No LINE entities found in DXF.")

    if summary["layers"].get("0", 0) > 0:
        warnings.append("Some entities are still on layer 0.")

    if summary["off_axis_line_count"] > 0:
        warnings.append(
            f"{summary['off_axis_line_count']} nearly horizontal/vertical lines are slightly off-axis."
        )

    rooms = _load_room_labels(room_label_json)
    if rooms and summary["text_count"] < len(rooms):
        warnings.append("Room text labels are fewer than rooms in room_label_json.")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
    }


def _set_entity_layer(lines: List[str], entity: Dict[str, Any], new_layer: str) -> bool:
    start = int(entity["start_index"])
    end = int(entity["end_index"])

    i = start + 2
    while i < end - 1:
        code = lines[i].strip()
        if code == "8":
            lines[i + 1] = new_layer
            return True
        i += 2

    # If no layer exists, insert after entity type.
    insert_at = start + 2
    lines[insert_at:insert_at] = ["8", new_layer]
    return True


def _set_pair_value(lines: List[str], entity: Dict[str, Any], group_code: str, new_value: float) -> bool:
    start = int(entity["start_index"])
    end = int(entity["end_index"])

    i = start + 2
    while i < end - 1:
        code = lines[i].strip()
        if code == group_code:
            lines[i + 1] = _format_number(new_value)
            return True
        i += 2

    return False


def _align_line_entity(lines: List[str], entity: Dict[str, Any], tolerance: float = 20.0) -> bool:
    if entity.get("type") != "LINE":
        return False

    required = ["x1", "y1", "x2", "y2"]
    if not all(k in entity for k in required):
        return False

    x1 = float(entity["x1"])
    y1 = float(entity["y1"])
    x2 = float(entity["x2"])
    y2 = float(entity["y2"])

    dx = abs(x2 - x1)
    dy = abs(y2 - y1)

    changed = False

    # Nearly horizontal
    if dx >= dy and dy <= tolerance:
        avg_y = (y1 + y2) / 2
        changed |= _set_pair_value(lines, entity, "20", avg_y)
        changed |= _set_pair_value(lines, entity, "21", avg_y)

    # Nearly vertical
    elif dy > dx and dx <= tolerance:
        avg_x = (x1 + x2) / 2
        changed |= _set_pair_value(lines, entity, "10", avg_x)
        changed |= _set_pair_value(lines, entity, "11", avg_x)

    return changed


def _append_text_entity(
    lines: List[str],
    label: str,
    x: float,
    y: float,
    layer: str = "ROOM_TEXT",
    height: float = 250,
) -> None:
    # Insert before EOF if possible.
    insert_at = len(lines)

    for idx in range(len(lines) - 2, 0, -1):
        if lines[idx].strip() == "0" and lines[idx + 1].strip() == "EOF":
            insert_at = idx
            break

    entity_lines = [
        "0",
        "TEXT",
        "8",
        layer,
        "10",
        _format_number(x),
        "20",
        _format_number(y),
        "30",
        "0",
        "40",
        _format_number(height),
        "1",
        label,
        "50",
        "0",
        "7",
        "STANDARD",
        "72",
        "1",
        "73",
        "2",
        "11",
        _format_number(x),
        "21",
        _format_number(y),
        "31",
        "0",
    ]

    lines[insert_at:insert_at] = entity_lines


def apply_plan_python(
    input_dxf: str,
    output_dxf: str,
    refinement_plan: Dict[str, Any],
    room_label_json: str | None = None,
) -> Dict[str, Any]:
    input_path = Path(input_dxf)
    output_path = Path(output_dxf)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines_raw = _read_lines(input_path)
    changed = {
        "normalized_layers": 0,
        "aligned_lines": 0,
        "added_room_labels": 0,
    }

    actions = refinement_plan.get("actions", [])

    for action in actions:
        tool = action.get("tool")
        params = action.get("params", {})

        entities = _parse_entities(lines_raw)

        if tool == "normalize_layers":
            wall_layer = params.get("wall_layer", "WALL")
            text_layer = params.get("text_layer", "ROOM_TEXT")

            for entity in entities:
                if entity["type"] == "LINE":
                    if _set_entity_layer(lines_raw, entity, wall_layer):
                        changed["normalized_layers"] += 1
                elif entity["type"] in {"TEXT", "MTEXT"}:
                    if _set_entity_layer(lines_raw, entity, text_layer):
                        changed["normalized_layers"] += 1

        elif tool in {"align_walls", "align_axis"}:
            tolerance = float(params.get("tolerance", 20))
            for entity in entities:
                if entity["type"] == "LINE":
                    if _align_line_entity(lines_raw, entity, tolerance=tolerance):
                        changed["aligned_lines"] += 1

        elif tool == "add_room_labels":
            text_height = float(params.get("text_height", 250))
            text_layer = params.get("text_layer", "ROOM_TEXT")
            rooms = _load_room_labels(room_label_json)

            existing_summary = summarize_dxf_from_lines(lines_raw)
            existing_values = {
                str(text.get("value", "")).strip()
                for text in existing_summary.get("texts", [])
            }

            for room in rooms:
                label = str(room["label"])
                if label in existing_values:
                    continue

                _append_text_entity(
                    lines_raw,
                    label=label,
                    x=float(room["x"]),
                    y=float(room["y"]),
                    layer=text_layer,
                    height=text_height,
                )
                changed["added_room_labels"] += 1

        elif tool == "snap_wall_endpoints":
            # Placeholder for future real endpoint snapping.
            # Current sample mostly needs axis alignment and labels.
            pass

    _write_lines(output_path, lines_raw)

    return {
        "output_dxf": str(output_path),
        "changed": changed,
        "validation": validate_dxf(str(output_path), room_label_json=room_label_json),
        "backend": "python",
        "success": True,
    }


def summarize_dxf_from_lines(lines_raw: List[str]) -> Dict[str, Any]:
    temp_entities = _parse_entities(lines_raw)

    line_entities = []
    text_entities = []
    layers: Dict[str, int] = {}

    for entity in temp_entities:
        layer = entity.get("layer", "0")
        layers[layer] = layers.get(layer, 0) + 1

        if entity["type"] == "LINE":
            if all(k in entity for k in ["x1", "y1", "x2", "y2"]):
                line_entities.append(
                    {
                        "layer": layer,
                        "x1": float(entity["x1"]),
                        "y1": float(entity["y1"]),
                        "x2": float(entity["x2"]),
                        "y2": float(entity["y2"]),
                    }
                )

        elif entity["type"] in {"TEXT", "MTEXT"}:
            text_entities.append(
                {
                    "layer": layer,
                    "x": float(entity.get("x", 0)),
                    "y": float(entity.get("y", 0)),
                    "value": str(entity.get("value", "")),
                    "height": float(entity.get("height", 250)),
                }
            )

    return {
        "line_count": len(line_entities),
        "text_count": len(text_entities),
        "layers": layers,
        "lines": line_entities,
        "texts": text_entities,
        "entities": temp_entities,
    }


def render_svg_python(input_dxf: str, output_svg: str) -> dict:
    """
    Fallback SVG renderer for the sample DXF.
    It renders LINE and TEXT entities parsed by summarize_dxf().
    Real CAD rendering should use QCAD with backend='qcad'.
    """
    summary = summarize_dxf(input_dxf)

    lines = summary.get("lines") or []
    texts = summary.get("texts") or []

    if not lines:
        for entity in summary.get("entities", []):
            if entity.get("type") == "LINE":
                lines.append(
                    {
                        "x1": float(entity.get("x1", 0)),
                        "y1": float(entity.get("y1", 0)),
                        "x2": float(entity.get("x2", 0)),
                        "y2": float(entity.get("y2", 0)),
                    }
                )

    if not texts:
        for entity in summary.get("entities", []):
            if entity.get("type") in {"TEXT", "MTEXT"}:
                texts.append(
                    {
                        "x": float(entity.get("x", 0)),
                        "y": float(entity.get("y", 0)),
                        "value": str(entity.get("value", "")),
                    }
                )

    all_x = []
    all_y = []

    for line in lines:
        all_x.extend([float(line["x1"]), float(line["x2"])])
        all_y.extend([float(line["y1"]), float(line["y2"])])

    for text in texts:
        all_x.append(float(text["x"]))
        all_y.append(float(text["y"]))

    if not all_x or not all_y:
        min_x, min_y, max_x, max_y = 0, 0, 1000, 1000
    else:
        min_x = min(all_x)
        min_y = min(all_y)
        max_x = max(all_x)
        max_y = max(all_y)

    padding = 300
    width = max((max_x - min_x) + padding * 2, 1000)
    height = max((max_y - min_y) + padding * 2, 1000)

    def tx(x: float) -> float:
        return float(x) - min_x + padding

    def ty(y: float) -> float:
        return height - (float(y) - min_y + padding)

    line_elements = []
    for line in lines:
        line_elements.append(
            f'<line x1="{tx(line["x1"]):.2f}" y1="{ty(line["y1"]):.2f}" '
            f'x2="{tx(line["x2"]):.2f}" y2="{ty(line["y2"]):.2f}" '
            f'stroke="black" stroke-width="20" stroke-linecap="round" />'
        )

    text_elements = []
    for text in texts:
        value = (
            str(text.get("value", ""))
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        text_elements.append(
            f'<text x="{tx(text["x"]):.2f}" y="{ty(text["y"]):.2f}" '
            f'font-size="180" text-anchor="middle" dominant-baseline="middle" '
            f'fill="blue">{value}</text>'
        )

    line_svg = "\n  ".join(line_elements)
    text_svg = "\n  ".join(text_elements)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
  width="{width:.0f}"
  height="{height:.0f}"
  viewBox="0 0 {width:.0f} {height:.0f}">
  <rect width="100%" height="100%" fill="white"/>
  {line_svg}
  {text_svg}
</svg>'''

    output_path = Path(output_svg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")

    return {
        "ok": True,
        "backend": "python",
        "output_svg": str(output_path),
        "line_count": len(lines),
        "text_count": len(texts),
        "bbox": [min_x, min_y, max_x, max_y],
    }