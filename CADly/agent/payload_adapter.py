from typing import Any, Dict

from planning.rplan_room_types import cadly_room_type_to_rplan_id


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
                "type": cadly_room_type_to_rplan_id(room_type),
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