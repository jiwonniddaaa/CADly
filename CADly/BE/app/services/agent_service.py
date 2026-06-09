import base64
import mimetypes
import httpx
from typing import Dict, Any
from fastapi import UploadFile
from app.core.config import AI_AGENT_URL as CONFIG_AI_AGENT_URL

# .env 설정이 없으면 로컬 기본값 사용
AI_AGENT_URL = CONFIG_AI_AGENT_URL or "http://localhost:8001"

# session_id별 planning_state 캐시 (FE projectId와 1:1 매핑)
_SESSION_STATES: Dict[str, Dict[str, Any]] = {}

# planning_state 외에도 세션에 보존할 오케스트레이터 메타 필드
_SESSION_META_KEYS = (
    "active_orchestrator",
    "design_state",
    "route",
)

# Agent가 planning_state 없이 내려줄 때만 개별 병합하는 레거시 키
_LEGACY_PLANNING_KEYS = (
    "pending_action",
    "concept_keywords",
    "concept",
    "concept_result",
    "design_intent",
    "narrative",
    "concept_structured",
    "concept_updated_at",
    "spaces",
    "edges",
    "design_payload",
    "output_name",
    "building_type",
    "site_analysis",
    "image_type",
)


def _get_session_state(session_id: str) -> Dict[str, Any]:
    return _SESSION_STATES.setdefault(session_id, {})


def clear_session_state(session_id: str) -> None:
    _SESSION_STATES.pop(session_id, None)


def _overlay_session_meta(state: Dict[str, Any], agent_response: Dict[str, Any]) -> None:
    for key in _SESSION_META_KEYS:
        if key in agent_response and agent_response[key] is not None:
            state[key] = agent_response[key]


def _merge_legacy_planning_fields(
    state: Dict[str, Any],
    agent_response: Dict[str, Any],
) -> None:
    for key in _LEGACY_PLANNING_KEYS:
        if key in agent_response:
            state[key] = agent_response[key]

    # concept_result(레거시) -> concept(planning) 매핑
    if "concept_result" in agent_response and "concept" not in state:
        state["concept"] = agent_response["concept_result"]


def _update_session_state(session_id: str, agent_response: Dict[str, Any]) -> Dict[str, Any]:
    state = _get_session_state(session_id)
    planning_state = agent_response.get("planning_state")
    if isinstance(planning_state, dict):
        state.clear()
        state.update(planning_state)
        _overlay_session_meta(state, agent_response)
        return state

    _merge_legacy_planning_fields(state, agent_response)
    _overlay_session_meta(state, agent_response)
    return state


async def send_to_agent(message: str, session_id: str, file: UploadFile | None = None) -> Dict[str, Any]:
    """일반 채팅(이미지 첨부 지원) 요청.
    FE multipart를 Agent JSON(/chat)으로 변환하는 어댑터 역할.
    """
    # Design 파이프라인(HD 샘플링)은 장시간 소요될 수 있음
    async with httpx.AsyncClient(timeout=600.0) as client:
        payload: Dict[str, Any] = {
            "query": message,
        }
        session_state = _get_session_state(session_id)
        if session_state:
            payload["planning_state"] = session_state

        if file:
            content = await file.read()
            payload["image_base64"] = base64.b64encode(content).decode("utf-8")
            payload["image_media_type"] = (
                file.content_type
                or mimetypes.guess_type(file.filename or "")[0]
                or "image/jpeg"
            )

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
    # Design 파이프라인(HD 샘플링)은 장시간 소요될 수 있음
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{AI_AGENT_URL}/agent/generate3d",
            json={"project_id": project_id, "format": format}
        )
        response.raise_for_status()
        return response.content
