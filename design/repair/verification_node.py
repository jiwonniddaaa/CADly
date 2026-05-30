from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Tuple

from design.state import CADlyGenerationState


SVG_SHAPE_TAGS = {
    "path",
    "polygon",
    "polyline",
    "rect",
    "line",
    "circle",
    "ellipse",
}

DXF_GEOMETRY_TYPES = {
    "LINE",
    "LWPOLYLINE",
    "POLYLINE",
    "HATCH",
    "CIRCLE",
    "ARC",
}

DXF_TEXT_TYPES = {
    "TEXT",
    "MTEXT",
}

def _local_name(tag: str) -> str:
    """
    Remove XML namespace from tag.

    Example:
    {http://www.w3.org/2000/svg}svg -> svg
    """
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag

def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _extract_input_rooms(state: CADlyGenerationState) -> List[Dict[str, Any]]:
    """
    Prefer graph_data from state.
    Fallback to graph_json_path if graph_data is missing.
    """
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

def _extract_room_label_items(room_label_data: Any) -> List[Dict[str, Any]]:
    """
    Accept multiple possible room label JSON shapes.

    Supported examples:
    1. [{"id": "...", "type": 0, ...}, ...]
    2. {"rooms": [...]}
    3. {"room_meta": [...]}
    4. {"labels": [...]}
    """
    if isinstance(room_label_data, list):
        return [item for item in room_label_data if isinstance(item, dict)]

    if not isinstance(room_label_data, dict):
        return []

    for key in ["rooms", "room_meta", "labels", "room_labels"]:
        value = room_label_data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []

def _room_output_id(room: Dict[str, Any]) -> str | None:
    value = room.get("id") or room.get("room_id")
    return str(value) if value is not None else None

def _room_output_type(room: Dict[str, Any]) -> int | None:
    value = room.get("type", room.get("room_type"))
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None

def _input_area_by_id(input_rooms: List[Dict[str, Any]]) -> Dict[str, float]:
    result: Dict[str, float] = {}

    for room in input_rooms:
        room_id = room.get("id")
        area = room.get("area")

        if room_id is None or area is None:
            continue

        try:
            area_value = float(area)
        except Exception:
            continue

        if area_value > 0:
            result[str(room_id)] = area_value

    return result

def _bbox_intersection_area(a: List[float], b: List[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)

def _bbox_area(bbox: List[float]) -> float:
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)

