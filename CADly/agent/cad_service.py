from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Literal, Tuple

from design.mcp_client import call_cad_import_tool_async

CadTarget = Literal["autocad", "rhino"]

_DEFAULT_RHINO_APP = "/Applications/Rhino 8.app"


def _parse_mcp_import_result(mcp_result: Dict[str, Any]) -> Tuple[bool, str]:
    if not mcp_result.get("ok"):
        return False, mcp_result.get("message", "MCP 호출에 실패했습니다.")

    inner = mcp_result.get("result")
    if isinstance(inner, dict):
        if "ok" in inner:
            return bool(inner.get("ok")), str(inner.get("message") or "")
        if inner.get("text"):
            return False, str(inner["text"])

    return True, str(mcp_result.get("message") or "CAD 앱에서 DXF를 열었습니다.")


async def import_dxf_to_cad(
    *,
    dxf_path: str,
    target_cad: CadTarget,
    rhino_exe_path: str | None = None,
) -> Dict[str, Any]:
    path = Path(dxf_path).resolve()
    if not path.is_file():
        return {
            "ok": False,
            "message": f"DXF 파일을 찾을 수 없습니다: {path}",
            "dxf_path": str(path),
            "target_cad": target_cad,
        }

    if path.suffix.lower() != ".dxf":
        return {
            "ok": False,
            "message": "DXF 파일만 CAD 연동할 수 있습니다.",
            "dxf_path": str(path),
            "target_cad": target_cad,
        }

    resolved = str(path)
    if target_cad == "autocad":
        mcp_result = await call_cad_import_tool_async(
            "import_to_autocad",
            {"dxf_path": resolved},
        )
    elif target_cad == "rhino":
        mcp_result = await call_cad_import_tool_async(
            "import_to_rhino",
            {
                "dxf_path": resolved,
                "rhino_exe_path": rhino_exe_path or os.getenv("RHINO_APP_PATH", _DEFAULT_RHINO_APP),
            },
        )
    else:
        return {
            "ok": False,
            "message": f"지원하지 않는 CAD 대상입니다: {target_cad}",
            "dxf_path": resolved,
            "target_cad": target_cad,
        }

    ok, message = _parse_mcp_import_result(mcp_result)
    return {
        "ok": ok,
        "message": message or ("CAD 앱에서 DXF를 열었습니다." if ok else "CAD 앱 열기에 실패했습니다."),
        "dxf_path": resolved,
        "target_cad": target_cad,
        "cad_import_result": mcp_result,
    }


def read_dxf_bytes(dxf_path: str) -> Tuple[bytes, str]:
    path = Path(dxf_path).resolve()
    if not path.is_file() or path.suffix.lower() != ".dxf":
        raise FileNotFoundError(f"DXF file not found: {path}")
    return path.read_bytes(), path.name
