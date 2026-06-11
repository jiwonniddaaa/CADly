from pydantic import BaseModel, Field
from typing import Any, Dict, Literal, Optional

CadTarget = Literal["autocad", "rhino"]


class CadImportRequest(BaseModel):
    session_id: str
    target_cad: CadTarget = "autocad"
    dxf_path: Optional[str] = None


class CadImportResponse(BaseModel):
    ok: bool
    message: str
    dxf_path: Optional[str] = None
    target_cad: Optional[str] = None
    fallback: Literal["download_dxf"] | None = None
    cad_import_result: Optional[Dict[str, Any]] = None
