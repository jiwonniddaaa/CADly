"""RPLAN room type IDs for HouseDiffusion (rplanhg / House-GAN++ data reader).

Reference: house_diffusion/house_diffusion/rplanhg_datasets.py reads room_type from
House-GAN++ JSON without remapping.
"""

from __future__ import annotations

# CADly room_type string -> RPLAN numeric id
RPLAN_ROOM_TYPE_IDS: dict[str, int] = {
    "living_room": 1,
    "kitchen": 2,
    "bedroom": 3,
    "bathroom": 4,
    "balcony": 5,
    "entrance": 6,
    "dining_room": 7,
    "study_room": 8,
    "storage": 10,
    "outside": 16,
    "corridor": 16,
    "unknown": 16,
}

RPLAN_DEFAULT_UNKNOWN_TYPE = 16


def cadly_room_type_to_rplan_id(room_type: str) -> int:
    normalized = (room_type or "unknown").strip().lower()
    return RPLAN_ROOM_TYPE_IDS.get(normalized, RPLAN_DEFAULT_UNKNOWN_TYPE)
