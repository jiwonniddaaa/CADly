# reference_agent/api/chat_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from reference_agent.api.design_chat_service import run_design_chat
from reference_agent.api.planning_chat_service import run_planning_chat
from reference_agent.api.session_utils import split_session_blob


async def run_cadly_chat(
    *,
    query: str,
    planning_state: Optional[Dict[str, Any]] = None,
    concept_state: Optional[Dict[str, Any]] = None,
    image_path: Optional[str] = None,
    image_base64: Optional[str] = None,
    image_media_type: Optional[str] = None,
) -> Dict[str, Any]:
    """CLI main.py와 동일: active_orchestrator 기준 Planning/Design 분기."""
    _, active_orchestrator, design_state, _ = split_session_blob(planning_state)

    if active_orchestrator == "design" and design_state.get("graph_data"):
        return await run_design_chat(
            query=query,
            session_state=planning_state,
            image_path=image_path,
            image_base64=image_base64,
            image_media_type=image_media_type,
        )

    result = await run_planning_chat(
        query=query,
        planning_state=planning_state,
        concept_state=concept_state,
        image_path=image_path,
        image_base64=image_base64,
        image_media_type=image_media_type,
    )

    # handoff 직후 Design 자동 실행: HD 입력은 design_state.graph_data (query 아님)
    # Planning이 이미 사용자 확인 메시지를 messages에 넣었으므로 중복 append 금지
    if (
        result.get("active_orchestrator") == "design"
        and result.get("design_state", {}).get("graph_data")
    ):
        return await run_design_chat(
            query="",
            session_state=result.get("planning_state"),
            image_path=image_path,
            image_base64=image_base64,
            image_media_type=image_media_type,
            append_user_message=False,
        )

    return result
