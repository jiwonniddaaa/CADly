from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional


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

        if code == "0" and value in {"LINE", "TEXT", "MTEXT", "LWPOLYLINE"}:
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
                
                elif entity_type == "LWPOLYLINE":
                    if next_code == "70":
                        try:
                            data["closed"] = int(next_value) == 1
                        except Exception:
                            data["closed"] = False
                    elif next_code == "10":
                        data.setdefault("_poly_xs", []).append(float(next_value))

                    elif next_code == "20":
                        data.setdefault("_poly_ys", []).append(float(next_value))

                i += 2

            if entity_type == "LWPOLYLINE":
                xs = data.pop("_poly_xs", [])
                ys = data.pop("_poly_ys", [])
                data["points"] = [
                    (float(x), float(y))
                    for x, y in zip(xs, ys)
                ]

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
 
        elif entity["type"] == "LWPOLYLINE":
            points = entity.get("points", [])
            closed = bool(entity.get("closed", False))
            
            if len(points) >= 2:
                segment_pairs = list(zip(points, points[1:]))

                if closed:
                    segment_pairs.append((points[-1], points[0]))

                for p1, p2 in segment_pairs:
                    x1, y1 = p1
                    x2, y2 = p2

                    item = {
                        "index": len(line_entities),
                        "layer": layer,
                        "x1": float(x1),
                        "y1": float(y1),
                        "x2": float(x2),
                        "y2": float(y2),
                        "source": "LWPOLYLINE",
                    }

                    line_entities.append(item)

                    all_x.extend([item["x1"], item["x2"]])
                    all_y.extend([item["y1"], item["y2"]])

                    dx = abs(item["x2"] - item["x1"])
                    dy = abs(item["y2"] - item["y1"])

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

# ==============================
# ezdxf refinement helpers
# ==============================

ROOM_LAYERS = {
    "living_room",
    "kitchen",
    "bedroom",
    "bathroom",
    "balcony",
    "entrance",
    "dining_room",
    "study_room",
    "storage",
    "room",
    "ROOM_BOUNDARY",
}

NON_ROOM_LAYERS = {
    "DOOR",
    "WINDOW",
    "DIMENSION",
    "GRID",
    "FURNITURE",
    "SANITARY",
    "TEXT",
    "ROOM_TEXT",
    "ADJACENCY",
}


def _ensure_layer(doc, name: str, color: int = 7) -> None:
    if name not in doc.layers:
        doc.layers.add(name, color=color)


def _get_doc_from_msp(msp):
    return msp.doc


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _add_text_ezdxf(
    msp,
    text: str,
    x: float,
    y: float,
    *,
    height: float = 4.0,
    layer: str = "TEXT",
) -> None:
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, layer)

    entity = msp.add_text(
        str(text),
        dxfattribs={
            "height": float(height),
            "layer": layer,
        },
    )

    try:
        entity.set_placement((float(x), float(y)))
    except Exception:
        entity.dxf.insert = (float(x), float(y), 0)


def _add_rect_lwpolyline(
    msp,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    layer: str,
) -> None:
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, layer)

    points = [
        (float(x1), float(y1)),
        (float(x2), float(y1)),
        (float(x2), float(y2)),
        (float(x1), float(y2)),
    ]

    msp.add_lwpolyline(
        points,
        format="xy",
        close=True,
        dxfattribs={"layer": layer},
    )


def _add_arc_as_polyline(
    msp,
    *,
    center: tuple[float, float],
    radius: float,
    start_angle: float,
    end_angle: float,
    layer: str = "DOOR",
    segments: int = 12,
) -> None:
    """
    render_svg_python이 ARC를 직접 렌더링하지 못할 수 있으므로
    문 스윙 arc를 LWPOLYLINE 근사로 생성한다.
    """
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, layer)

    cx, cy = center
    points = []

    for i in range(segments + 1):
        t = i / segments
        angle = math.radians(start_angle + (end_angle - start_angle) * t)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        points.append((x, y))

    msp.add_lwpolyline(
        points,
        format="xy",
        close=False,
        dxfattribs={"layer": layer},
    )


def _get_entity_bbox(entity) -> tuple[float, float, float, float] | None:
    dxftype = entity.dxftype()

    try:
        if dxftype == "LWPOLYLINE":
            points = list(entity.get_points())
            if not points:
                return None

            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]
            return min(xs), min(ys), max(xs), max(ys)

        if dxftype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            xs = [float(start.x), float(end.x)]
            ys = [float(start.y), float(end.y)]
            return min(xs), min(ys), max(xs), max(ys)

        if dxftype in {"TEXT", "MTEXT"}:
            insert = entity.dxf.insert
            x = float(insert.x)
            y = float(insert.y)
            return x, y, x, y

    except Exception:
        return None

    return None


def _get_bbox_from_msp(msp) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []

    for entity in msp:
        bbox = _get_entity_bbox(entity)
        if bbox is None:
            continue

        x1, y1, x2, y2 = bbox
        xs.extend([x1, x2])
        ys.extend([y1, y2])

    if not xs or not ys:
        return 0.0, 0.0, 100.0, 100.0

    return min(xs), min(ys), max(xs), max(ys)


def _bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2, (y1 + y2) / 2


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _point_inside_bbox(
    x: float,
    y: float,
    bbox: tuple[float, float, float, float],
    *,
    margin: float = 0.0,
) -> bool:
    x1, y1, x2, y2 = bbox
    return (
        x1 - margin <= x <= x2 + margin
        and y1 - margin <= y <= y2 + margin
    )


