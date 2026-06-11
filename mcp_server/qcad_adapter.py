from __future__ import annotations

from pathlib import Path
import subprocess


def import_dxf_to_qcad(
    dxf_path: str,
    qcad_app_path: str | None = None,
) -> dict:
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
            "path": str(path),
        }

    try:
        if qcad_app_path:
            command = ["open", "-a", qcad_app_path, str(path)]
        else:
            command = ["open", "-a", "QCAD", str(path)]

        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )

        return {
            "ok": True,
            "message": "QCAD launch command succeeded. Check QCAD to confirm the DXF is displayed correctly.",
            "path": str(path),
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    except subprocess.CalledProcessError as e:
        return {
            "ok": False,
            "message": f"Failed to open DXF in QCAD: {e.stderr.strip() or e}",
            "path": str(path),
            "stdout": e.stdout,
            "stderr": e.stderr,
        }

    except Exception as e:
        return {
            "ok": False,
            "message": f"Unexpected QCAD import error: {e}",
            "path": str(path),
        }