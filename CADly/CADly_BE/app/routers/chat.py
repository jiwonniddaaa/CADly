import re
import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import ValidationError
from app.core.config import DEBUG
from app.schemas.chat import ChatResponse
from app.services.agent_service import send_to_agent

router = APIRouter()

# 응답 모델은 기존 ChatResponse를 유지하되, 요청은 Form과 File로 받습니다.
@router.post("/", response_model=ChatResponse, response_model_exclude_none=True)
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

        # 2. Agent 응답 정규화: search_results -> references/image_urls
        search_results = agent_response.get("search_results", [])
        references = search_results if isinstance(search_results, list) else []
        image_urls = agent_response.get("image_urls", [])
        if not image_urls and references:
            image_urls = [
                item.get("imageUrl") or item.get("thumbnail")
                for item in references
                if isinstance(item, dict) and (item.get("imageUrl") or item.get("thumbnail"))
            ]

        # 3. 방어 로직: 텍스트 내 URL 추출
        if not image_urls:
            urls = re.findall(r'(https?://[^\s]+)', raw_text)
            image_urls = [
                url for url in urls
                if re.search(r'\.(png|jpg|jpeg|gif|webp)(\?|$)', url, re.IGNORECASE)
            ]
            
            # 프론트 말풍선 정리를 위해 URL 문자열 제거
            for url in urls:
                raw_text = raw_text.replace(url, "").replace("imageUrl:", "").strip()
                
        # 4. 도면 데이터 포함 여부 확인
        cad_svg_content = agent_response.get("cad_svg_content")
        agent_type = agent_response.get("agent_type") or (
            "reference_agent" if references else "agent"
        )
        debug = None
        if DEBUG:
            debug = {
                "intent": agent_response.get("intent", ""),
                "search_query": agent_response.get("search_query", ""),
                "input_mode": agent_response.get("input_mode", ""),
                "proceed_to_search": agent_response.get("proceed_to_search", False),
            }

        return ChatResponse(
            message=raw_text,
            response=raw_text,
            image_urls=image_urls,
            references=references,
            cad_svg_content=cad_svg_content,
            agent_type=agent_type,
            debug=debug,
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Agent server error: {e.response.status_code}",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Agent server is not reachable.",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))