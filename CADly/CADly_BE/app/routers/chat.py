import re
from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest
from app.services.agent_service import send_to_agent

router = APIRouter()

@router.post("/{agent_type}") # api.js에서 /chat/{agentType} 으로 찌르고 있으므로 경로 수정
async def chat(agent_type: str, request: ChatRequest):
    try:
        agent_response = await send_to_agent(
            message=request.message,
            agent_type=agent_type,
            session_id=request.project_id # api.js에서 project_id로 넘기고 있음
        )
        
        # 에이전트 응답 텍스트
        raw_text = agent_response["response"]
        
        # 정규식을 사용하여 "imageUrl: https://..." 패턴에서 URL만 추출
        image_urls = re.findall(r"imageUrl:\s*(https?://[^\s]+)", raw_text)

        return {
            "success": True,
            "agent_type": agent_type,
            "message": raw_text, 
            "image_urls": image_urls # 추출된 이미지 URL 리스트를 함께 반환
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )