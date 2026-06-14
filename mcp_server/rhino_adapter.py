from __future__ import annotations

from pathlib import Path
import subprocess


def import_dxf_to_rhino(dxf_path: str, rhino_exe_path: str | None = None) -> dict:
    path = Path(dxf_path).resolve()

    if not path.exists():
        return {
            "ok": False,
            "message": f"DXF file not found: {path}",
        }

    if path.suffix.lower() != ".dxf":
        return {
            "ok": False,
            "message": f"Expected .dxf file, got: {path.suffix}",
        }

    try:
        # macOS
        subprocess.Popen(["open", "-a", "Rhino 8", str(path)])

        return {
            "ok": True,
            "message": "DXF opened in Rhino.",
            "path": str(path),
        }

    except Exception as e:
        return {
            "ok": False,
            "message": f"Failed to open DXF in Rhino: {e}",
            "path": str(path),
        }