def _bbox_gap(a: List[float], b: List[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    dx = max(bx1 - ax2, ax1 - bx2, 0.0)
    dy = max(by1 - ay2, ay1 - by2, 0.0)

    return math.sqrt(dx * dx + dy * dy)

def _extract_input_edges(state: CADlyGenerationState) -> List[Tuple[str, str]]:
    graph_data = state.get("graph_data")

    if not isinstance(graph_data, dict):
        graph_json_path = state.get("graph_json_path")
        if not graph_json_path:
            return []

        path = Path(graph_json_path)
        if not path.exists():
            return []

        try:
            graph_data = _read_json(path)
        except Exception:
            return []

    edges = graph_data.get("edges", [])
    result: List[Tuple[str, str]] = []

    for edge in edges:
        if isinstance(edge, dict):
            source = edge.get("source")
            target = edge.get("target")
        elif isinstance(edge, (list, tuple)) and len(edge) == 2:
            source, target = edge
        else:
            continue

        if source is None or target is None:
            continue

        result.append((str(source), str(target)))

    return result

def _is_finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except Exception:
        return False

    return math.isfinite(number)

def _check_dxf_entity_coordinates(entity: Any) -> bool:
    """
    Lightweight coordinate sanity check for common DXF entities.
    Returns True if entity has plausible finite coordinates.
    """
    dxftype = entity.dxftype()

    try:
        if dxftype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            return all(_is_finite_number(v) for v in [start.x, start.y, end.x, end.y])

        if dxftype == "LWPOLYLINE":
            points = list(entity.get_points())
            if not points:
                return False
            for point in points:
                x, y = point[0], point[1]
                if not _is_finite_number(x) or not _is_finite_number(y):
                    return False
            return True

        if dxftype == "POLYLINE":
            points = list(entity.points())
            if not points:
                return False
            for point in points:
                if not _is_finite_number(point.x) or not _is_finite_number(point.y):
                    return False
            return True

        if dxftype in {"TEXT", "MTEXT"}:
            insert = entity.dxf.insert
            return _is_finite_number(insert.x) and _is_finite_number(insert.y)

        if dxftype in {"CIRCLE", "ARC"}:
            center = entity.dxf.center
            return _is_finite_number(center.x) and _is_finite_number(center.y)

    except Exception:
        return False

    return True

def verify_svg_file(svg_path: Path) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if not svg_path.exists():
        return [f"SVG file not found: {svg_path}"], warnings

    if svg_path.stat().st_size == 0:
        return [f"SVG file is empty: {svg_path}"], warnings

    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
    except Exception as e:
        return [f"SVG file cannot be parsed: {e}"], warnings

    root_name = _local_name(root.tag)

    if root_name.lower() != "svg":
        errors.append(f"SVG root tag must be <svg>, got <{root_name}>.")

    has_viewbox = "viewBox" in root.attrib
    has_size = "width" in root.attrib and "height" in root.attrib

    if not has_viewbox and not has_size:
        warnings.append("SVG has neither viewBox nor width/height attributes.")

    shape_count = 0
    empty_geometry_count = 0

    for elem in root.iter():
        tag = _local_name(elem.tag).lower()

        if tag not in SVG_SHAPE_TAGS:
            continue

        shape_count += 1

        if tag == "path":
            if not elem.attrib.get("d"):
                empty_geometry_count += 1

        elif tag in {"polygon", "polyline"}:
            if not elem.attrib.get("points"):
                empty_geometry_count += 1

        elif tag == "rect":
            required = ["x", "y", "width", "height"]
            if not all(key in elem.attrib for key in required):
                empty_geometry_count += 1

        elif tag == "line":
            required = ["x1", "y1", "x2", "y2"]
            if not all(key in elem.attrib for key in required):
                empty_geometry_count += 1

    if shape_count == 0:
        errors.append("SVG contains no drawable geometry elements.")

    if empty_geometry_count > 0:
        warnings.append(
            f"SVG contains {empty_geometry_count} geometry elements with missing coordinate attributes."
        )

    return errors, warnings

def verify_dxf_file(dxf_path: Path) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if not dxf_path.exists():
        return [f"DXF file not found: {dxf_path}"], warnings

    if dxf_path.stat().st_size == 0:
        return [f"DXF file is empty: {dxf_path}"], warnings

    try:
        import ezdxf
    except ImportError:
        warnings.append(
            "ezdxf is not installed. DXF structure validation was skipped. "
            "Install with: pip install ezdxf"
        )
        return errors, warnings

    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        return [f"DXF file cannot be parsed by ezdxf: {e}"], warnings

    try:
        msp = doc.modelspace()
    except Exception as e:
        return [f"DXF modelspace cannot be accessed: {e}"], warnings

    entities = list(msp)

    if not entities:
        errors.append("DXF modelspace contains no entities.")
        return errors, warnings

    geometry_count = 0
    text_count = 0
    invalid_coord_count = 0

    for entity in entities:
        dxftype = entity.dxftype()

        if dxftype in DXF_GEOMETRY_TYPES:
            geometry_count += 1

        if dxftype in DXF_TEXT_TYPES:
            text_count += 1

        if dxftype in DXF_GEOMETRY_TYPES or dxftype in DXF_TEXT_TYPES:
            if not _check_dxf_entity_coordinates(entity):
                invalid_coord_count += 1

    if geometry_count == 0:
        errors.append(
            "DXF contains no geometric entities. "
            f"Expected one of: {sorted(DXF_GEOMETRY_TYPES)}."
        )

    if text_count == 0:
        warnings.append("DXF contains no TEXT/MTEXT room label entities.")

    if invalid_coord_count > 0:
        warnings.append(
            f"DXF contains {invalid_coord_count} entities with invalid or missing coordinates."
        )

    return errors, warnings

def load_room_label_rooms(
    room_label_path: Path,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if not room_label_path.exists():
        warnings.append(f"Room label file not found: {room_label_path}")
        return [], errors, warnings

    if room_label_path.stat().st_size == 0:
        warnings.append(f"Room label file is empty: {room_label_path}")
        return [], errors, warnings

    try:
        room_label_data = _read_json(room_label_path)
    except Exception as e:
        errors.append(f"Room label JSON exists but cannot be parsed: {e}")
        return [], errors, warnings

    output_rooms = _extract_room_label_items(room_label_data)

    if not output_rooms:
        warnings.append("Room label JSON does not contain recognizable room metadata.")
        return [], errors, warnings

    return output_rooms, errors, warnings

def verify_room_label_consistency(
    input_rooms: List[Dict[str, Any]],
    output_rooms: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    input_count = len(input_rooms)
    output_count = len(output_rooms)

    if input_count > 0 and output_count != input_count:
        warnings.append(
            f"Room count mismatch: input graph has {input_count} rooms, "
            f"room label JSON has {output_count} rooms."
        )

    input_ids = {
        str(room.get("id"))
        for room in input_rooms
        if isinstance(room, dict) and room.get("id") is not None
    }

    output_ids = {
        str(_room_output_id(room))
        for room in output_rooms
        if _room_output_id(room) is not None
    }

    if input_ids and output_ids:
        missing_ids = sorted(input_ids - output_ids)

        if missing_ids:
            warnings.append(
                "Room label JSON is missing input room ids: "
                + ", ".join(missing_ids)
            )

    input_types = [
        int(room["type"])
        for room in input_rooms
        if isinstance(room, dict) and "type" in room
    ]

    output_types = [
        output_type
        for output_type in (_room_output_type(room) for room in output_rooms)
        if output_type is not None
    ]

    if input_types and output_types:
        missing_types = sorted(set(input_types) - set(output_types))

        if missing_types:
            warnings.append(
                "Room label JSON is missing input room types: "
                + ", ".join(str(t) for t in missing_types)
            )

    return errors, warnings

def verify_room_geometry_metadata(
    output_rooms: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    for room in output_rooms:
        room_id = _room_output_id(room) or "<unknown>"

        polygon = room.get("polygon")
        bbox = room.get("bbox")
        area_px = room.get("area_px")
        point_count = room.get("point_count")
        is_closed = room.get("is_closed")
        is_degenerate = room.get("is_degenerate")

        if not isinstance(polygon, list) or len(polygon) < 3:
            errors.append(f"Room {room_id} has invalid polygon.")
            continue

        if point_count is not None and int(point_count) < 3:
            errors.append(f"Room {room_id} has fewer than 3 polygon points.")

        if bbox is None or not isinstance(bbox, list) or len(bbox) != 4:
            errors.append(f"Room {room_id} has invalid bbox.")
        else:
            bbox_values_valid = all(_is_finite_number(v) for v in bbox)
            if not bbox_values_valid:
                errors.append(f"Room {room_id} bbox contains non-finite values.")
            elif _bbox_area([float(v) for v in bbox]) <= 1e-6:
                errors.append(f"Room {room_id} bbox area is zero or near zero.")

        if area_px is None:
            warnings.append(f"Room {room_id} is missing area_px.")
        else:
            try:
                area_value = float(area_px)
                if area_value <= 1e-6:
                    errors.append(f"Room {room_id} polygon area is zero or near zero.")
            except Exception:
                errors.append(f"Room {room_id} area_px is not numeric.")

        if is_closed is False:
            warnings.append(f"Room {room_id} polygon is marked as not closed.")

        if is_degenerate is True:
            errors.append(f"Room {room_id} is marked as degenerate.")

    return errors, warnings

def verify_area_ratio_consistency(
    input_rooms: List[Dict[str, Any]],
    output_rooms: List[Dict[str, Any]],
    tolerance: float = 0.35,
) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    input_area = _input_area_by_id(input_rooms)

    if not input_area:
        return errors, warnings

    output_area: Dict[str, float] = {}

    for room in output_rooms:
        room_id = _room_output_id(room)
        area_px = room.get("area_px")

        if room_id is None or area_px is None:
            continue

        try:
            value = float(area_px)
        except Exception:
            continue

        if value > 0:
            output_area[room_id] = value

    common_ids = sorted(set(input_area) & set(output_area))

    if len(common_ids) < 2:
        warnings.append(
            "Area ratio verification skipped because fewer than two rooms have both input area and output area_px."
        )
        return errors, warnings

    input_total = sum(input_area[room_id] for room_id in common_ids)
    output_total = sum(output_area[room_id] for room_id in common_ids)

    if input_total <= 0 or output_total <= 0:
        warnings.append("Area ratio verification skipped because total area is zero.")
        return errors, warnings

    for room_id in common_ids:
        input_ratio = input_area[room_id] / input_total
        output_ratio = output_area[room_id] / output_total

        diff = abs(input_ratio - output_ratio)

        if diff > tolerance:
            warnings.append(
                f"Room {room_id} area ratio mismatch: "
                f"input={input_ratio:.3f}, output={output_ratio:.3f}, diff={diff:.3f}."
            )

    return errors, warnings

def verify_bbox_overlap(
    output_rooms: List[Dict[str, Any]],
    max_overlap_ratio: float = 0.25,
) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    rooms_with_bbox = []

    for room in output_rooms:
        room_id = _room_output_id(room)
        bbox = room.get("bbox")

        if room_id is None or not isinstance(bbox, list) or len(bbox) != 4:
            continue

        try:
            bbox_values = [float(v) for v in bbox]
        except Exception:
            continue

        area = _bbox_area(bbox_values)

        if area <= 1e-6:
            continue

        rooms_with_bbox.append((room_id, bbox_values, area))

    for i in range(len(rooms_with_bbox)):
        id_a, bbox_a, area_a = rooms_with_bbox[i]

        for j in range(i + 1, len(rooms_with_bbox)):
            id_b, bbox_b, area_b = rooms_with_bbox[j]

            intersection = _bbox_intersection_area(bbox_a, bbox_b)

            if intersection <= 0:
                continue

            ratio = intersection / min(area_a, area_b)

            if ratio > max_overlap_ratio:
                warnings.append(
                    f"Rooms {id_a} and {id_b} have high bbox overlap: ratio={ratio:.3f}."
                )

    return errors, warnings

def verify_adjacency_satisfaction(
    state: CADlyGenerationState,
    output_rooms: List[Dict[str, Any]],
    max_gap_px: float = 12.0,
) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    edges = _extract_input_edges(state)

    if not edges:
        return errors, warnings

    room_bbox: Dict[str, List[float]] = {}

    for room in output_rooms:
        room_id = _room_output_id(room)
        bbox = room.get("bbox")

        if room_id is None or not isinstance(bbox, list) or len(bbox) != 4:
            continue

        try:
            room_bbox[room_id] = [float(v) for v in bbox]
        except Exception:
            continue

    for source, target in edges:
        if source not in room_bbox or target not in room_bbox:
            warnings.append(
                f"Adjacency check skipped for edge {source}-{target}: missing output bbox."
            )
            continue

        gap = _bbox_gap(room_bbox[source], room_bbox[target])

        if gap > max_gap_px:
            warnings.append(
                f"Adjacency may not be satisfied for edge {source}-{target}: bbox gap={gap:.2f}px."
            )

    return errors, warnings

def verify_generated_floorplan(state: CADlyGenerationState) -> CADlyGenerationState:
    if state.get("status") != "completed":
        return state

    errors: List[str] = []
    warnings: List[str] = []

    svg_path = Path(state.get("svg_path", ""))
    dxf_path = Path(state.get("dxf_path", ""))
    room_label_path = Path(state.get("room_label_path", ""))

    # file-level verification
    svg_errors, svg_warnings = verify_svg_file(svg_path)
    dxf_errors, dxf_warnings = verify_dxf_file(dxf_path)

    errors.extend(svg_errors)
    warnings.extend(svg_warnings)

    errors.extend(dxf_errors)
    warnings.extend(dxf_warnings)

    # load room data
    input_rooms = _extract_input_rooms(state)
    
    output_rooms, label_load_errors, label_load_warnings = load_room_label_rooms(
        room_label_path
    )

    errors.extend(label_load_errors)
    warnings.extend(label_load_warnings)

    if output_rooms:
        # graph consistency verification
        label_errors, label_warnings = verify_room_label_consistency(
            input_rooms=input_rooms,
            output_rooms=output_rooms,
        )
        errors.extend(label_errors)
        warnings.extend(label_warnings)

        # geometry metadata verification
        geometry_errors, geometry_warnings = verify_room_geometry_metadata(
            output_rooms
        )
        errors.extend(geometry_errors)
        warnings.extend(geometry_warnings)

        # area ratio verification
        area_errors, area_warnings = verify_area_ratio_consistency(
            input_rooms=input_rooms,
            output_rooms=output_rooms,
        )
        errors.extend(area_errors)
        warnings.extend(area_warnings)

        # overlap verification
        overlap_errors, overlap_warnings = verify_bbox_overlap(
            output_rooms
        )
        errors.extend(overlap_errors)
        warnings.extend(overlap_warnings)

        adjacency_errors, adjacency_warnings = verify_adjacency_satisfaction(
            state=state,
            output_rooms=output_rooms,
        )
        errors.extend(adjacency_errors)
        warnings.extend(adjacency_warnings)

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