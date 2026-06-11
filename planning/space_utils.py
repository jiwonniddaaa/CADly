from __future__ import annotations

from typing import Any, Dict, List, Tuple

OUTSIDE_ROOM_ID = "outside"


def is_outside_node(node_id: Any) -> bool:
    return str(node_id) == OUTSIDE_ROOM_ID


def is_indoor_space(space: Dict[str, Any]) -> bool:
    if not isinstance(space, dict):
        return False
    return space.get("room_type") != "outside" and space.get("id") != OUTSIDE_ROOM_ID


def indoor_spaces(spaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [space for space in (spaces or []) if is_indoor_space(space)]


def strip_outside_edges(edges: List[Any]) -> List[List[str]]:
    """PlanningState edges: outside 참조 edge 제거."""
    cleaned: List[List[str]] = []
    for edge in edges or []:
        if not isinstance(edge, list) or len(edge) != 2:
            continue
        source, target = str(edge[0]), str(edge[1])
        if is_outside_node(source) or is_outside_node(target):
            continue
        cleaned.append([source, target])
    return cleaned


def outside_boundary_space() -> Dict[str, Any]:
    return {
        "id": OUTSIDE_ROOM_ID,
        "room_type": "outside",
        "area": 0,
        "notes": "auto-added boundary node",
    }


def sum_indoor_space_areas(spaces: List[Dict[str, Any]]) -> float | None:
    """실내 공간 면적 합. 대지 분석 없이 도면 생성 기준 면적으로 쓸 때 사용."""
    total = 0.0
    for space in indoor_spaces(spaces):
        area = space.get("area")
        if isinstance(area, (int, float)) and area > 0:
            total += float(area)
    return round(total, 1) if total > 0 else None


def apply_single_room_generator_fallback(
    spaces: List[Dict[str, Any]],
    edges: List[List[str]],
) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
    """공간 1개 + indoor edge 없음일 때만 generator용 outside boundary 내부 추가."""
    payload_spaces = list(indoor_spaces(spaces))
    payload_edges = strip_outside_edges(edges)

    if len(payload_spaces) == 1 and not payload_edges:
        payload_spaces = payload_spaces + [outside_boundary_space()]
        payload_edges = [[payload_spaces[0]["id"], OUTSIDE_ROOM_ID]]

    return payload_spaces, payload_edges
