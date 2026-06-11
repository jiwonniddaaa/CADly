# design/qcad_dxf_generator.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import math

import ezdxf


ROOM_TYPE_LABELS = {
    1: "living_room",
    2: "kitchen",
    3: "bedroom",
    4: "bathroom",
    5: "balcony",
    6: "entrance",
    7: "dining_room",
    8: "study_room",
    10: "storage",
    16: "unknown",
}

# mm 단위 기준
METER_TO_MM = 1000.0
DEFAULT_ROOM_AREA_M2 = 12.0
DEFAULT_ASPECT_RATIO = 1.25

ROOM_GAP = 0.0
TEXT_HEIGHT = 250.0


def generate_dxf_from_graph_data(
    graph_data: Dict[str, Any],
    output_path: str,
) -> Dict[str, Any]:
    """
    CADly graph_data를 기반으로 HouseDiffusion 없이 직접 DXF를 생성한다.

    Expected graph_data:
    {
        "rooms": [
            {"id": "living_room1", "type": 1, "area": 30.0},
            ...
        ],
        "edges": [
            {"source": "living_room1", "target": "kitchen1"},
            ...
        ],
        "area_for_generation": 84.0
    }
    """
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    rooms = graph_data.get("rooms", [])
    edges = graph_data.get("edges", [])
    area_for_generation = graph_data.get("area_for_generation")

    if not rooms:
        return {
            "ok": False,
            "message": "No rooms found in graph_data.",
        }

    usable_rooms = [
        room for room in rooms
        if str(room.get("id", "")) != "outside"
        and str(room.get("room_type", "")).lower() != "outside"
    ]

    if not usable_rooms:
        return {
            "ok": False,
            "message": "No usable rooms found. Only outside node exists.",
        }

    placed_rooms = _create_simple_layout(
        rooms=usable_rooms,
        total_area_m2=area_for_generation,
        edges=edges,
    )

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    _setup_layers(doc)

    for room in placed_rooms:
        _draw_room(msp, room)

    _draw_adjacency_lines(msp, placed_rooms, edges)

    doc.saveas(output)

    return {
        "ok": True,
        "message": "DXF generated from graph_data using QCAD/ezdxf route.",
        "dxf_path": str(output),
        "room_count": len(placed_rooms),
        "layout": placed_rooms,
    }


