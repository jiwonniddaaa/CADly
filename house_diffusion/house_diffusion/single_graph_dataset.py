"""
Single-graph inference adapter for HouseDiffusion.

Purpose:
- Accept one CADly graph JSON at inference time.
- Build the model input tensor and model_kwargs directly in memory.
- No RPLAN list.txt scanning.
- No processed_rplan/*.npz cache read/write.

Expected JSON shape:

{
  "rooms": [
    {"id": "living", "type": 1, "label": "Living Room", "corners": 4},
    {"id": "kitchen", "type": 3, "label": "Kitchen", "corners": 4}
  ],
  "edges": [
    ["living", "kitchen"]
  ]
}

Room type ids should match the labels used during HouseDiffusion training.
For your modified setting, keep the same id range used in image_sample_modified.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch as th
from torch.utils.data import Dataset, DataLoader


def get_one_hot(index: int, size: int) -> np.ndarray:
    arr = np.zeros(size, dtype=np.float32)
    arr[index] = 1.0
    return arr


@dataclass
class RoomSpec:
    id: str
    type: int
    label: str
    corners: int = 4


class SingleGraphDataset(Dataset):
    """
    Dataset with length 1.

    HouseDiffusion expects:
    - data_sample: coordinate tensor shaped [2, max_num_points] when analog_bit=False
    - model_kwargs: masks, room types, indices, connections, graph triples

    During inference, coordinates are zeros because the model generates coordinates.
    The condition is carried by syn_* fields, since image_sample.py uses is_syn=True
    for predicted outputs.
    """

    def __init__(
        self,
        graph_json: str | Path | dict[str, Any],
        analog_bit: bool = False,
        max_num_points: int = 100,
        max_graph_edges: int = 200,
        num_room_types: int = 25,
        max_room_index: int = 32,
        max_corner_index: int = 32,
        add_negative_edges: bool = True,
        connect_isolated_to_first_room: bool = True,
    ) -> None:
        self.analog_bit = analog_bit
        self.max_num_points = max_num_points
        self.max_graph_edges = max_graph_edges
        self.num_room_types = num_room_types
        self.max_room_index = max_room_index
        self.max_corner_index = max_corner_index
        self.add_negative_edges = add_negative_edges
        self.connect_isolated_to_first_room = connect_isolated_to_first_room

        if isinstance(graph_json, (str, Path)):
            with open(graph_json, "r", encoding="utf-8") as f:
                graph = json.load(f)
        else:
            graph = graph_json

        self.graph = graph
        self.rooms = self._parse_rooms(graph)
        self.edge_pairs = self._parse_edges(graph, self.rooms)

        self.house, self.cond, self.room_meta = self._build_condition()

    def __len__(self) -> int:
        return 1

    def __getitem__(self, idx: int):
        arr = self.house[:, :2]  # [max_num_points, 2], all zeros at inference

        graph = np.concatenate(
            [self.cond["graph_raw"], np.zeros((self.max_graph_edges - len(self.cond["graph_raw"]), 3), dtype=np.float32)],
            axis=0,
        )

        cond = {
            "door_mask": self.cond["door_mask"],
            "self_mask": self.cond["self_mask"],
            "gen_mask": self.cond["gen_mask"],
            "room_types": self.house[:, 2:27],
            "corner_indices": self.house[:, 27:59],
            "room_indices": self.house[:, 59:91],
            "src_key_padding_mask": 1 - self.house[:, 91],
            "connections": self.house[:, 92:94],
            "graph": graph,

            # Predicted sample saving path in your modified image_sample.py reads syn_* when is_syn=True.
            "syn_door_mask": self.cond["door_mask"],
            "syn_self_mask": self.cond["self_mask"],
            "syn_gen_mask": self.cond["gen_mask"],
            "syn_room_types": self.house[:, 2:27],
            "syn_corner_indices": self.house[:, 27:59],
            "syn_room_indices": self.house[:, 59:91],
            "syn_src_key_padding_mask": 1 - self.house[:, 91],
            "syn_connections": self.house[:, 92:94],
            "syn_graph": graph,

            # Non-tensor metadata. Keep this out before .cuda() in sampling.
            "room_meta": self.room_meta,
        }

        if not self.analog_bit:
            arr = np.transpose(arr, [1, 0])  # [2, max_num_points]
            return arr.astype(np.float32), cond

        raise NotImplementedError("analog_bit=True is not implemented for CADly single-graph inference.")

    def _parse_rooms(self, graph: dict[str, Any]) -> list[RoomSpec]:
        rooms: list[RoomSpec] = []
        for i, room in enumerate(graph.get("rooms", [])):
            room_id = str(room.get("id", f"room_{i}"))
            room_type = int(room["type"])
            label = str(room.get("label", room_id))
            corners = int(room.get("corners", 4))
            if corners < 3:
                raise ValueError(f"Room {room_id} must have at least 3 corners.")
            if corners >= self.max_corner_index:
                raise ValueError(f"Room {room_id} corners={corners} exceeds max_corner_index={self.max_corner_index}.")
            if room_type >= self.num_room_types:
                raise ValueError(f"Room {room_id} type={room_type} exceeds num_room_types={self.num_room_types}.")
            rooms.append(RoomSpec(id=room_id, type=room_type, label=label, corners=corners))

        if not rooms:
            raise ValueError("Input graph JSON must include at least one room.")

        return rooms

    def _parse_edges(self, graph: dict[str, Any], rooms: list[RoomSpec]) -> set[tuple[int, int]]:
        id_to_idx = {room.id: i for i, room in enumerate(rooms)}
        pairs: set[tuple[int, int]] = set()

        for edge in graph.get("edges", []):
            if isinstance(edge, dict):
                a, b = edge["source"], edge["target"]
            else:
                a, b = edge[0], edge[1]

            if str(a) not in id_to_idx or str(b) not in id_to_idx:
                raise ValueError(f"Edge references unknown room: {edge}")

            i, j = id_to_idx[str(a)], id_to_idx[str(b)]
            if i == j:
                continue
            pairs.add(tuple(sorted((i, j))))

        return pairs

    def _build_graph_triples(self) -> np.ndarray:
        triples = []
        n = len(self.rooms)
        for i in range(n):
            for j in range(i + 1, n):
                if (i, j) in self.edge_pairs:
                    triples.append([i, 1, j])
                elif self.add_negative_edges:
                    triples.append([i, -1, j])

        if len(triples) > self.max_graph_edges:
            raise ValueError(f"Graph has {len(triples)} triples, exceeds max_graph_edges={self.max_graph_edges}.")

        return np.asarray(triples, dtype=np.float32)

    def _build_condition(self):
        house_rows = []
        corner_bounds = []
        num_points = 0

        for room_index_zero_based, room in enumerate(self.rooms):
            num_corners = room.corners
            coords = np.zeros((num_corners, 2), dtype=np.float32)

            rtype = np.repeat(get_one_hot(room.type, 25)[None, :], num_corners, axis=0)
            # Original HouseDiffusion uses 1-based room index.
            room_index = np.repeat(get_one_hot(room_index_zero_based + 1, 32)[None, :], num_corners, axis=0)
            corner_index = np.asarray([get_one_hot(k, 32) for k in range(num_corners)], dtype=np.float32)

            padding_mask = np.ones((num_corners, 1), dtype=np.float32)

            connections = np.asarray(
                [[k, (k + 1) % num_corners] for k in range(num_corners)],
                dtype=np.float32,
            )
            connections += num_points

            corner_bounds.append((num_points, num_points + num_corners))
            num_points += num_corners

            row = np.concatenate([coords, rtype, corner_index, room_index, padding_mask, connections], axis=1)
            house_rows.append(row)

        house = np.concatenate(house_rows, axis=0)

        if len(house) > self.max_num_points:
            raise ValueError(f"Total corners={len(house)} exceeds max_num_points={self.max_num_points}.")

        padding = np.zeros((self.max_num_points - len(house), 94), dtype=np.float32)
        house = np.concatenate([house, padding], axis=0)

        gen_mask = np.ones((self.max_num_points, self.max_num_points), dtype=np.float32)
        gen_mask[:num_points, :num_points] = 0

        door_mask = np.ones((self.max_num_points, self.max_num_points), dtype=np.float32)
        self_mask = np.ones((self.max_num_points, self.max_num_points), dtype=np.float32)

        connected_any = [False] * len(self.rooms)
        for i, (s_i, e_i) in enumerate(corner_bounds):
            for j, (s_j, e_j) in enumerate(corner_bounds):
                if i == j:
                    self_mask[s_i:e_i, s_j:e_j] = 0
                elif tuple(sorted((i, j))) in self.edge_pairs:
                    door_mask[s_i:e_i, s_j:e_j] = 0
                    connected_any[i] = True
                    connected_any[j] = True

        if self.connect_isolated_to_first_room and len(self.rooms) > 1:
            anchor = 0
            s_a, e_a = corner_bounds[anchor]
            for i, is_connected in enumerate(connected_any):
                if i == anchor or is_connected:
                    continue
                s_i, e_i = corner_bounds[i]
                door_mask[s_i:e_i, s_a:e_a] = 0
                door_mask[s_a:e_a, s_i:e_i] = 0

        cond = {
            "door_mask": door_mask,
            "self_mask": self_mask,
            "gen_mask": gen_mask,
            "graph_raw": self._build_graph_triples(),
        }

        room_meta = [
            {
                "index": i,
                "id": room.id,
                "type": room.type,
                "label": room.label,
                "corners": room.corners,
            }
            for i, room in enumerate(self.rooms)
        ]

        return house, cond, room_meta


def load_single_graph_data(
    graph_json: str | Path | dict[str, Any],
    batch_size: int = 1,
    analog_bit: bool = False,
):
    dataset = SingleGraphDataset(graph_json=graph_json, analog_bit=analog_bit)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0, drop_last=False)
    while True:
        yield from loader
