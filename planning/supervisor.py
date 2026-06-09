from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from planning.pending_state import PendingAction, normalize_pending_action

VALID_SUPERVISOR_ROUTES = frozenset(
    {
        "reference_agent",
        "site_agent",
        "extract_requirements",
        "planning_agent",
        "handoff_to_design",
        "general_answer",
    }
)

_PENDING_FLOW_ROUTES: Dict[PendingAction, str] = {
    "manual_area_input": "extract_requirements",
    "area_decision": "planning_agent",
    "area_mode": "planning_agent",
    "concept_confirmation": "reference_agent",
}

_PENDING_LABELS: Dict[PendingAction, str] = {
    "none": "없음",
    "area_decision": "세부 공간 면적 설정 여부 확인 (네/아니오)",
    "area_mode": "면적 입력 방식 선택 (직접 입력 / 추천값)",
    "manual_area_input": "공간별 면적 직접 입력",
    "concept_confirmation": "레퍼런스/컨셉 확인",
}

_PENDING_REMINDERS: Dict[PendingAction, str] = {
    "area_decision": (
        "\n\n—\n"
        "계속 진행하려면: 세부 공간 면적을 직접 설정할지 **네/아니오**로 답해 주세요."
    ),
    "area_mode": (
        "\n\n—\n"
        "계속 진행하려면: **직접 입력** 또는 **추천값** 중 하나로 답해 주세요."
    ),
    "manual_area_input": (
        "\n\n—\n"
        "계속 진행하려면: 공간별 면적을 입력해 주세요. "
        "예) 거실 24, 주방 12, 침실1 14"
    ),
    "concept_confirmation": (
        "\n\n—\n"
        "계속 진행하려면: 컨셉/레퍼런스 방향을 확인하거나 수정 요청을 입력해 주세요."
    ),
}

_SUPERVISOR_SYSTEM = """
You are the CADly planning supervisor.

Your job: read the conversation, session state, and pending workflow — then choose exactly ONE route.
You must understand intent even when the user does NOT use question marks or wh-words.

Routes:

1. reference_agent
- User wants references, styles, examples, or concept development/search.

2. site_agent
- User wants NEW site analysis for an address/location, or legal/zoning lookup on a site.
- NOT for explaining already-stored site_analysis in session (use general_answer).

3. extract_requirements
- User states or changes spatial requirements: rooms, adjacency, file name, building type, target area.
- User gives manual area input (e.g. "거실 24, 주방 12").
- User corrects the plan with concrete requirement changes.

4. planning_agent
- User clearly continues a pending workflow step with a short flow answer:
  yes/no, direct input vs recommend, concept confirmation.
- ONLY when pending_action is set AND the message is clearly a flow continuation.

5. handoff_to_design
- has_design_payload is true, assistant asked final generation confirmation, user clearly confirms.

6. general_answer
- Q&A, review, explanation, complaint, status check about CURRENT session/plan/state.
- Includes non-question phrasing: "25평으로 해달라고 했는데", "251.92 말고", "지금 뭐 하는 중인지 모르겠어",
  "생성 기준 면적 다시 확인해줘", "이상한데", "왜 그렇게 잡혔는지 모르겠어".
- Casual chat, capabilities, greetings when no specialized agent is needed.

CRITICAL RULES (Supervisor behavior):
- pending_action does NOT force a route. Always interpret user intent first.
- If pending is set but user asks/reviews/complains/modifies plan without a clear flow answer → general_answer or extract_requirements, NOT planning_agent.
- If user asks about numbers/areas already in session (e.g. 251.92㎡) → general_answer.
- Prefer general_answer over site_agent when user asks about existing site_analysis results.
- Return ONLY JSON: {"route": "..."}
"""


def _safe_json_loads(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])
        raise ValueError(f"JSON parsing failed: {text}")


def _messages_to_text(messages: List[BaseMessage]) -> str:
    lines = []
    for msg in messages:
        lines.append(f"{msg.type}: {msg.content}")
    return "\n".join(lines)


def _summarize_design_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    gen_ctx = payload.get("generation_context") or {}
    reqs = payload.get("design_requirements") or {}
    return {
        "area_m2_for_generation": gen_ctx.get("area_m2"),
        "per_space_areas": gen_ctx.get("area"),
        "spaces": reqs.get("spaces"),
        "edges": reqs.get("edges"),
    }