def _create_simple_layout(
    rooms: List[Dict[str, Any]],
    total_area_m2: float | None,
    edges: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """
    임시 deterministic layout planner.

    현재 버전:
    - 각 room의 area를 기반으로 width/height 산정
    - area가 없으면 남은 전체 면적을 방 개수 기준으로 분배
    - living_room을 중심 공간으로 먼저 배치
    - 나머지 방은 가로 방향으로 붙이고, 일정 개수 이후 다음 줄로 내림

    나중에 개선 가능:
    - edges 기반 인접 배치 강화
    - corridor 생성
    - wall thickness / door opening 반영
    """
    normalized_rooms = _normalize_room_areas(rooms, total_area_m2)

    # living_room을 먼저 오게 정렬
    normalized_rooms.sort(
        key=lambda room: 0 if room["room_type"] == "living_room" else 1
    )

    placed: List[Dict[str, Any]] = []

    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0

    max_rooms_per_row = _estimate_rooms_per_row(len(normalized_rooms))

    for index, room in enumerate(normalized_rooms):
        width, height = _area_to_room_size_mm(
            area_m2=room["area"],
            room_type=room["room_type"],
        )

        if index > 0 and index % max_rooms_per_row == 0:
            cursor_x = 0.0
            cursor_y += row_height + ROOM_GAP
            row_height = 0.0

        placed_room = {
            **room,
            "x": cursor_x,
            "y": cursor_y,
            "width": width,
            "height": height,
            "center": (
                cursor_x + width / 2.0,
                cursor_y + height / 2.0,
            ),
        }

        placed.append(placed_room)

        cursor_x += width + ROOM_GAP
        row_height = max(row_height, height)

    return placed


def _normalize_room_areas(
    rooms: List[Dict[str, Any]],
    total_area_m2: float | None,
) -> List[Dict[str, Any]]:
    normalized = []

    known_area_sum = 0.0
    missing_area_rooms = []

    for room in rooms:
        area = room.get("area")

        if area is not None:
            try:
                area = float(area)
                if area > 0:
                    known_area_sum += area
                else:
                    area = None
            except Exception:
                area = None

        if area is None:
            missing_area_rooms.append(room)

        normalized.append(
            {
                "id": room.get("id", "room"),
                "type": room.get("type", 16),
                "room_type": ROOM_TYPE_LABELS.get(room.get("type", 16), "unknown"),
                "area": area,
            }
        )

    if missing_area_rooms:
        if total_area_m2 and total_area_m2 > known_area_sum:
            remaining_area = float(total_area_m2) - known_area_sum
            default_area = remaining_area / len(missing_area_rooms)
        else:
            default_area = DEFAULT_ROOM_AREA_M2

        for room in normalized:
            if room["area"] is None:
                room["area"] = default_area

    return normalized


def _area_to_room_size_mm(
    area_m2: float,
    room_type: str,
) -> Tuple[float, float]:
    """
    면적을 단순 직사각형 width/height로 변환.
    area_m2는 ㎡, 반환은 mm.
    """
    area_mm2 = area_m2 * METER_TO_MM * METER_TO_MM

    aspect_ratio = _room_aspect_ratio(room_type)

    width = math.sqrt(area_mm2 * aspect_ratio)
    height = area_mm2 / width

    return width, height


def _room_aspect_ratio(room_type: str) -> float:
    """
    방 유형별 가로세로 비율.
    """
    if room_type == "living_room":
        return 1.55

    if room_type == "kitchen":
        return 1.35

    if room_type == "bedroom":
        return 1.25

    if room_type == "bathroom":
        return 0.85

    if room_type == "entrance":
        return 0.75

    if room_type == "balcony":
        return 2.5

    if room_type == "dining_room":
        return 1.3

    if room_type == "study_room":
        return 1.2

    if room_type == "storage":
        return 0.8

    return DEFAULT_ASPECT_RATIO


def _estimate_rooms_per_row(room_count: int) -> int:
    if room_count <= 2:
        return room_count

    if room_count <= 4:
        return 2

    if room_count <= 6:
        return 3

    return 4


def _setup_layers(doc: ezdxf.document.Drawing) -> None:
    layers = {
        "ROOM_BOUNDARY": 7,
        "ROOM_TEXT": 2,
        "ADJACENCY": 4,
    }

    for layer_name, color in layers.items():
        if layer_name not in doc.layers:
            doc.layers.add(
                name=layer_name,
                color=color,
            )


def _draw_room(
    msp: ezdxf.layouts.Modelspace,
    room: Dict[str, Any],
) -> None:
    x = room["x"]
    y = room["y"]
    w = room["width"]
    h = room["height"]

    points = [
        (x, y),
        (x + w, y),
        (x + w, y + h),
        (x, y + h),
        (x, y),
    ]

    msp.add_lwpolyline(
        points,
        dxfattribs={
            "layer": "ROOM_BOUNDARY",
            "closed": True,
        },
    )

    label = _build_room_label(room)

    text = msp.add_text(
        label,
        dxfattribs={
            "layer": "ROOM_TEXT",
            "height": TEXT_HEIGHT,
        },
    )

    text.dxf.insert = (
        x + w * 0.12,
        y + h * 0.50,
    )


def _build_room_label(room: Dict[str, Any]) -> str:
    room_type = room.get("room_type", "unknown")
    area = room.get("area")

    if area is None:
        return room_type

    return f"{room_type} {area:.1f} m2"


def _draw_adjacency_lines(
    msp: ezdxf.layouts.Modelspace,
    placed_rooms: List[Dict[str, Any]],
    edges: List[Dict[str, str]],
) -> None:
    """
    현재는 인접관계를 시각적으로 확인하기 위해 중심점 간 점선성 line을 그림.
    실제 벽/문 생성은 다음 단계에서 별도 구현하는 게 좋음.
    """
    room_by_id = {
        room["id"]: room
        for room in placed_rooms
    }

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")

        if source == "outside" or target == "outside":
            continue

        source_room = room_by_id.get(source)
        target_room = room_by_id.get(target)

        if not source_room or not target_room:
            continue

        source_center = source_room["center"]
        target_center = target_room["center"]

        msp.add_line(
            source_center,
            target_center,
            dxfattribs={
                "layer": "ADJACENCY",
            },
        )