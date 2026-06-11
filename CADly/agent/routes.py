from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from CADly.agent.cad_service import CadTarget, import_dxf_to_cad, read_dxf_bytes
from CADly.agent.chat_service import run_cadly_chat

router = APIRouter()


class ChatRequest(BaseModel):
    query: str = Field(default="", description="텍스트 요청 (이미지와 함께 사용 가능)")
    planning_state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Planning 오케스트레이터 세션 상태 (messages 포함)",
    )
    concept_state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="하위 호환용 레거시 컨셉 상태 (planning_state 없을 때만 사용)",
    )
    chat_history: Optional[List] = Field(
        default=None,
        description="미사용 (planning_state.messages 사용)",
    )
    image_path: Optional[str] = Field(
        default=None,
        description="서버에 저장된 이미지 파일 경로",
    )
    image_base64: Optional[str] = Field(
        default=None,
        description="base64 인코딩 이미지 (data URL 형식도 가능)",
    )
    image_media_type: Optional[str] = Field(
        default=None,
        description="image/jpeg, image/png, image/webp",
    )


@router.post("/chat")
async def cadly_chat(req: ChatRequest):
    """CADly 통합 채팅 (active_orchestrator → Planning 또는 Design)."""
    return await run_cadly_chat(
        query=req.query,
        planning_state=req.planning_state,
        concept_state=req.concept_state,
        image_path=req.image_path,
        image_base64=req.image_base64,
        image_media_type=req.image_media_type,
    )


class CadImportRequest(BaseModel):
    dxf_path: str
    target_cad: CadTarget = "autocad"


@router.post("/cad/import")
async def cad_import(req: CadImportRequest):
    """MCP로 로컬 CAD 앱(AutoCAD/QCAD)에서 DXF를 엽니다."""
    return await import_dxf_to_cad(
        dxf_path=req.dxf_path,
        target_cad=req.target_cad,
    )


@router.get("/cad/dxf")
async def download_dxf(dxf_path: str = Query(..., description="서버에 저장된 DXF 절대 경로")):
    try:
        content, filename = read_dxf_bytes(dxf_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
