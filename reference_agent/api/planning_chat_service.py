from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage

from planning.orchestrator import build_planning_orchestrator
from reference_agent.api.session_utils import (
    EPHEMERAL_STATE_KEYS,
    build_persisted_fields,
    get_last_ai_text,
    merge_session_blob,
    persist_upload_image,
    split_session_blob,
)

_planning_app = build_planning_orchestrator()

_LEGACY_CONCEPT_TO_PLANNING = {
    "concept_result": "concept",
}


def _merge_legacy_concept_state(
    planning_state: Optional[Dict[str, Any]],
    concept_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = dict(planning_state or {})
    if not concept_state:
        return merged

    for legacy_key, planning_key in _LEGACY_CONCEPT_TO_PLANNING.items():
        if legacy_key in concept_state and planning_key not in merged:
            merged[planning_key] = concept_state[legacy_key]

    for key in (
        "awaiting_concept_confirmation",
        "concept_keywords",
        "design_intent",
        "narrative",
        "concept_structured",
        "concept_updated_at",
    ):
        if key in concept_state:
            merged[key] = concept_state[key]

    return merged


def _load_session_state(
    planning_state: Optional[Dict[str, Any]],
    concept_state: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List, str, Dict[str, Any]]:
    merged = _merge_legacy_concept_state(planning_state, concept_state)
    messages, active_orchestrator, design_state, planning_fields = split_session_blob(merged)
    return planning_fields, messages, active_orchestrator, design_state


def _resolve_agent_type(route: str, references: List[Any]) -> str:
    if route:
        return route
    if references:
        return "reference_agent"
    return "agent"


async def run_planning_chat(
    *,
    query: str,
    planning_state: Optional[Dict[str, Any]] = None,
    concept_state: Optional[Dict[str, Any]] = None,
    image_path: Optional[str] = None,
    image_base64: Optional[str] = None,
    image_media_type: Optional[str] = None,
) -> Dict[str, Any]:
    user_text = (query or "").strip()
    has_image = bool(image_path or image_base64)

    if not has_image and not user_text:
        return {
            "response": "검색할 텍스트 또는 이미지를 입력해 주세요.",
            "search_results": [],
            "planning_state": planning_state or {},
            "agent_type": "agent",
            "route": "",
            "active_orchestrator": "planning",
        }

    planning_fields, history_messages, prev_active, prev_design_state = _load_session_state(
        planning_state,
        concept_state,
    )
    messages = [*history_messages, HumanMessage(content=user_text)]

    resolved_image_path = image_path
    if image_base64 and not resolved_image_path:
        resolved_image_path = persist_upload_image(image_base64, image_media_type)

    invoke_state: Dict[str, Any] = {
        **planning_fields,
        "messages": messages,
        "user_input": user_text,
    }

    if resolved_image_path:
        invoke_state["image_path"] = resolved_image_path
    if image_base64:
        invoke_state["image_base64"] = image_base64
    if image_media_type:
        invoke_state["image_media_type"] = image_media_type

    result = await _planning_app.ainvoke(invoke_state)

    result_messages = result.get("messages", [])
    if result_messages:
        messages = [*messages, *result_messages]

    response_text = get_last_ai_text(messages) or "응답을 생성하지 못했습니다."
    references = result.get("references", [])
    if not isinstance(references, list):
        references = []

    route = result.get("route", "") or ""
    active_orchestrator = result.get("active_orchestrator", prev_active) or "planning"
    design_state = result.get("design_state") if active_orchestrator == "design" else prev_design_state
    if not isinstance(design_state, dict):
        design_state = {}

    updated_planning_fields = build_persisted_fields(planning_fields, result, EPHEMERAL_STATE_KEYS)
    updated_planning_state = merge_session_blob(
        updated_planning_fields,
        messages,
        active_orchestrator,
        design_state,
    )
    concept_value = result.get("concept", updated_planning_fields.get("concept", ""))

    return {
        "response": response_text,
        "search_results": references,
        "references": references,
        "route": route,
        "agent_type": _resolve_agent_type(route, references),
        "planning_state": updated_planning_state,
        "concept_result": concept_value,
        "concept_keywords": result.get("concept_keywords", []),
        "design_intent": result.get("design_intent", ""),
        "narrative": result.get("narrative", ""),
        "concept_structured": result.get("concept_structured", {}),
        "concept_updated_at": result.get("concept_updated_at", ""),
        "awaiting_concept_confirmation": result.get(
            "awaiting_concept_confirmation", False
        ),
        "image_type": result.get("image_type"),
        "active_orchestrator": active_orchestrator,
        "design_state": design_state,
    }