def _text_entities(msp) -> list[dict[str, Any]]:
    result = []

    for entity in msp:
        if entity.dxftype() not in {"TEXT", "MTEXT"}:
            continue

        try:
            insert = entity.dxf.insert
            value = entity.dxf.text if entity.dxftype() == "TEXT" else entity.text
            height = float(getattr(entity.dxf, "height", 4.0))
            result.append(
                {
                    "x": float(insert.x),
                    "y": float(insert.y),
                    "value": str(value),
                    "height": height,
                    "layer": entity.dxf.layer,
                }
            )
        except Exception:
            continue

    return result


def _infer_room_type_from_text(
    bbox: tuple[float, float, float, float],
    texts: list[dict[str, Any]],
) -> str | None:
    for text in texts:
        if not _point_inside_bbox(text["x"], text["y"], bbox):
            continue

        value = str(text.get("value", "")).lower()

        if "living" in value or "거실" in value:
            return "living_room"
        if "kitchen" in value or "주방" in value or "부엌" in value:
            return "kitchen"
        if "bed" in value or "침실" in value or "방" in value:
            return "bedroom"
        if "bath" in value or "toilet" in value or "화장실" in value:
            return "bathroom"
        if "entrance" in value or "현관" in value:
            return "entrance"
        if "balcony" in value or "porch" in value or "발코니" in value:
            return "balcony"

    return None


def _iter_room_polygons(msp) -> list[dict[str, Any]]:
    """
    Closed LWPOLYLINE 기반으로 room 후보를 수집한다.
    layer가 WALL로 normalize된 뒤에도 TEXT 위치로 room_type을 다시 추정한다.
    """
    texts = _text_entities(msp)
    rooms = []

    for entity in msp:
        if entity.dxftype() != "LWPOLYLINE":
            continue

        layer = str(entity.dxf.layer)
        if layer in NON_ROOM_LAYERS:
            continue

        try:
            if not entity.closed:
                continue

            points_raw = list(entity.get_points())
            points = [(float(p[0]), float(p[1])) for p in points_raw]
            if len(points) < 3:
                continue

            bbox = _get_entity_bbox(entity)
            if bbox is None:
                continue

            layer_lower = layer.lower()
            room_type = layer_lower if layer_lower in ROOM_LAYERS else None

            inferred = _infer_room_type_from_text(bbox, texts)
            if inferred:
                room_type = inferred

            if room_type is None:
                room_type = "room"

            rooms.append(
                {
                    "entity": entity,
                    "layer": layer,
                    "room_type": room_type,
                    "bbox": bbox,
                    "area": _bbox_area(bbox),
                    "center": _bbox_center(bbox),
                    "points": points,
                }
            )

        except Exception:
            continue

    return rooms


def _normalize_layers(msp, params: Dict[str, Any]) -> int:
    """
    기존 room layer를 완전히 없애면 room_type 추론이 어려워질 수 있으므로,
    기본값은 room layer 보존 + 새 CAD layer 생성만 한다.

    params:
    - mode: "preserve_room_layers" | "map_to_wall"
    """
    doc = _get_doc_from_msp(msp)

    for name, color in {
        "WALL": 7,
        "DOOR": 3,
        "WINDOW": 5,
        "TEXT": 7,
        "DIMENSION": 1,
        "FURNITURE": 2,
        "SANITARY": 4,
    }.items():
        _ensure_layer(doc, name, color=color)

    mode = params.get("mode", "preserve_room_layers")

    if mode != "map_to_wall":
        return 0

    changed = 0

    for entity in msp:
        old_layer = str(entity.dxf.layer)
        if old_layer in ROOM_LAYERS:
            entity.dxf.layer = "WALL"
            changed += 1

    return changed


def _align_walls(msp, params: Dict[str, Any]) -> int:
    """
    LINE entity만 axis-align한다.
    LWPOLYLINE vertex 직접 수정은 위험하므로 MVP에서는 건드리지 않는다.
    """
    tolerance = float(params.get("tolerance", 20.0))
    changed = 0

    for entity in msp:
        if entity.dxftype() != "LINE":
            continue

        try:
            start = entity.dxf.start
            end = entity.dxf.end

            x1, y1 = float(start.x), float(start.y)
            x2, y2 = float(end.x), float(end.y)

            dx = abs(x2 - x1)
            dy = abs(y2 - y1)

            if dx >= dy and 0 < dy <= tolerance:
                avg_y = (y1 + y2) / 2
                entity.dxf.start = (x1, avg_y, 0)
                entity.dxf.end = (x2, avg_y, 0)
                changed += 1

            elif dy > dx and 0 < dx <= tolerance:
                avg_x = (x1 + x2) / 2
                entity.dxf.start = (avg_x, y1, 0)
                entity.dxf.end = (avg_x, y2, 0)
                changed += 1

        except Exception:
            continue

    return changed


def _add_room_labels(
    msp,
    room_label_json: str | None,
    params: Dict[str, Any],
) -> int:
    """
    기존 TEXT/MTEXT가 있으면 중복 추가하지 않는다.
    """
    existing_text_count = sum(
        1 for entity in msp if entity.dxftype() in {"TEXT", "MTEXT"}
    )

    if existing_text_count > 0:
        return 0

    rooms = _load_room_labels(room_label_json)
    if not rooms:
        return 0

    height = float(params.get("height", 4.0))
    added = 0

    for room in rooms:
        _add_text_ezdxf(
            msp,
            room["label"],
            room["x"],
            room["y"],
            height=height,
            layer="TEXT",
        )
        added += 1

    return added

