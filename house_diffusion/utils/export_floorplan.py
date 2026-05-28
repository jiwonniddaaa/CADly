"""
Export HouseDiffusion polygon output to SVG, DXF, and room-label JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import drawSvg as drawsvg


DEFAULT_ID_COLOR = {
    1: "#EE4D4D", 2: "#C67C7B", 3: "#FFD274", 4: "#BEBEBE",
    5: "#BFE3E8", 6: "#7BA779", 7: "#E87A90", 8: "#FF8C69",
    9: "#A0C4FF", 10: "#1F849B", 11: "#727171", 12: "#D3A2C7",
    13: "#785A67", 14: "#999999"
}


def _to_px(point, resolution: int = 256):
    point = np.asarray(point, dtype=float)
    point = point / 2 + 0.5
    point = point * resolution
    return float(point[0]), float(point[1])


def extract_polygons_from_sample(
    sample_final,
    model_kwargs: dict[str, Any],
    batch_index: int = 0,
    prefix: str = "syn_",
    resolution: int = 256,
):
    """
    sample_final shape after image_sample permute:
    [batch, max_points, 2]
    """
    room_types = model_kwargs[f"{prefix}room_types"][batch_index]
    room_indices = model_kwargs[f"{prefix}room_indices"][batch_index]
    padding_mask = model_kwargs[f"{prefix}src_key_padding_mask"][batch_index]

    if hasattr(sample_final, "detach"):
        sample_final = sample_final.detach().cpu().numpy()
    if hasattr(room_types, "detach"):
        room_types = room_types.detach().cpu().numpy()
    if hasattr(room_indices, "detach"):
        room_indices = room_indices.detach().cpu().numpy()
    if hasattr(padding_mask, "detach"):
        padding_mask = padding_mask.detach().cpu().numpy()

    polys = []
    current_poly = []
    current_room_type = None
    current_room_index = None

    for j, point in enumerate(sample_final):
        if int(padding_mask[j]) == 1:
            continue

        room_index = int(np.argmax(room_indices[j]))
        room_type = int(np.argmax(room_types[j]))

        if current_room_index is None:
            current_room_index = room_index
            current_room_type = room_type

        if room_index != current_room_index:
            if len(current_poly) >= 3:
                polys.append({
                    "room_index": current_room_index,
                    "room_type": current_room_type,
                    "points": current_poly,
                })
            current_poly = []
            current_room_index = room_index
            current_room_type = room_type

        current_poly.append(_to_px(point, resolution=resolution))

    if len(current_poly) >= 3:
        polys.append({
            "room_index": current_room_index,
            "room_type": current_room_type,
            "points": current_poly,
        })

    return polys


def attach_room_labels(polys, room_meta):
    by_index = {int(r["index"]) + 1: r for r in room_meta}  # HouseDiffusion room index is 1-based.
    labeled = []
    for poly in polys:
        meta = by_index.get(int(poly["room_index"]), {})
        labeled.append({
            **poly,
            "room_id": meta.get("id", f"room_{poly['room_index']}"),
            "label": meta.get("label", f"room_{poly['room_index']}"),
        })
    return labeled


def save_svg(polys, out_path: str | Path, resolution: int = 256, colors=None):
    colors = colors or DEFAULT_ID_COLOR
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    drawing = drawsvg.Drawing(resolution, resolution, displayInline=False)
    drawing.append(drawsvg.Rectangle(0, 0, resolution, resolution, fill="white"))

    for poly in polys:
        pts = np.asarray(poly["points"], dtype=float)
        room_type = int(poly["room_type"])
        color = colors.get(room_type, "#CCCCCC")

        drawing.append(
            drawsvg.Lines(
                *pts.flatten().tolist(),
                close=True,
                fill=color,
                fill_opacity=0.55,
                stroke="black",
                stroke_width=1,
            )
        )

        cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
        drawing.append(drawsvg.Text(poly.get("label", ""), 8, cx, cy, center=True, fill="black"))

    drawing.saveSvg(str(out_path))


def save_room_labels_json(polys, out_path: str | Path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "rooms": [
            {
                "room_id": p.get("room_id"),
                "label": p.get("label"),
                "room_type": int(p["room_type"]),
                "room_index": int(p["room_index"]),
                "polygon": [[float(x), float(y)] for x, y in p["points"]],
            }
            for p in polys
        ]
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_dxf(polys, out_path: str | Path):
    """
    Requires: pip install ezdxf
    """
    import ezdxf

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    for poly in polys:
        layer = str(poly.get("label", f"room_{poly['room_index']}"))[:255]
        if layer not in doc.layers:
            doc.layers.add(layer)

        pts = [(float(x), float(y)) for x, y in poly["points"]]
        if pts[0] != pts[-1]:
            pts.append(pts[0])

        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})

        cx = sum(x for x, _ in pts[:-1]) / (len(pts) - 1)
        cy = sum(y for _, y in pts[:-1]) / (len(pts) - 1)
        msp.add_text(
            poly.get("label", ""),
            dxfattribs={"height": 4, "layer": layer},
        ).set_placement((cx, cy))

    doc.saveas(str(out_path))


def export_prediction(sample, model_kwargs, room_meta, out_dir: str | Path, name: str = "floorplan"):
    """
    sample expected shape:
    - after diffusion and permute: [diffusion_steps_or_1, batch, max_points, 2]
      or final only: [batch, max_points, 2]
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if hasattr(sample, "detach"):
        sample = sample.detach().cpu()

    # If sample has diffusion-step dimension, use final step.
    if len(sample.shape) == 4:
        final = sample[-1, 0]
    elif len(sample.shape) == 3:
        final = sample[0]
    else:
        raise ValueError(f"Unexpected sample shape: {sample.shape}")

    polys = extract_polygons_from_sample(final, model_kwargs, batch_index=0, prefix="syn_")
    polys = attach_room_labels(polys, room_meta)

    save_svg(polys, out_dir / f"{name}.svg")
    save_room_labels_json(polys, out_dir / f"{name}_rooms.json")

    try:
        save_dxf(polys, out_dir / f"{name}.dxf")
    except ImportError:
        print("ezdxf is not installed. Skipped DXF export. Run: pip install ezdxf")

    return polys
