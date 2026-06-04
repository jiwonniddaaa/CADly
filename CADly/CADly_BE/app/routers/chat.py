from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent_service import send_to_agent
import re

router = APIRouter()

@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # 1. AI 에이전트로 데이터 전송
        agent_response = await send_to_agent(
            message=request.message, 
            session_id=request.session_id
        )
        
        raw_text = agent_response.get("response", "")
        
        # 2. 이미지 URL 추출 파이프라인
        image_urls = agent_response.get("image_urls", [])
        if not image_urls:
            # 에이전트가 생 텍스트로 'imageUrl: http...'을 줄 경우를 대비한 정규식 방어 코드
            urls = re.findall(r'(https?://[^\s]+)', raw_text)
            image_urls = [url for url in urls if url.endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            
        # 3. 도면 데이터가 포함되었는지 확인
        cad_svg_content = agent_response.get("cad_svg_content", None)

        return ChatResponse(
            response=raw_text,
            image_urls=image_urls,
            cad_svg_content=cad_svg_content
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))