def _add_rect_lines(
    msp,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    layer: str,
) -> int:
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, layer)

    msp.add_line((x1, y1), (x2, y1), dxfattribs={"layer": layer})
    msp.add_line((x2, y1), (x2, y2), dxfattribs={"layer": layer})
    msp.add_line((x2, y2), (x1, y2), dxfattribs={"layer": layer})
    msp.add_line((x1, y2), (x1, y1), dxfattribs={"layer": layer})

    return 4

def _add_wall_outline(msp, params: Dict[str, Any]) -> int:
    """
    MVP 벽체 보강:
    - 전체 외곽 bbox를 기준으로 외벽 outline을 LINE으로 추가한다.
    - 닫힌 LWPOLYLINE을 쓰면 SVG renderer가 polygon fill로 처리해서 도면을 덮어버리므로 사용하지 않는다.
    """
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, "WALL", color=7)

    min_x, min_y, max_x, max_y = _get_bbox_from_msp(msp)

    drawing_w = max_x - min_x
    drawing_h = max_y - min_y

    if drawing_w <= 0 or drawing_h <= 0:
        return 0

    offset = float(params.get("offset", max(drawing_w, drawing_h) * 0.015))
    inner_offset = offset * 1.8

    added = 0

    # outer wall line
    added += _add_rect_lines(
        msp,
        min_x - offset,
        min_y - offset,
        max_x + offset,
        max_y + offset,
        layer="WALL",
    )

    # inner wall line
    added += _add_rect_lines(
        msp,
        min_x + inner_offset,
        min_y + inner_offset,
        max_x - inner_offset,
        max_y - inner_offset,
        layer="WALL",
    )

    return added


def _add_door_symbol(
    msp,
    *,
    x: float,
    y: float,
    width: float,
    orientation: str,
    swing: str = "left",
    layer: str = "DOOR",
) -> int:
    """
    orientation:
    - horizontal: 벽이 수평, 문은 위/아래 방향으로 열린다고 가정
    - vertical: 벽이 수직, 문은 좌/우 방향으로 열린다고 가정
    """
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, layer, color=3)

    width = float(width)

    if orientation == "horizontal":
        # 문짝
        if swing == "right":
            hinge = (x + width, y)
            leaf_end = (x + width, y + width)
            start_angle, end_angle = 180, 90
        else:
            hinge = (x, y)
            leaf_end = (x, y + width)
            start_angle, end_angle = 0, 90

        msp.add_line(hinge, leaf_end, dxfattribs={"layer": layer})
        _add_arc_as_polyline(
            msp,
            center=hinge,
            radius=width,
            start_angle=start_angle,
            end_angle=end_angle,
            layer=layer,
        )

    else:
        if swing == "right":
            hinge = (x, y + width)
            leaf_end = (x + width, y + width)
            start_angle, end_angle = -90, 0
        else:
            hinge = (x, y)
            leaf_end = (x + width, y)
            start_angle, end_angle = 0, 90

        msp.add_line(hinge, leaf_end, dxfattribs={"layer": layer})
        _add_arc_as_polyline(
            msp,
            center=hinge,
            radius=width,
            start_angle=start_angle,
            end_angle=end_angle,
            layer=layer,
        )

    return 2


def _shared_interval(
    a1: float,
    a2: float,
    b1: float,
    b2: float,
) -> tuple[float, float] | None:
    lo = max(min(a1, a2), min(b1, b2))
    hi = min(max(a1, a2), max(b1, b2))

    if hi <= lo:
        return None

    return lo, hi


