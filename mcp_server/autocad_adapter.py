from pathlib import Path
import win32com.client


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

    acad = win32com.client.Dispatch("AutoCAD.Application")
    acad.Visible = True

    doc = acad.Documents.Open(str(path))

    return {
        "ok": True,
        "message": "DXF imported to AutoCAD.",
        "path": str(path),
        "document_name": doc.Name
    }