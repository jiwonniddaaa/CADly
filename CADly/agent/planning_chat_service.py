from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage

from planning.pending_state import migrate_pending_fields, reference_awaiting_from_pending
from planning.orchestrator import build_planning_orchestrator
from CADly.agent.session_utils import (
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
        "concept_keywords",
        "design_intent",
        "narrative",
        "concept_structured",
        "concept_updated_at",
    ):
        if key in concept_state:
            merged[key] = concept_state[key]

    if "pending_action" not in merged and concept_state.get("awaiting_concept_confirmation"):
        merged["pending_action"] = "concept_confirmation"

    return migrate_pending_fields(merged)


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
    route = result.get("route", "") or ""

    stored_references = result.get("references", [])
    if not isinstance(stored_references, list):
        stored_references = []
    
    previous_references = planning_fields.get("references", [])
    if not isinstance(previous_references, list):
        previous_references = []

    reference_routes = {
        "reference",
        "reference_agent",
        "search",
        "image_reference",
    }

    has_new_reference = stored_references != previous_references
    should_display_references = route in reference_routes and has_new_reference

    output_references = stored_references if should_display_references else []
    
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
        "search_results": output_references,
        "references": output_references,
        "display_references": should_display_references,
        "route": route,
        "agent_type": _resolve_agent_type(route, output_references),
        "planning_state": updated_planning_state,
        "concept_result": concept_value,
        "concept_keywords": result.get("concept_keywords", []),
        "design_intent": result.get("design_intent", ""),
        "narrative": result.get("narrative", ""),
        "concept_structured": result.get("concept_structured", {}),
        "concept_updated_at": result.get("concept_updated_at", ""),
        "pending_action": result.get("pending_action", "none"),
        "image_type": result.get("image_type"),
        "active_orchestrator": active_orchestrator,
        "design_state": design_state,
    }