def _add_simple_doors(msp, params: Dict[str, Any]) -> int:
    """
    Simple deterministic door placement.

    Rules:
    - Find living_room. If not found, use the largest room as living.
    - Add one door between living_room and kitchen if kitchen exists.
    - Add one door between living_room and bedroom if bedroom exists.
    - Add one entrance door on living_room lower wall.
    - Do not use area filters, shared-wall filters, or max door filters.
    """
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, "DOOR", color=3)

    rooms = _iter_room_polygons(msp)
    if not rooms:
        return 0

    plan_min_x, plan_min_y, plan_max_x, plan_max_y = _get_bbox_from_msp(msp)
    plan_size = max(plan_max_x - plan_min_x, plan_max_y - plan_min_y, 1.0)

    door_width_ratio = float(params.get("door_width_ratio", 0.08))
    door_width = float(params.get("default_width") or plan_size * door_width_ratio)

    # 현재 샘플 좌표계 기준으로 너무 큰 문 방지
    door_width = max(6.0, min(door_width, 14.0))

    living = None
    kitchen = None
    bedrooms = []

    for room in rooms:
        room_type = str(room.get("room_type", "")).lower()
        layer = str(room.get("layer", "")).lower()
        value = room_type or layer

        if value == "living_room":
            living = room
        elif value == "kitchen":
            kitchen = room
        elif value == "bedroom":
            bedrooms.append(room)

    if living is None:
        living = max(rooms, key=lambda r: float(r.get("area", 0.0)))

    added = 0
    placed_centers: list[tuple[float, float]] = []

    def _already_near(x: float, y: float, tol: float = 4.0) -> bool:
        for px, py in placed_centers:
            if abs(px - x) <= tol and abs(py - y) <= tol:
                return True
        return False

    def _overlap_center(
        a1: float,
        a2: float,
        b1: float,
        b2: float,
    ) -> float:
        """
        두 구간이 겹치면 겹치는 구간의 중심,
        안 겹치면 target 중심을 living 범위 안으로 clamp.
        """
        lo = max(min(a1, a2), min(b1, b2))
        hi = min(max(a1, a2), max(b1, b2))

        if hi > lo:
            return (lo + hi) / 2

        target_center = (b1 + b2) / 2
        return max(min(a1, a2), min(target_center, max(a1, a2)))

    def _place_door_to_room(target_room: dict[str, Any]) -> int:
        lx1, ly1, lx2, ly2 = living["bbox"]
        tx1, ty1, tx2, ty2 = target_room["bbox"]

        # living과 target의 상대 위치 판단
        living_cx = (lx1 + lx2) / 2
        living_cy = (ly1 + ly2) / 2
        target_cx = (tx1 + tx2) / 2
        target_cy = (ty1 + ty2) / 2

        dx = target_cx - living_cx
        dy = target_cy - living_cy

        # 좌우 관계가 더 강한 경우: vertical door
        if abs(dx) >= abs(dy):
            if dx >= 0:
                # target is right of living
                x = lx2
                y_center = _overlap_center(ly1, ly2, ty1, ty2)
                swing = "left"
            else:
                # target is left of living
                x = lx1
                y_center = _overlap_center(ly1, ly2, ty1, ty2)
                swing = "right"

            width = min(door_width, max(6.0, abs(ty2 - ty1) * 0.7))
            y = y_center - width / 2
            center = (x, y_center)

            if _already_near(*center):
                return 0

            placed_centers.append(center)

            return _add_door_symbol(
                msp,
                x=x,
                y=y,
                width=width,
                orientation="vertical",
                swing=swing,
                layer="DOOR",
            )

        # 상하 관계가 더 강한 경우: horizontal door
        else:
            if dy >= 0:
                # target is above living
                y = ly2
                x_center = _overlap_center(lx1, lx2, tx1, tx2)
            else:
                # target is below living
                y = ly1
                x_center = _overlap_center(lx1, lx2, tx1, tx2)

            width = min(door_width, max(6.0, abs(tx2 - tx1) * 0.7))
            x = x_center - width / 2
            center = (x_center, y)

            if _already_near(*center):
                return 0

            placed_centers.append(center)

            return _add_door_symbol(
                msp,
                x=x,
                y=y,
                width=width,
                orientation="horizontal",
                swing="left",
                layer="DOOR",
            )

    def _place_entrance_door() -> int:
        lx1, ly1, lx2, ly2 = living["bbox"]
        living_w = lx2 - lx1

        if living_w <= 1.0:
            return 0

        width = min(door_width, living_w * 0.18)
        x = lx1 + living_w * 0.25
        y = ly1
        center = (x + width / 2, y)

        if _already_near(*center):
            return 0

        placed_centers.append(center)

        return _add_door_symbol(
            msp,
            x=x,
            y=y,
            width=width,
            orientation="horizontal",
            swing="left",
            layer="DOOR",
        )

    # 1. kitchen door
    if kitchen is not None:
        added += _place_door_to_room(kitchen)

    # 2. bedroom door
    if bedrooms:
        # 여러 bedroom이면 가장 큰 bedroom 하나만
        bedroom = max(bedrooms, key=lambda r: float(r.get("area", 0.0)))
        added += _place_door_to_room(bedroom)

    # 3. entrance door
    if params.get("add_entrance_door", True):
        added += _place_entrance_door()

    return added


def _add_window_symbol(
    msp,
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    orientation: str,
    layer: str = "WINDOW",
) -> int:
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, layer, color=5)

    length = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    offset = max(length * 0.04, 0.8)

    if orientation == "horizontal":
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})
        msp.add_line((x1, y1 - offset), (x2, y2 - offset), dxfattribs={"layer": layer})
    else:
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})
        msp.add_line((x1 + offset, y1), (x2 + offset, y2), dxfattribs={"layer": layer})

    return 2


def _add_simple_windows(msp, params: Dict[str, Any]) -> int:
    """
    외곽에 닿은 방에 window symbol 추가.
    living/bedroom/kitchen/bathroom 우선.
    """
    rooms = _iter_room_polygons(msp)
    if not rooms:
        return 0

    min_x, min_y, max_x, max_y = _get_bbox_from_msp(msp)
    plan_w = max_x - min_x
    plan_h = max_y - min_y
    plan_size = max(plan_w, plan_h)

    tolerance = float(params.get("exterior_tolerance", plan_size * 0.03))

    added = 0

    preferred = {
        "living_room": 0.28,
        "bedroom": 0.20,
        "kitchen": 0.16,
        "bathroom": 0.10,
    }

    for room in rooms:
        room_type = room["room_type"]
        if room_type not in preferred:
            continue

        x1, y1, x2, y2 = room["bbox"]
        rw = x2 - x1
        rh = y2 - y1

        ratio = preferred.get(room_type, 0.15)
        window_len = max(plan_size * ratio, 3.0)

        # 가장 명확한 외곽벽에 배치
        if abs(y2 - max_y) <= tolerance:
            length = min(window_len, rw * 0.65)
            cx = (x1 + x2) / 2
            added += _add_window_symbol(
                msp,
                x1=cx - length / 2,
                y1=y2,
                x2=cx + length / 2,
                y2=y2,
                orientation="horizontal",
            )

        elif abs(y1 - min_y) <= tolerance:
            length = min(window_len, rw * 0.65)
            cx = (x1 + x2) / 2
            added += _add_window_symbol(
                msp,
                x1=cx - length / 2,
                y1=y1,
                x2=cx + length / 2,
                y2=y1,
                orientation="horizontal",
            )

        elif abs(x1 - min_x) <= tolerance:
            length = min(window_len, rh * 0.65)
            cy = (y1 + y2) / 2
            added += _add_window_symbol(
                msp,
                x1=x1,
                y1=cy - length / 2,
                x2=x1,
                y2=cy + length / 2,
                orientation="vertical",
            )

        elif abs(x2 - max_x) <= tolerance:
            length = min(window_len, rh * 0.65)
            cy = (y1 + y2) / 2
            added += _add_window_symbol(
                msp,
                x1=x2,
                y1=cy - length / 2,
                x2=x2,
                y2=cy + length / 2,
                orientation="vertical",
            )

    return added


