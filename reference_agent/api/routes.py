# reference_agent/api/routes.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from reference_agent.api.chat_service import run_cadly_chat

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
