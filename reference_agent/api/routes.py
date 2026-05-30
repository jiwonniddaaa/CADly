# reference_agent/api/routes.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from reference_agent.agents.reference_agent import ReferenceAgent

router = APIRouter()
agent = ReferenceAgent()

# 프론트에서 받을 요청 데이터 형식
class ChatRequest(BaseModel):
    query: str
    chat_history: Optional[List] = None
    concept_state: Optional[Dict[str, Any]] = None

@router.post('/chat')
def reference_agent_query(req: ChatRequest):
    """
    사용자의 질문을 받아 레퍼런스 에이전트를 실행하고 결과를 반환합니다.
    """
    return agent.chat(
        user_input=req.query,
        chat_history=req.chat_history,
        concept_state=req.concept_state,
    )