def _add_basic_dimensions(msp, params: Dict[str, Any]) -> int:
    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, "DIMENSION", color=1)

    min_x, min_y, max_x, max_y = _get_bbox_from_msp(msp)

    width = max_x - min_x
    height = max_y - min_y

    if width <= 0 or height <= 0:
        return 0

    offset = float(params.get("offset", max(width, height) * 0.065))
    text_height = float(params.get("text_height", max(width, height) * 0.025))
    scale_factor = float(params.get("scale_factor", 100.0))

    displayed_width = int(round(width * scale_factor))
    displayed_height = int(round(height * scale_factor))

    added = 0

    # bottom dimension
    y = min_y - offset

    msp.add_line((min_x, y), (max_x, y), dxfattribs={"layer": "DIMENSION"})
    msp.add_line((min_x, y - offset * 0.12), (min_x, y + offset * 0.12), dxfattribs={"layer": "DIMENSION"})
    msp.add_line((max_x, y - offset * 0.12), (max_x, y + offset * 0.12), dxfattribs={"layer": "DIMENSION"})

    _add_text_ezdxf(
        msp,
        f"{displayed_width}",
        (min_x + max_x) / 2,
        y - offset * 0.35,
        height=text_height,
        layer="DIMENSION",
    )

    added += 4

    # left dimension
    x = min_x - offset

    msp.add_line((x, min_y), (x, max_y), dxfattribs={"layer": "DIMENSION"})
    msp.add_line((x - offset * 0.12, min_y), (x + offset * 0.12, min_y), dxfattribs={"layer": "DIMENSION"})
    msp.add_line((x - offset * 0.12, max_y), (x + offset * 0.12, max_y), dxfattribs={"layer": "DIMENSION"})

    _add_text_ezdxf(
        msp,
        f"{displayed_height}",
        x - offset * 0.40,
        (min_y + max_y) / 2,
        height=text_height,
        layer="DIMENSION",
    )

    added += 4

    return added


def _add_basic_fixtures(msp, params: Dict[str, Any]) -> int:
    rooms = _iter_room_polygons(msp)
    if not rooms:
        return 0

    doc = _get_doc_from_msp(msp)
    _ensure_layer(doc, "FURNITURE", color=2)
    _ensure_layer(doc, "SANITARY", color=4)

    added = 0

    for room in rooms:
        room_type = room["room_type"]
        x1, y1, x2, y2 = room["bbox"]
        w = x2 - x1
        h = y2 - y1

        if w <= 0 or h <= 0:
            continue

        if room_type == "bathroom":
            # toilet
            tx1 = x1 + w * 0.12
            ty1 = y1 + h * 0.15
            tx2 = tx1 + w * 0.22
            ty2 = ty1 + h * 0.22
            _add_rect_lwpolyline(msp, tx1, ty1, tx2, ty2, layer="SANITARY")

            # sink
            sx1 = x1 + w * 0.58
            sy1 = y1 + h * 0.15
            sx2 = sx1 + w * 0.25
            sy2 = sy1 + h * 0.18
            _add_rect_lwpolyline(msp, sx1, sy1, sx2, sy2, layer="SANITARY")

            added += 2

        elif room_type == "kitchen":
            # counter line
            cx1 = x1 + w * 0.12
            cy1 = y1 + h * 0.12
            cx2 = x2 - w * 0.12
            cy2 = cy1 + h * 0.16
            _add_rect_lwpolyline(msp, cx1, cy1, cx2, cy2, layer="FURNITURE")
            added += 1

        elif room_type == "bedroom":
            # bed
            bx1 = x1 + w * 0.15
            by1 = y1 + h * 0.18
            bx2 = bx1 + w * 0.45
            by2 = by1 + h * 0.50
            _add_rect_lwpolyline(msp, bx1, by1, bx2, by2, layer="FURNITURE")
            added += 1

        elif room_type == "living_room":
            # sofa/table
            sx1 = x1 + w * 0.12
            sy1 = y1 + h * 0.15
            sx2 = sx1 + w * 0.32
            sy2 = sy1 + h * 0.15
            _add_rect_lwpolyline(msp, sx1, sy1, sx2, sy2, layer="FURNITURE")

            tx1 = x1 + w * 0.48
            ty1 = y1 + h * 0.35
            tx2 = tx1 + w * 0.18
            ty2 = ty1 + h * 0.12
            _add_rect_lwpolyline(msp, tx1, ty1, tx2, ty2, layer="FURNITURE")

            added += 2

    return added

def _remove_tiny_lines(msp, params: Dict[str, Any]) -> int:
    min_length = float(params.get("min_length", 0.5))
    removed = 0

    for entity in list(msp):
        if entity.dxftype() != "LINE":
            continue

        try:
            start = entity.dxf.start
            end = entity.dxf.end

            dx = float(end.x) - float(start.x)
            dy = float(end.y) - float(start.y)
            length = (dx ** 2 + dy ** 2) ** 0.5

            if length < min_length:
                msp.delete_entity(entity)
                removed += 1

        except Exception:
            continue

    return removed


