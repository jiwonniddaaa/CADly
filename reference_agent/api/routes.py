# reference_agent/api/routes.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from reference_agent.agents.reference_agent import ReferenceAgent

router = APIRouter()
agent = ReferenceAgent()


class ChatRequest(BaseModel):
    query: str = Field(default="", description="텍스트 요청 (이미지와 함께 사용 가능)")
    chat_history: Optional[List] = None
    concept_state: Optional[Dict[str, Any]] = None
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
def reference_agent_query(req: ChatRequest):
    """
    텍스트·이미지 입력으로 레퍼런스 에이전트를 실행합니다.
    이미지만내면 Vision으로 스타일을 분석해 유사 레퍼런스를 검색합니다.
    """
    return agent.chat(
        user_input=req.query,
        chat_history=req.chat_history,
        concept_state=req.concept_state,
        image_path=req.image_path,
        image_base64=req.image_base64,
        image_media_type=req.image_media_type,
    )
