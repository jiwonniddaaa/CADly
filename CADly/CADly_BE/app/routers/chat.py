import re
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.schemas.chat import ChatResponse
from app.services.agent_service import send_to_agent

router = APIRouter()

# 응답 모델은 기존 ChatResponse를 유지하되, 요청은 Form과 File로 받습니다.
@router.post("/", response_model=ChatResponse)
async def chat(
    message: str = Form(...),
    session_id: str = Form(...),
    file: UploadFile | None = File(None)
):
    try:
        # 1. AI 에이전트로 데이터 전송 (이미지 파일 포함)
        agent_response = await send_to_agent(
            message=message, 
            session_id=session_id,
            file=file
        )
        
        raw_text = agent_response.get("response", "")
        
        # 2. 이미지 URL 추출 파이프라인 (기존 방어 코드 복원 완벽 적용)
        image_urls = agent_response.get("image_urls", [])
        if not image_urls:
            # 에이전트가 생 텍스트로 URL을 줄 경우를 대비한 정규식 방어 코드
            urls = re.findall(r'(https?://[^\s]+)', raw_text)
            image_urls = [url for url in urls if url.endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            
            # (선택 사항) 프론트엔드 말풍선이 깔끔하도록 본문 텍스트에서 URL 문자열 제거
            for url in urls:
                raw_text = raw_text.replace(url, "").replace("imageUrl:", "").strip()
                
        # 3. 도면 데이터가 포함되었는지 확인
        cad_svg_content = agent_response.get("cad_svg_content", None)

        return ChatResponse(
            response=raw_text,
            image_urls=image_urls,
            cad_svg_content=cad_svg_content
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))