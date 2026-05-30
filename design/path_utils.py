from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]   # CADly/
HD_ROOT = PROJECT_ROOT / "house_diffusion"            # CADly/house_diffusion


def resolve_hd_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return HD_ROOT / path