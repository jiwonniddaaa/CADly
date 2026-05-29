from __future__ import annotations

import sys
from typing import List

from design.state import CADlyGenerationState
from design.path_utils import HD_ROOT


def validate_generator_graph(state: CADlyGenerationState) -> CADlyGenerationState:
    graph_data = state.get("graph_data")
    errors: List[str] = []

    if not graph_data:
        return {
            **state,
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
            **state,
            "status": "validation_failed",
            "message": "Generator graph validation failed.",
            "validation_errors": errors,
        }

    return {
        **state,
        "status": "validated",
        "message": "Generator graph validation passed.",
        "validation_errors": [],
    }