from typing import Any, Dict

ROOM_TYPE_TO_ID = {
    "outside": 0,
    "living_room": 1,
    "kitchen": 2,
    "bedroom": 3,
    "bathroom": 4,
    "entrance": 5,
    "balcony": 6,
    "dining_room": 7,
    "study_room": 8,
    "storage": 9,
    "corridor": 10,
    "unknown": 11,
}


def convert_design_payload_to_graph(design_payload: Dict[str, Any]) -> Dict[str, Any]:
    requirements = design_payload.get("design_requirements") or {}
    spaces = requirements.get("spaces") or []
    edges = requirements.get("edges") or []

    rooms = []
    for space in spaces:
        if not isinstance(space, dict):
            continue

        room_id = space.get("id")
        if not room_id:
            continue

        room_type = str(space.get("room_type") or "unknown")

        rooms.append(
            {
                "id": str(room_id),
                "type": ROOM_TYPE_TO_ID.get(room_type, ROOM_TYPE_TO_ID["unknown"]),
                "label": room_type,
                "room_type": room_type,
                "area": space.get("area"),
                "corners": 4,
            }
        )

    room_ids = {room["id"] for room in rooms}
    normalized_edges = []

    for edge in edges:
        if isinstance(edge, dict):
            source = edge.get("source")
            target = edge.get("target")
        elif isinstance(edge, list) and len(edge) == 2:
            source, target = edge
        else:
            continue

        source = str(source)
        target = str(target)

        if source in room_ids and target in room_ids and source != target:
            normalized_edges.append([source, target])

    return {
        "rooms": rooms,
        "edges": normalized_edges,
    }