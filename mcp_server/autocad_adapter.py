import os
import platform
import subprocess
from pathlib import Path


def import_dxf_to_autocad(dxf_path: str) -> dict:
    path = Path(dxf_path).resolve()

    if not path.exists():
        return {
            "ok": False,
            "message": f"DXF file not found: {path}"
        }

    if path.suffix.lower() != ".dxf":
        return {
            "ok": False,
            "message": "Only .dxf files are supported for AutoCAD import."
        }

    current_os = platform.system().lower()

    if current_os == "windows":
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError:
            return {
                "ok": False,
                "message": (
                    "win32com is not available. Install pywin32 and run on Windows "
                    "for COM-based AutoCAD automation."
                ),
            }

        try:
            acad = win32com.client.Dispatch("AutoCAD.Application")
            acad.Visible = True
            doc = acad.Documents.Open(str(path))
        except Exception as e:
            return {
                "ok": False,
                "message": f"Failed to open DXF in AutoCAD via COM: {e}",
                "path": str(path),
            }

        return {
            "ok": True,
            "message": "DXF opened in AutoCAD via Windows COM automation.",
            "path": str(path),
            "document_name": doc.Name,
            "launch_mode": "win32com",
        }

    if current_os == "darwin":
        autocad_app_name = os.getenv("AUTOCAD_APP_NAME", "AutoCAD")

        try:
            subprocess.run(
                ["open", "-a", autocad_app_name, str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            details = (e.stderr or e.stdout or str(e)).strip()
            return {
                "ok": False,
                "message": (
                    f"Failed to open DXF with '{autocad_app_name}' on macOS. "
                    "Check app name/path and installation."
                ),
                "path": str(path),
                "details": details,
            }

        return {
            "ok": True,
            "message": f"DXF opened in AutoCAD on macOS using '{autocad_app_name}'.",
            "path": str(path),
            "launch_mode": "macos_open",
        }

    return {
        "ok": False,
        "message": (
            f"Unsupported OS '{platform.system()}'. "
            "AutoCAD open is supported on Windows/macOS only."
        ),
        "path": str(path),
    }