def _summarize_site_analysis(site_analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(site_analysis, dict):
        return {}
    raw = site_analysis.get("raw_site_output") or {}
    diffusion = site_analysis.get("diffusion_output") or raw.get("diffusion_output") or {}
    identifiers = raw.get("building_identifiers") or {}
    return {
        "diffusion_output": diffusion,
        "building_identifiers": identifiers,
        "site_area_m2": diffusion.get("site_area_m2"),
        "building_area_m2": diffusion.get("building_area_m2"),
        "private_area_m2": diffusion.get("private_area_m2"),
    }


def _last_assistant_excerpt(messages: List[BaseMessage], limit: int = 400) -> str:
    for message in reversed(messages or []):
        if message.type not in ("ai", "assistant"):
            continue
        text = message.content if isinstance(message.content, str) else str(message.content or "")
        if text.strip():
            return text.strip()[:limit]
    return ""


def build_session_context(state: Dict[str, Any]) -> str:
    pending = normalize_pending_action(state)
    payload_summary = _summarize_design_payload(state.get("design_payload"))
    area_reco = state.get("area_recommendation_result") or {}

    context = {
        "pending_action": pending,
        "pending_label": _PENDING_LABELS.get(pending, pending),
        "pending_flow_route_if_continue": _PENDING_FLOW_ROUTES.get(pending),
        "concept": state.get("concept"),
        "spaces": state.get("spaces", []),
        "edges": state.get("edges", []),
        "output_name": state.get("output_name"),
        "building_type": state.get("building_type"),
        "missing_requirements": state.get("missing_requirements", []),
        "ready_for_design": state.get("ready_for_design"),
        "has_design_payload": state.get("design_payload") is not None,
        "design_payload_summary": payload_summary,
        "site_analysis_summary": _summarize_site_analysis(state.get("site_analysis")),
        "area_recommendation_status": area_reco.get("status"),
        "area_recommendation_total_m2": area_reco.get("total_area_m2"),
        "area_recommendation_source": area_reco.get("area_source"),
        "last_assistant_message": _last_assistant_excerpt(state.get("messages", [])),
    }
    return json.dumps(context, ensure_ascii=False, indent=2)


def pending_reminder(state: Dict[str, Any]) -> str:
    pending = normalize_pending_action(state)
    return _PENDING_REMINDERS.get(pending, "")


_DESIGN_CONFIRMATION_MARKERS = (
    "도면 생성을 시작해도 될까요",
    "이 조건으로 도면 생성",
)

_HANDOFF_DENIAL_TOKENS = ("아니", "아니오", "취소", "no", "하지마", "말고", "되지")

_HANDOFF_CONFIRM_TOKENS = (
    "네",
    "예",
    "응",
    "yes",
    "y",
    "ok",
    "확인",
    "생성",
    "만들어",
    "진행",
    "그래",
    "좋아",
    "ㅇㅇ",
    "시작",
)


def _normalize_user_text(text: str) -> str:
    return (text or "").strip().lower().replace(" ", "")


def is_awaiting_design_handoff_confirmation(state: Dict[str, Any]) -> bool:
    if not state.get("design_payload"):
        return False
    excerpt = _last_assistant_excerpt(state.get("messages", []))
    return any(marker in excerpt for marker in _DESIGN_CONFIRMATION_MARKERS)


def is_clear_handoff_confirmation(user_text: str) -> bool:
    raw = (user_text or "").strip()
    if not raw:
        return False

    normalized = _normalize_user_text(raw)
    if any(token in normalized for token in _HANDOFF_DENIAL_TOKENS):
        return False

    review_markers = ("왜", "이상", "말고", "다시", "?", "몰라", "확인해", "설명")
    if len(raw) > 20 and any(marker in raw for marker in review_markers):
        return False

    if any(token in normalized for token in _HANDOFF_CONFIRM_TOKENS):
        return True

    return len(normalized) <= 4 and normalized in {"네", "예", "응", "ok", "y"}


def try_handoff_to_design_precheck(state: Dict[str, Any]) -> Optional[str]:
    """design_payload + 최종 확인 문맥 + 명확한 승인 → LLM 없이 handoff."""
    messages = state.get("messages") or []
    if not messages:
        return None

    user_text = messages[-1].content
    if not isinstance(user_text, str):
        user_text = str(user_text or "")

    if not is_awaiting_design_handoff_confirmation(state):
        return None
    if not is_clear_handoff_confirmation(user_text):
        return None
    return "handoff_to_design"


def resolve_entry_route(
    state: Dict[str, Any],
    llm: BaseChatModel,
) -> str:
    """deterministic pre-check 후 Supervisor LLM으로 진입 route 결정."""
    precheck_route = try_handoff_to_design_precheck(state)
    if precheck_route:
        return precheck_route
    return resolve_supervisor_route(state, llm)


def resolve_supervisor_route(
    state: Dict[str, Any],
    llm: BaseChatModel,
) -> str:
    """Supervisor: 세션 상태 + pending + 사용자 의도를 보고 route 결정."""
    messages = state.get("messages") or []
    conversation = _messages_to_text(messages[-10:])
    session_context = build_session_context(state)
    pending = normalize_pending_action(state)
    flow_route = _PENDING_FLOW_ROUTES.get(pending)

    user_prompt = f"""
Conversation (recent):
{conversation}

Session state (JSON):
{session_context}

Latest user message:
{messages[-1].content if messages else ""}

Hints:
- has_design_payload = {state.get("design_payload") is not None}
- pending_action = {pending!r}
- if user continues pending flow only, typical route = {flow_route!r}

Few-shot:
- pending area_decision + "네" -> planning_agent
- pending area_decision + "25평으로 해달라고 했는데 251.92가 나왔어" -> general_answer
- pending area_decision + "251.92 말고 25평 기준으로" -> extract_requirements
- no pending + "왜 생성 기준 면적이 251.92야" -> general_answer
- no pending + "역삼동 747 건폐율 조회해줘" -> site_agent
- has payload + user confirms generation -> handoff_to_design
"""

    response = llm.invoke(
        [
            SystemMessage(content=_SUPERVISOR_SYSTEM),
            HumanMessage(content=user_prompt),
        ]
    )

    try:
        parsed = _safe_json_loads(response.content)
    except ValueError:
        return "general_answer"

    route = (parsed.get("route") or "general_answer").strip()
    if route not in VALID_SUPERVISOR_ROUTES:
        return "general_answer"
    return route
