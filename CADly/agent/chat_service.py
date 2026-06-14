# CADly/agent/chat_service.py
from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from CADly.agent.design_chat_service import run_design_chat
from CADly.agent.planning_chat_service import run_planning_chat
from CADly.agent.session_utils import merge_session_blob, read_svg_content, split_session_blob
from CADly.agent.payload_adapter import convert_design_payload_to_graph

# 도면 완료 후 Design 모드 잠금 안내 (문구는 추후 변경 가능)
DESIGN_MODE_LOCKED_MSG = (
    "도면 생성이 완료되었습니다. 완료된 세션에서는 추가 요청을 처리하지 않습니다. "
    "새 프로젝트를 시작해 주세요."
)


def _sanitize_output_name(raw_name: Optional[str]) -> str:
    name = raw_name or "CADly_Result_001"
    return (
        name.strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )


def _build_design_session_state(
    *,
    planning_state_result: Dict[str, Any],
    design_payload: Dict[str, Any],
    fallback_name: str = "CADly_Result_001",
) -> Dict[str, Any]:
    graph_data = convert_design_payload_to_graph(design_payload)

    if not graph_data.get("rooms"):
        print("⚠️ converted graph_data has no rooms:", graph_data)

    raw_name = (
        planning_state_result.get("output_name")
        or fallback_name
    )
    name = _sanitize_output_name(raw_name)

    patched_design_state = {
        "graph_data": graph_data,
        "name": name,
    }

    return {
        **planning_state_result,
        "active_orchestrator": "design",
        "design_state": patched_design_state,
    }


def _is_design_completed(design_state: Dict[str, Any]) -> bool:
    return (
        design_state.get("status") == "completed"
        and bool(design_state.get("svg_path"))
    )


def _design_mode_locked_response(
    *,
    query: str,
    session_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    messages, _, design_state, planning_fields = split_session_blob(session_state)
    user_text = (query or "").strip()
    if user_text:
        messages = [*messages, HumanMessage(content=user_text)]
    messages = [*messages, AIMessage(content=DESIGN_MODE_LOCKED_MSG)]

    planning_state = merge_session_blob(
        planning_fields,
        messages,
        "design",
        design_state,
    )
    return {
        "response": DESIGN_MODE_LOCKED_MSG,
        "search_results": [],
        "references": [],
        "planning_state": planning_state,
        "active_orchestrator": "design",
        "design_state": design_state,
        "route": "design",
        "agent_type": "design",
        "status": design_state.get("status"),
        "svg_path": design_state.get("svg_path"),
        "dxf_path": design_state.get("dxf_path"),
        "cad_svg_content": read_svg_content(design_state.get("svg_path")),
    }


async def run_cadly_chat(
    *,
    query: str,
    planning_state: Optional[Dict[str, Any]] = None,
    concept_state: Optional[Dict[str, Any]] = None,
    image_path: Optional[str] = None,
    image_base64: Optional[str] = None,
    image_media_type: Optional[str] = None,
) -> Dict[str, Any]:
    """CADly 통합 채팅

    - 도면 완료된 Design 세션이면 모든 요청에 잠금 안내 반환
    - Design 활성화 + graph_data가 있으면 Design orchestrator로 전달
    - 그 외에는 Planning orchestrator를 실행
    - Planning 결과가 handoff_to_design이면 design_payload를 graph_data로 변환한 뒤 Design 자동 실행
    """
    _, active_orchestrator, design_state, _ = split_session_blob(planning_state)

    # 1. 도면 완료 후 Design 모드 잠금 — 추가 요청은 모두 동일 안내
    if active_orchestrator == "design" and _is_design_completed(design_state):
        return _design_mode_locked_response(
            query=query,
            session_state=planning_state,
        )

    # 2. Design 활성화 세션이면 Design 파이프라인 실행
    if active_orchestrator == "design" and design_state.get("graph_data"):
        return await run_design_chat(
            query=query,
            session_state=planning_state,
            image_path=image_path,
            image_base64=image_base64,
            image_media_type=image_media_type,
        )

    # 3. 기본 Planning 실행
    result = await run_planning_chat(
        query=query,
        planning_state=planning_state,
        concept_state=concept_state,
        image_path=image_path,
        image_base64=image_base64,
        image_media_type=image_media_type,
    )

    planning_state_result = result.get("planning_state") or {}

    # 디버깅용
    print("\n========== CADLY CHAT AFTER PLANNING ==========")
    print("active_orchestrator:", result.get("active_orchestrator"))
    print("route:", result.get("route"))
    print("response:", result.get("response"))
    print("design_state:", result.get("design_state"))
    print("design_state keys:", (result.get("design_state") or {}).keys())
    print("graph_data:", (result.get("design_state") or {}).get("graph_data"))
    print("planning_state keys:", (result.get("planning_state") or {}).keys())
    print("==============================================\n")
    
    # 4. Planning 결과가 handoff_to_design이면 design_payload를 graph_data로 변환한 뒤 Design 자동 실행
    design_payload = (
        result.get("design_payload")
        or planning_state_result.get("design_payload")
    )

    if result.get("route") == "handoff_to_design" and design_payload:
        fallback_name = (
            result.get("output_name")
            or planning_state_result.get("output_name")
            or "CADly_Result_001"
        )

        patched_planning_state = _build_design_session_state(
            planning_state_result=planning_state_result,
            design_payload=design_payload,
            fallback_name=fallback_name,
        )

        patched_design_state = patched_planning_state.get("design_state") or {}

        print("patched active_orchestrator:", patched_planning_state.get("active_orchestrator"))
        print("patched design_state keys:", patched_design_state.keys())
        print("patched graph_data:", patched_design_state.get("graph_data"))

        return await run_design_chat(
            query="",
            session_state=patched_planning_state,
            image_path=image_path,
            image_base64=image_base64,
            image_media_type=image_media_type,
            append_user_message=False,
        )

    return result