def _normalize_text_size(msp, params: Dict[str, Any]) -> int:
    min_x, min_y, max_x, max_y = _get_bbox_from_msp(msp)
    plan_size = max(max_x - min_x, max_y - min_y)

    if plan_size <= 0:
        return 0

    default_height = float(params.get("height", plan_size * 0.025))
    min_height = float(params.get("min_height", plan_size * 0.012))
    max_height = float(params.get("max_height", plan_size * 0.035))

    changed = 0

    for entity in msp:
        if entity.dxftype() not in {"TEXT", "MTEXT"}:
            continue

        try:
            old_height = float(entity.dxf.height)

            if old_height < min_height or old_height > max_height:
                entity.dxf.height = default_height
                changed += 1

        except Exception:
            continue

    return changed


def _clean_cad_layers(msp, params: Dict[str, Any]) -> int:
    doc = _get_doc_from_msp(msp)

    for name, color in {
        "WALL": 7,
        "DOOR": 3,
        "WINDOW": 5,
        "TEXT": 7,
        "DIMENSION": 1,
        "FURNITURE": 2,
        "SANITARY": 4,
    }.items():
        _ensure_layer(doc, name, color=color)

    changed = 0
    room_layers = {"living_room", "kitchen", "bedroom", "bathroom"}

    for entity in msp:
        layer = str(entity.dxf.layer)

        # 방 레이어는 색상 렌더링에 쓰일 수 있으니까 건드리지 않음
        if layer in room_layers:
            continue

        if entity.dxftype() in {"TEXT", "MTEXT"} and layer in {"0", "ROOM_TEXT"}:
            entity.dxf.layer = "TEXT"
            changed += 1

        elif entity.dxftype() == "LINE" and layer == "0":
            entity.dxf.layer = "WALL"
            changed += 1

    return changed


def _line_key(entity, precision: int = 3):
    start = entity.dxf.start
    end = entity.dxf.end

    p1 = (
        round(float(start.x), precision),
        round(float(start.y), precision),
    )
    p2 = (
        round(float(end.x), precision),
        round(float(end.y), precision),
    )

    a, b = sorted([p1, p2])

    return (
        str(entity.dxf.layer),
        a,
        b,
    )


def _remove_duplicate_elements(msp, params: Dict[str, Any]) -> int:
    removed = 0
    seen = set()

    for entity in list(msp):
        if entity.dxftype() != "LINE":
            continue

        try:
            key = _line_key(entity)

            if key in seen:
                msp.delete_entity(entity)
                removed += 1
            else:
                seen.add(key)

        except Exception:
            continue

    return removed


def _distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _cluster_numeric_values(values: List[float], tolerance: float) -> Dict[float, float]:
    """
    가까운 좌표값들을 하나의 대표값으로 스냅하기 위한 매핑 생성.
    예: [0, 0.2, 0.3, 10, 10.1] -> {0->0.166, 0.2->0.166, 0.3->0.166, 10->10.05, 10.1->10.05}
    """
    if not values:
        return {}

    sorted_values = sorted(values)
    groups: List[List[float]] = []
    current_group = [sorted_values[0]]

    for v in sorted_values[1:]:
        if abs(v - current_group[-1]) <= tolerance:
            current_group.append(v)
        else:
            groups.append(current_group)
            current_group = [v]
    groups.append(current_group)

    value_map: Dict[float, float] = {}
    for group in groups:
        rep = sum(group) / len(group)
        for v in group:
            value_map[v] = rep

    return value_map


def _get_lwpolyline_xy_points(entity) -> List[Tuple[float, float]]:
    points = []
    for p in entity.get_points("xy"):
        points.append((float(p[0]), float(p[1])))
    return points


def _set_lwpolyline_xy_points(entity, points: List[Tuple[float, float]]) -> None:
    closed = entity.closed
    entity.clear()
    entity.append_points(points, format="xy")
    entity.closed = closed


