"""
Export HouseDiffusion polygon output to SVG, DXF, and room-label JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import drawsvg


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


def _to_scalar(value):
    """
    Convert DataLoader-collated values like ['living'] or tensor([1])
    into plain scalar values.
    """
    if hasattr(value, "item"):
        return value.item()

    if isinstance(value, (list, tuple)):
        if len(value) == 1:
            return _to_scalar(value[0])
        return [_to_scalar(v) for v in value]

    return value


def _compute_bbox(polygon):
    """
    polygon: [[x, y], [x, y], ...]
    return: [min_x, min_y, max_x, max_y]
    """
    if not polygon:
        return None

    xs = [float(p[0]) for p in polygon]
    ys = [float(p[1]) for p in polygon]

    return [min(xs), min(ys), max(xs), max(ys)]


def _polygon_area(polygon):
    """
    Shoelace formula.
    """
    if not polygon or len(polygon) < 3:
        return 0.0

    area = 0.0
    n = len(polygon)

    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        area += float(x1) * float(y2) - float(x2) * float(y1)

    return abs(area) / 2.0

    
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
    """
    Attach room metadata to generated polygons.

    room_meta may contain DataLoader-collated values such as ['living'].
    This function normalizes them into scalar values.
    """
    by_index = {}

    for r in room_meta:
        if not isinstance(r, dict):
            continue

        raw_index = r.get("index", r.get("room_index", None))

        if raw_index is None:
            continue

        try:
            # HouseDiffusion room index is 1-based.
            index = int(_to_scalar(raw_index)) + 1
        except Exception:
            continue

        by_index[index] = r

    labeled = []

    for poly in polys:
        room_index = int(poly["room_index"])
        meta = by_index.get(room_index, {})

        room_id = _to_scalar(
            meta.get("room_id", meta.get("id", f"room_{room_index}"))
        )
        label = _to_scalar(
            meta.get("label", room_id)
        )
        room_type = _to_scalar(
            meta.get("room_type", meta.get("type", poly.get("room_type")))
        )

        labeled.append({
            **poly,
            "room_id": room_id,
            "id": room_id,
            "label": label,
            "room_type": int(room_type) if room_type is not None else int(poly["room_type"]),
            "type": int(room_type) if room_type is not None else int(poly["room_type"]),
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

    drawing.save_svg(str(out_path))


def save_room_labels_json(polys, out_path: str | Path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rooms = []

    for p in polys:
        polygon = [[float(x), float(y)] for x, y in p["points"]]

        bbox = _compute_bbox(polygon)
        area_px = _polygon_area(polygon)

        room_id = _to_scalar(p.get("room_id", p.get("id")))
        label = _to_scalar(p.get("label", room_id))
        room_type = _to_scalar(p.get("room_type", p.get("type")))

        is_degenerate = (
            bbox is None
            or len(polygon) < 3
            or area_px <= 1e-6
        )

        rooms.append(
            {
                "room_id": room_id,
                "id": room_id,

                "label": label,

                "room_type": int(room_type) if room_type is not None else None,
                "type": int(room_type) if room_type is not None else None,

                "room_index": int(p["room_index"]),

                "polygon": polygon,
                "bbox": bbox,
                "area_px": area_px,

                "point_count": len(polygon),
                "is_closed": True,
                "is_degenerate": bool(is_degenerate),
            }
        )

    payload = {
        "rooms": rooms
    }

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
        label = _to_scalar(poly.get("label", f"room_{poly['room_index']}"))
        layer = str(label)[:255]
        
        if layer not in doc.layers:
            doc.layers.add(layer)

        pts = [(float(x), float(y)) for x, y in poly["points"]]

        if pts[0] != pts[-1]:
            pts.append(pts[0])

        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})

        cx = sum(x for x, _ in pts[:-1]) / (len(pts) - 1)
        cy = sum(y for _, y in pts[:-1]) / (len(pts) - 1)
        
        msp.add_text(
            str(label),
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
