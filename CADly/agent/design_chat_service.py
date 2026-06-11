from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage

from design.orchestrator import build_design_orchestrator
from CADly.agent.session_utils import (
    EPHEMERAL_STATE_KEYS,
    build_persisted_fields,
    get_last_ai_text,
    merge_session_blob,
    persist_upload_image,
    read_svg_content,
    split_session_blob,
)

_design_app = build_design_orchestrator()

_HANDOFF_SUCCESS_TAIL = "이제 도면 생성, 수정, CAD 연동 작업을 진행할 수 있습니다."
_DESIGN_FAILURE_STATUSES = frozenset(
    {"validation_failed", "save_failed", "sampling_failed", "error"}
)


def _is_design_failure(status: str) -> bool:
    return status in _DESIGN_FAILURE_STATUSES


def _failure_detail(result: Dict[str, Any]) -> str:
    errors = result.get("validation_errors") or []
    if errors:
        return str(errors[0]).strip()
    return (result.get("message") or "").strip()


def _compose_handoff_failure_response(handoff_text: str, result: Dict[str, Any]) -> str:
    detail = _failure_detail(result)
    failure_block = "다만 도면 파일 생성에 실패했습니다."
    if detail:
        failure_block = f"{failure_block}\n{detail}"

    if _HANDOFF_SUCCESS_TAIL in handoff_text:
        prefix = handoff_text.split(_HANDOFF_SUCCESS_TAIL, 1)[0].rstrip()
        return f"{prefix}\n{failure_block}"

    return f"{handoff_text.rstrip()}\n\n{failure_block}"


def _build_design_response_text(result: Dict[str, Any]) -> str:
    status = result.get("status", "")
    message = (result.get("message") or "").strip()
    svg_path = result.get("svg_path")
    dxf_path = result.get("dxf_path")

    if status == "completed" and svg_path:
        lines = ["도면 생성이 완료되었습니다."]
        if svg_path:
            lines.append(f"SVG: {svg_path}")
        if dxf_path:
            lines.append(f"DXF: {dxf_path}")
        return "\n".join(lines)

    if _is_design_failure(status):
        detail = _failure_detail(result)
        if detail:
            return f"도면 생성에 실패했습니다.\n{detail}"
        return "도면 생성에 실패했습니다."

    if message:
        return message

    return "설계 파이프라인을 실행했습니다."


def _resolve_design_response_text(
    messages: List[Any],
    result: Dict[str, Any],
) -> str:
    status = result.get("status", "")

    if _is_design_failure(status):
        handoff_text = get_last_ai_text(messages)
        if handoff_text and "설계 단계로 넘어갑니다" in handoff_text:
            return _compose_handoff_failure_response(handoff_text, result)
        return _build_design_response_text(result)

    design_text = _build_design_response_text(result)
    if status == "completed" and result.get("svg_path"):
        return design_text

    return get_last_ai_text(messages) or design_text


async def run_design_chat(
    *,
    query: str = "",
    session_state: Optional[Dict[str, Any]] = None,
    image_path: Optional[str] = None,
    image_base64: Optional[str] = None,
    image_media_type: Optional[str] = None,
    append_user_message: bool = True,
) -> Dict[str, Any]:
    """Design 파이프라인 실행.

    HouseDiffusion 입력은 query가 아니라 design_state.graph_data(rooms/edges)입니다.
    query는 채팅 기록용이며, handoff 직후 자동 실행 시 append_user_message=False로 중복을 막습니다.
    """
    user_text = (query or "").strip()
    messages, _, design_state, planning_fields = split_session_blob(session_state)

    if not design_state.get("graph_data"):
        return {
            "response": "설계 데이터가 없습니다. 기획 단계에서 도면 생성을 먼저 확정해 주세요.",
            "search_results": [],
            "planning_state": session_state or {},
            "active_orchestrator": "planning",
            "route": "design",
            "agent_type": "design",
        }

    if append_user_message and user_text:
        messages = [*messages, HumanMessage(content=user_text)]

    resolved_image_path = image_path
    if image_base64 and not resolved_image_path:
        resolved_image_path = persist_upload_image(image_base64, image_media_type)

    invoke_state: Dict[str, Any] = {
        **design_state,
        "messages": messages,
        "user_input": user_text,
    }
    if resolved_image_path:
        invoke_state["image_path"] = resolved_image_path

    # 디버깅용
    print("\n========== DESIGN CHAT DEBUG ==========")
    print("design_state:", design_state)
    print("graph_data:", design_state.get("graph_data"))
    print("======================================\n")

    result = await _design_app.ainvoke(invoke_state)

    # 디버깅용
    print("\n========== DESIGN RESULT DEBUG ==========")
    print("status:", result.get("status"))
    print("message:", result.get("message"))
    print("svg_path:", result.get("svg_path"))
    print("dxf_path:", result.get("dxf_path"))
    print("errors:", result.get("validation_errors"))
    print("warnings:", result.get("verification_warnings"))
    print("========================================\n")

    persist_exclude = EPHEMERAL_STATE_KEYS | frozenset({"messages"})
    updated_design_state = build_persisted_fields(design_state, result, persist_exclude)

    result_messages = result.get("messages", [])
    if result_messages:
        messages = [*messages, *result_messages]

    response_text = _resolve_design_response_text(messages, result)
    if response_text and not any(isinstance(m, AIMessage) and m.content == response_text for m in messages):
        messages = [*messages, AIMessage(content=response_text)]

    planning_state = merge_session_blob(
        planning_fields,
        messages,
        "design",
        updated_design_state,
    )
    svg_content = read_svg_content(result.get("svg_path"))

    return {
        "response": response_text,
        "search_results": [],
        "references": [],
        "route": "design",
        "agent_type": "design",
        "planning_state": planning_state,
        "active_orchestrator": "design",
        "design_state": updated_design_state,
        "cad_svg_content": svg_content,
        "dxf_path": result.get("dxf_path"),
        "svg_path": result.get("svg_path"),
        "status": result.get("status"),
    }
