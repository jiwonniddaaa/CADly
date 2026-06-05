import base64
import mimetypes
import httpx
from typing import Dict, Any
from fastapi import UploadFile
from app.core.config import AI_AGENT_URL as CONFIG_AI_AGENT_URL

# .env 설정이 없으면 로컬 기본값 사용
AI_AGENT_URL = CONFIG_AI_AGENT_URL or "http://localhost:8001"

_SESSION_STATES: Dict[str, Dict[str, Any]] = {}

_STATE_KEYS = (
    "awaiting_concept_confirmation",
    "concept_keywords",
    "concept_result",
    "design_intent",
    "narrative",
    "concept_structured",
)


def _get_session_state(session_id: str) -> Dict[str, Any]:
    return _SESSION_STATES.setdefault(session_id, {})


def _update_session_state(session_id: str, agent_response: Dict[str, Any]) -> Dict[str, Any]:
    state = _get_session_state(session_id)
    for key in _STATE_KEYS:
        if key in agent_response:
            state[key] = agent_response[key]
    return state


async def send_to_agent(message: str, session_id: str, file: UploadFile | None = None) -> Dict[str, Any]:
    """일반 채팅(이미지 첨부 지원) 요청.
    FE multipart를 Agent JSON(/chat)으로 변환하는 어댑터 역할.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload: Dict[str, Any] = {
            "query": message,
        }
        session_state = _get_session_state(session_id)
        if session_state:
            payload["concept_state"] = session_state

        if file:
            content = await file.read()
            payload["image_base64"] = base64.b64encode(content).decode("utf-8")
            payload["image_media_type"] = (
                file.content_type
                or mimetypes.guess_type(file.filename or "")[0]
                or "image/jpeg"
            )

        # Agent는 /chat JSON Body 인터페이스를 사용
        response = await client.post(
            f"{AI_AGENT_URL}/chat",
            json=payload,
        )

        response.raise_for_status()
        agent_response = response.json()
        agent_response["_state"] = _update_session_state(session_id, agent_response)
        return agent_response

async def generate_3d_file(project_id: str, format: str) -> bytes:
    """무거운 3D 파일(바이너리) 생성 요청 (기존 코드 완벽 유지)"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{AI_AGENT_URL}/agent/generate3d",
            json={"project_id": project_id, "format": format}
        )
        response.raise_for_status()
        # JSON이 아닌 원시 바이트(Raw Bytes) 데이터를 그대로 반환
        return response.content