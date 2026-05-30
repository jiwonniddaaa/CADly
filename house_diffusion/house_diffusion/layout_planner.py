from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LayoutRoom:
    id: str
    type: int
    label: str
    area: float | None = None
    has_existing_box: bool = False


def _edge_to_pair(edge: Any) -> tuple[str, str]:
    if isinstance(edge, dict):
        return str(edge["source"]), str(edge["target"])

    if isinstance(edge, (list, tuple)) and len(edge) == 2:
        return str(edge[0]), str(edge[1])

    raise ValueError(f"Invalid edge format: {edge}")


def _normalize_rooms(graph: dict[str, Any]) -> list[LayoutRoom]:
    rooms: list[LayoutRoom] = []

    for i, room in enumerate(graph.get("rooms", [])):
        room_id = str(room.get("id", f"room_{i}"))
        room_type = int(room["type"])
        label = str(room.get("label", room_id))

        area = room.get("area")
        if area is not None:
            area = float(area)

        rooms.append(
            LayoutRoom(
                id=room_id,
                type=room_type,
                label=label,
                area=area,
                has_existing_box=room.get("box") is not None,
            )
        )

    if not rooms:
        raise ValueError("layout_planner requires at least one room.")

    return rooms


def _build_adjacency_score(room: LayoutRoom, edges: list[tuple[str, str]]) -> int:
    score = 0

    for a, b in edges:
        if room.id == a or room.id == b:
            score += 1

    return score


def _sort_rooms_for_basic_layout(
    rooms: list[LayoutRoom],
    edges: list[tuple[str, str]],
) -> list[LayoutRoom]:
    """
    Simple heuristic ordering.

    More connected and larger rooms are placed earlier in the horizontal sequence.
    This is not a final architectural solver, but a stable initial layout heuristic.
    """
    return sorted(
        rooms,
        key=lambda room: (
            -_build_adjacency_score(room, edges),
            -(room.area or 1.0),
            room.id,
        ),
    )


def _area_weights(rooms: list[LayoutRoom]) -> dict[str, float]:
    values: dict[str, float] = {}

    for room in rooms:
        if room.area is not None and room.area > 0:
            values[room.id] = float(room.area)
        else:
            values[room.id] = 1.0

    total = sum(values.values())

    if total <= 0:
        return {room.id: 1.0 / len(rooms) for room in rooms}

    return {room_id: value / total for room_id, value in values.items()}


def _normalize_generated_boxes(
    boxes: dict[str, list[float]],
    x_min: float,
    x_max: float,
) -> dict[str, list[float]]:
    if not boxes:
        return boxes

    current_min = min(box[0] for box in boxes.values())
    current_max = max(box[2] for box in boxes.values())

    current_width = current_max - current_min
    target_width = x_max - x_min

    if current_width <= 0:
        return boxes

    scale = target_width / current_width

    normalized: dict[str, list[float]] = {}

    for room_id, box in boxes.items():
        bx1, by1, bx2, by2 = box

        nx1 = x_min + (bx1 - current_min) * scale
        nx2 = x_min + (bx2 - current_min) * scale

        normalized[room_id] = [nx1, by1, nx2, by2]

    return normalized


def generate_basic_area_boxes(
    rooms: list[LayoutRoom],
    edges: list[tuple[str, str]],
) -> dict[str, list[float]]:
    """
    Generate rough rectangular boxes from area ratios.

    Coordinate range:
    x: [-0.9, 0.9]
    y: [-0.55, 0.55]

    Strategy:
    - sort rooms by connectivity and area
    - place rooms horizontally
    - width roughly follows area ratio
    - height is fixed for now

    More architectural layout logic should be added here later,
    not inside single_graph_dataset.py.
    """
    ordered_rooms = _sort_rooms_for_basic_layout(rooms, edges)
    weights = _area_weights(ordered_rooms)

    x_min = -0.9
    x_max = 0.9
    y_min = -0.55
    y_max = 0.55

    total_width = x_max - x_min
    room_count = len(ordered_rooms)

    min_width = min(0.18, total_width / max(room_count, 1) * 0.5)

    cursor = x_min
    boxes: dict[str, list[float]] = {}

    for idx, room in enumerate(ordered_rooms):
        if idx == room_count - 1:
            next_x = x_max
        else:
            width = max(total_width * weights[room.id], min_width)
            next_x = cursor + width

        if next_x <= cursor:
            next_x = cursor + min_width

        boxes[room.id] = [cursor, y_min, next_x, y_max]
        cursor = next_x

    boxes = _normalize_generated_boxes(boxes, x_min=x_min, x_max=x_max)

    return boxes


def apply_layout_planner(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Add box field to rooms when missing.

    Priority:
    1. If a room already has box, keep it.
    2. If a room has area, generated box reflects area ratio.
    3. If a room has no area, equal weight is used.
    """
    rooms = _normalize_rooms(graph)
    edges = [_edge_to_pair(edge) for edge in graph.get("edges", [])]

    generated_boxes = generate_basic_area_boxes(rooms, edges)

    next_rooms: list[dict[str, Any]] = []

    for i, room in enumerate(graph.get("rooms", [])):
        room_id = str(room.get("id", f"room_{i}"))

        if room.get("box") is not None:
            next_rooms.append(
                {
                    **room,
                    "id": room_id,
                }
            )
            continue

        next_rooms.append(
            {
                **room,
                "id": room_id,
                "box": generated_boxes[room_id],
            }
        )

    return {
        **graph,
        "rooms": next_rooms,
    }