def _bbox_from_points(points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_contains_point(
    bbox: Tuple[float, float, float, float],
    point: Tuple[float, float],
    margin: float = 0.0,
) -> bool:
    min_x, min_y, max_x, max_y = bbox
    x, y = point
    return (
        min_x - margin <= x <= max_x + margin
        and min_y - margin <= y <= max_y + margin
    )


def _polygon_area(points: List[Tuple[float, float]]) -> float:
    """
    Shoelace formula. 반환값 단위는 입력 좌표 단위^2.
    """
    if len(points) < 3:
        return 0.0

    area = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _polygon_centroid(points: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Polygon centroid. 실패하면 bbox center 반환.
    """
    if len(points) < 3:
        min_x, min_y, max_x, max_y = _bbox_from_points(points)
        return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    signed_area = 0.0
    cx = 0.0
    cy = 0.0

    for i in range(len(points)):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % len(points)]
        a = x0 * y1 - x1 * y0
        signed_area += a
        cx += (x0 + x1) * a
        cy += (y0 + y1) * a

    if abs(signed_area) < 1e-9:
        min_x, min_y, max_x, max_y = _bbox_from_points(points)
        return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    signed_area *= 0.5
    cx /= (6.0 * signed_area)
    cy /= (6.0 * signed_area)
    return (cx, cy)


def _entity_center_2d(entity) -> Optional[Tuple[float, float]]:
    try:
        dxftype = entity.dxftype()

        if dxftype == "ARC":
            center = entity.dxf.center
            return (float(center.x), float(center.y))

        if dxftype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            return (
                (float(start.x) + float(end.x)) / 2.0,
                (float(start.y) + float(end.y)) / 2.0,
            )

        if dxftype == "LWPOLYLINE":
            pts = _get_lwpolyline_xy_points(entity)
            if not pts:
                return None
            min_x, min_y, max_x, max_y = _bbox_from_points(pts)
            return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

        if dxftype == "TEXT":
            insert = entity.dxf.insert
            return (float(insert.x), float(insert.y))

        if dxftype == "MTEXT":
            insert = entity.dxf.insert
            return (float(insert.x), float(insert.y))

    except Exception:
        return None

    return None


def _get_room_polylines(msp) -> List[Any]:
    room_polylines = []

    for entity in msp:
        if entity.dxftype() != "LWPOLYLINE":
            continue

        layer = str(entity.dxf.layer)
        if layer not in ROOM_LAYERS:
            continue

        if not entity.closed:
            continue

        room_polylines.append(entity)

    return room_polylines


def _align_room_boundaries(msp, params: Dict[str, Any]) -> int:
    """
    room layer에 있는 closed LWPOLYLINE들의 vertex x/y를 tolerance 기준으로 스냅.
    가까운 수평/수직 경계를 정렬해 미세한 틀어짐을 줄인다.
    """
    tolerance = float(params.get("boundary_tolerance", 8.0))

    room_polylines = _get_room_polylines(msp)
    if not room_polylines:
        return 0

    all_x = []
    all_y = []

    poly_points_map: Dict[Any, List[Tuple[float, float]]] = {}
    for entity in room_polylines:
        pts = _get_lwpolyline_xy_points(entity)
        if len(pts) < 3:
            continue
        poly_points_map[entity] = pts
        for x, y in pts:
            all_x.append(x)
            all_y.append(y)

    if not all_x or not all_y:
        return 0

    x_map = _cluster_numeric_values(all_x, tolerance)
    y_map = _cluster_numeric_values(all_y, tolerance)

    changed_vertices = 0

    for entity, pts in poly_points_map.items():
        new_pts = []
        changed_here = False

        for x, y in pts:
            nx = x_map.get(x, x)
            ny = y_map.get(y, y)

            if abs(nx - x) > 1e-6 or abs(ny - y) > 1e-6:
                changed_here = True
                changed_vertices += 1

            new_pts.append((nx, ny))

        if changed_here:
            _set_lwpolyline_xy_points(entity, new_pts)

    return changed_vertices


def apply_plan_python(
    input_dxf: str,
    output_dxf: str,
    refinement_plan: Dict[str, Any],
    room_label_json: str | None = None,
) -> Dict[str, Any]:
    import ezdxf

    doc = ezdxf.readfile(input_dxf)
    msp = doc.modelspace()

    changed = {
        "normalized_layers": 0,
        "aligned_lines": 0,
        "added_room_labels": 0,
        "added_doors": 0,
        "added_windows": 0,
        "added_dimensions": 0,
        "added_wall_outline": 0,
        "added_fixtures": 0,

        "removed_tiny_lines": 0,
        "normalized_text_size": 0,
        "cleaned_layers": 0,
        "removed_duplicates": 0,

        "aligned_room_boundaries": 0,
        "added_room_area_labels": 0,
    }

    actions = refinement_plan.get("actions", [])

    for action in actions:
        tool = action.get("tool")
        params = action.get("params", {})

        if tool == "enhance_cad_style":
            # room geometry 미세 정렬
            if params.get("align_room_boundaries", True):
                changed["aligned_room_boundaries"] += _align_room_boundaries(msp, params)

            # CAD 요소 추가
            changed["added_wall_outline"] += _add_wall_outline(msp, params)
            changed["added_doors"] += _add_simple_doors(msp, params)
            changed["added_windows"] += _add_simple_windows(msp, params)
            changed["added_dimensions"] += _add_basic_dimensions(msp, params)

            # optional fixtures
            if params.get("add_fixtures", False):
                changed["added_fixtures"] += _add_basic_fixtures(msp, params)
            
            # cleanup
            changed["removed_tiny_lines"] += _remove_tiny_lines(msp, params)
            changed["normalized_text_size"] += _normalize_text_size(msp, params)
            changed["cleaned_layers"] += _clean_cad_layers(msp, params)
            changed["removed_duplicates"] += _remove_duplicate_elements(msp, params)

        elif tool == "normalize_layers":
            changed["normalized_layers"] += _normalize_layers(msp, params)

        elif tool in {"align_walls", "align_lines"}:
            changed["aligned_lines"] += _align_walls(msp, params)

        elif tool == "add_room_labels":
            changed["added_room_labels"] += _add_room_labels(
                msp,
                room_label_json,
                params,
            )

        elif tool == "add_simple_doors":
            changed["added_doors"] += _add_simple_doors(
                msp,
                params,
            )

        elif tool == "add_simple_windows":
            changed["added_windows"] += _add_simple_windows(
                msp,
                params,
            )

        elif tool == "add_basic_dimensions":
            changed["added_dimensions"] += _add_basic_dimensions(
                msp,
                params,
            )

        elif tool == "add_wall_outline":
            changed["added_wall_outline"] += _add_wall_outline(
                msp,
                params,
            )

        elif tool == "add_basic_fixtures":
            changed["added_fixtures"] += _add_basic_fixtures(
                msp,
                params,
            )
        
        elif tool == "remove_tiny_lines":
            changed["removed_tiny_lines"] += _remove_tiny_lines(msp, params)

        elif tool == "normalize_text_size":
            changed["normalized_text_size"] += _normalize_text_size(msp, params)

        elif tool == "clean_cad_layers":
            changed["cleaned_layers"] += _clean_cad_layers(msp, params)

        elif tool == "remove_duplicate_elements":
            changed["removed_duplicates"] += _remove_duplicate_elements(msp, params)

        elif tool == "align_room_boundaries":
            changed["aligned_room_boundaries"] += _align_room_boundaries(msp, params)

    Path(output_dxf).parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_dxf)

    return {
        "output_dxf": output_dxf,
        "changed": changed,
        "validation": validate_dxf(output_dxf, room_label_json),
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
    Preview renderer for CADly/QCAD DXF.

    - Closed LWPOLYLINE entities are rendered as room polygons.
    - ADJACENCY lines are hidden by default.
    - TEXT/MTEXT labels use DXF text height.
    """
    summary = summarize_dxf(input_dxf)
    entities = summary.get("entities", [])
    texts = summary.get("texts") or []

    ROOM_COLORS = {
        "living_room": "#f4a3a8",
        "kitchen": "#ffe3a3",
        "bedroom": "#f6c7c7",
        "bathroom": "#d9d9d9",
        "balcony": "#cde7ff",
        "entrance": "#d8f3dc",
        "dining_room": "#fff1b8",
        "study_room": "#d7c9ff",
        "storage": "#eeeeee",
        "ROOM_BOUNDARY": "#eeeeee",
        "room": "#eeeeee",
        "0": "#eeeeee",
    }

    HIDDEN_LAYERS = {"ADJACENCY"}

    polygons = []
    lines = []

    for entity in entities:
        layer = str(entity.get("layer", "0"))

        if layer in HIDDEN_LAYERS:
            continue

        if entity.get("type") == "LWPOLYLINE":
            points = entity.get("points", [])
            if len(points) < 2:
                continue

            clean_points = [(float(x), float(y)) for x, y in points]

            # ezdxf가 닫힌 polyline에 첫 점을 마지막에 한 번 더 넣는 경우 제거
            if len(clean_points) >= 2 and clean_points[0] == clean_points[-1]:
                clean_points = clean_points[:-1]

            if len(clean_points) >= 3 and entity.get("closed", False):
                polygons.append(
                    {
                        "layer": layer,
                        "points": clean_points,
                    }
                )
            else:
                for p1, p2 in zip(clean_points, clean_points[1:]):
                    if p1 == p2:
                        continue
                    lines.append(
                        {
                            "layer": layer,
                            "x1": p1[0],
                            "y1": p1[1],
                            "x2": p2[0],
                            "y2": p2[1],
                        }
                    )

        elif entity.get("type") == "LINE":
            if all(k in entity for k in ["x1", "y1", "x2", "y2"]):
                lines.append(
                    {
                        "layer": layer,
                        "x1": float(entity["x1"]),
                        "y1": float(entity["y1"]),
                        "x2": float(entity["x2"]),
                        "y2": float(entity["y2"]),
                    }
                )

    all_x = []
    all_y = []

    for poly in polygons:
        for x, y in poly["points"]:
            all_x.append(x)
            all_y.append(y)

    for line in lines:
        all_x.extend([line["x1"], line["x2"]])
        all_y.extend([line["y1"], line["y2"]])

    for text in texts:
        all_x.append(float(text.get("x", 0)))
        all_y.append(float(text.get("y", 0)))

    if not all_x or not all_y:
        min_x, min_y, max_x, max_y = 0.0, 0.0, 100.0, 100.0
    else:
        min_x = min(all_x)
        min_y = min(all_y)
        max_x = max(all_x)
        max_y = max(all_y)

    drawing_w = max(max_x - min_x, 1.0)
    drawing_h = max(max_y - min_y, 1.0)
    max_dim = max(drawing_w, drawing_h)

    # 화면에서 너무 작거나 너무 크게 보이지 않도록 스케일 제한
    scale = min(max(720.0 / max_dim, 2.5), 8.0)
    padding = 50.0

    width = drawing_w * scale + padding * 2
    height = drawing_h * scale + padding * 2

    def tx(x: float) -> float:
        return (float(x) - min_x) * scale + padding

    def ty(y: float) -> float:
        return height - ((float(y) - min_y) * scale + padding)

    def esc(value: str) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    polygon_elements = []
    for poly in polygons:
        layer = poly["layer"]
        fill = ROOM_COLORS.get(layer, ROOM_COLORS["room"])

        points_attr = " ".join(
            f"{tx(x):.2f},{ty(y):.2f}"
            for x, y in poly["points"]
        )

        polygon_elements.append(
            f'<polygon points="{points_attr}" '
            f'fill="{fill}" stroke="#111111" stroke-width="2" />'
        )

    line_elements = []
    for line in lines:
        line_elements.append(
            f'<line x1="{tx(line["x1"]):.2f}" y1="{ty(line["y1"]):.2f}" '
            f'x2="{tx(line["x2"]):.2f}" y2="{ty(line["y2"]):.2f}" '
            f'stroke="#111111" stroke-width="2" stroke-linecap="round" />'
        )

    text_elements = []
    for text in texts:
        value = esc(text.get("value", ""))
        if not value:
            continue

        text_height = float(text.get("height", 4.0))

        # DXF height를 SVG scale에 맞춰 변환
        font_size = max(text_height * scale * 0.85, 10.0)

        text_elements.append(
            f'<text x="{tx(text["x"]):.2f}" y="{ty(text["y"]):.2f}" '
            f'font-size="{font_size:.2f}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'font-family="Arial, sans-serif" fill="#1f4ed8">{value}</text>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
  width="{width:.0f}"
  height="{height:.0f}"
  viewBox="0 0 {width:.0f} {height:.0f}">
  <rect width="100%" height="100%" fill="white"/>
  {"".join(polygon_elements)}
  {"".join(line_elements)}
  {"".join(text_elements)}
</svg>'''

    output_path = Path(output_svg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")

    return {
        "ok": True,
        "backend": "python",
        "output_svg": str(output_path),
        "polygon_count": len(polygons),
        "line_count": len(lines),
        "text_count": len(texts),
        "bbox": [min_x, min_y, max_x, max_y],
    }