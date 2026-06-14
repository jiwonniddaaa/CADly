# planning/supervisor.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from planning.pending_state import PendingAction, normalize_pending_action
from planning.planning_agent import has_recommendation_inputs
from planning.space_utils import indoor_spaces

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

WorkflowStage = Literal[
    "awaiting_concept_confirmation",
    "awaiting_area_decision",
    "awaiting_area_mode",
    "awaiting_manual_area",
    "awaiting_area_abnormal_confirm",
    "awaiting_design_confirm",
    "needs_site_analysis",
    "needs_requirements",
    "ready_for_planning_check",
    "idle",
]

_PENDING_FLOW_ROUTES: Dict[PendingAction, str] = {
    "manual_area_input": "extract_requirements",
    "area_decision": "planning_agent",
    "area_mode": "planning_agent",
    "area_abnormal_confirmation": "planning_agent",
    "concept_confirmation": "reference_agent",
}

_PENDING_LABELS: Dict[PendingAction, str] = {
    "none": "없음",
    "area_decision": "세부 공간 면적 설정 여부 확인 (네/아니오)",
    "area_mode": "면적 입력 방식 선택 (대지 분석 / 직접 입력 / 추천값)",
    "manual_area_input": "공간별 면적 직접 입력",
    "area_abnormal_confirmation": "비정상 입력 면적 확인 (네/아니오)",
    "concept_confirmation": "레퍼런스/컨셉 확인",
}

_PENDING_REMINDERS: Dict[PendingAction, str] = {
    "area_decision": (
        "\n\n—\n"
        "계속 진행하려면: 세부 공간 면적을 직접 설정할지 **네/아니오**로 답해 주세요."
    ),
    "area_mode": (
        "\n\n—\n"
        "계속 진행하려면: **대지 분석**, **직접 입력**, **추천값** 중 하나로 답해 주세요."
    ),
    "area_abnormal_confirmation": (
        "\n\n—\n"
        "계속 진행하려면: 입력하신 면적이 맞는지 **네/아니오**로 답해 주세요."
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

_WORKFLOW_GUIDANCE: Dict[WorkflowStage, str] = {
    "awaiting_concept_confirmation": (
        "현재 단계: **컨셉/레퍼런스 확인**. 방향을 확정하거나 수정 요청을 입력해 주세요."
    ),
    "awaiting_area_decision": (
        "현재 단계: **세부 면적 설정 여부 확인**. "
        "구체적인 면적을 설정할지 **네/아니오**로 답해 주세요."
    ),
    "awaiting_area_mode": (
        "현재 단계: **면적 입력 방식 선택**. "
        "**대지 분석**, **직접 입력**, **추천값** 중 하나로 답해 주세요."
    ),
    "awaiting_manual_area": (
        "현재 단계: **공간별 면적 입력**. "
        "예) 거실 24, 주방 12, 침실1 14"
    ),
    "awaiting_area_abnormal_confirm": (
        "현재 단계: **비정상 입력 면적 확인**. "
        "입력하신 면적이 맞으면 **네**, 수정하려면 **아니오**로 답해 주세요."
    ),
    "awaiting_design_confirm": (
        "현재 단계: **도면 생성 최종 확인**. "
        "조건을 검토한 뒤 생성을 원하시면 **네/생성해줘** 등으로 답해 주세요."
    ),
    "needs_site_analysis": (
        "현재 단계: **대지 분석 필요**. "
        "분석할 주소/지번을 입력해 주세요. (예: 역삼동 747)"
    ),
    "needs_requirements": (
        "현재 단계: **요구사항 정리 필요**. "
        "공간 구성, 파일명, 건물 유형(단독/공동) 등을 알려 주세요."
    ),
    "ready_for_planning_check": (
        "현재 단계: **기획 검증/면적 설정**. "
        "요구사항이 모이면 세부 면적 설정 또는 도면 생성 조건 확인으로 이어집니다."
    ),
    "idle": "",
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
- User asks to FIND/RECOMMEND a candidate site by conditions (region + area/coverage),
  e.g. "강동구 천호동에 건축면적 30평 되는 주소 있을까?", "역삼동에 50평짜리 땅 추천해줘".
- NOT for explaining already-stored site_analysis in session (use general_answer).
- NOT when the user references an example/case to imitate (use reference_agent).

3. extract_requirements
- User states or changes CONCRETE spatial requirements: specific rooms/counts, adjacency, file name, building type, target area.
- User gives manual area input (e.g. "거실 24, 주방 12").
- User corrects the plan with concrete requirement changes (e.g. "침실 하나 더 추가해줘").
- NOT for vague aspirational wishes without concrete rooms/specs (use general_answer).

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
- Vague aspirational design wishes WITHOUT concrete spatial specs
  (e.g. "부모님이 살만한 2층 주택이면 좋겠어"): acknowledge, then ask the user to clarify
  the direction (레퍼런스/스타일 탐색 / 공간 구성 정리 / 대지 분석).
- Casual chat, capabilities, greetings when no specialized agent is needed.

CRITICAL RULES (Supervisor behavior):
- pending_action does NOT force a route. Always interpret user intent first.
- If pending is set but user asks/reviews/complains/modifies plan without a clear flow answer → general_answer or extract_requirements, NOT planning_agent.
- If user asks about numbers/areas already in session (e.g. 251.92㎡) → general_answer.
- Prefer general_answer over site_agent when user asks about existing site_analysis results.
- Return ONLY JSON: {"route": "..."}
"""

_GENERAL_ANSWER_SYSTEM = """
You are CADly, an AI architectural planning and design assistant.

This turn is READ-ONLY Q&A. You must NOT claim to have executed agents, changed state, started/completed design generation, or updated the plan.

Answer using the provided session state and conversation when relevant.
Always respond in natural Korean.

SOURCE RULES (critical — never violate):
- site_analysis.diffusion_output / site_analysis_summary comes ONLY from site_agent (building registry / mart DB).
- hand sketch / sketch_result provides layout only (spaces, edges). It does NOT produce diffusion_output or generation area.
- Never say sketch analysis wrote diffusion_output or building_area_m2/private_area_m2.
- area_for_generation.value_m2 and its source_label in session JSON are authoritative for "도면 생성 기준 면적".
- floor_area_m2 (연면적) in site_analysis is informational; generation uses building_area_m2 or private_area_m2 per building_type.

EXECUTION PROHIBITION:
- Do not say you started, completed, or will run design generation, site analysis, or requirement extraction in this turn.
- Direct the user what to say/do next using workflow_stage and flow_guidance instead.

Guidelines:
- Explain workflow stage, pending steps, and area provenance clearly.
- Be concise. Use bullet lists when comparing values.
- For casual questions without session relevance, answer naturally as CADly.
- If the user expresses a vague design wish without concrete requirements
  (e.g. "부모님이 살만한 2층 주택이면 좋겠어"), do NOT invent or extract requirements.
  Briefly acknowledge, then ask which direction they want, offering concrete options:
  레퍼런스/스타일 탐색, 공간 구성(요구사항) 정리, 대지 분석.
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


def _last_user_text(state: Dict[str, Any]) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    content = messages[-1].content
    return content if isinstance(content, str) else str(content or "")


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
        return {
            "present": False,
            "source": "site_agent_building_registry",
            "source_label": "대지 분석 (건축대장/마트 DB)",
        }
    raw = site_analysis.get("raw_site_output") or {}
    diffusion = site_analysis.get("diffusion_output") or raw.get("diffusion_output") or {}
    identifiers = raw.get("building_identifiers") or {}
    return {
        "present": True,
        "source": "site_agent_building_registry",
        "source_label": "대지 분석 (건축대장/마트 DB)",
        "provides": [
            "diffusion_output",
            "building_area_m2",
            "private_area_m2",
            "floor_area_m2",
            "common_area_m2",
        ],
        "does_not_come_from": "hand_sketch",
        "diffusion_output": diffusion,
        "building_identifiers": identifiers,
        "site_area_m2": diffusion.get("site_area_m2"),
        "building_area_m2": diffusion.get("building_area_m2"),
        "floor_area_m2": diffusion.get("floor_area_m2"),
        "private_area_m2": diffusion.get("private_area_m2"),
        "common_area_m2": diffusion.get("common_area_m2"),
    }


def _summarize_sketch_result(sketch_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(sketch_result, dict) or not sketch_result.get("spaces"):
        return {
            "present": False,
            "source": "hand_sketch_extract",
            "source_label": "손도면 분석 (레이아웃 추출)",
        }
    return {
        "present": True,
        "source": "hand_sketch_extract",
        "source_label": "손도면 분석 (레이아웃 추출)",
        "provides": ["spaces", "edges", "output_name", "building_type"],
        "does_not_provide": [
            "diffusion_output",
            "generation_area_m2",
            "building_area_m2",
            "private_area_m2",
        ],
        "space_count": len(sketch_result.get("spaces") or []),
        "edge_count": len(sketch_result.get("edges") or []),
        "spaces": sketch_result.get("spaces"),
        "edges": sketch_result.get("edges"),
    }


def _derive_area_for_generation(state: Dict[str, Any]) -> Dict[str, Any]:
    building_type = state.get("building_type")
    payload = state.get("design_payload")
    if isinstance(payload, dict):
        gen_ctx = payload.get("generation_context") or {}
        value = gen_ctx.get("area_m2")
        if value is not None:
            field = (
                "private_area_m2"
                if building_type == "multi_family"
                else "building_area_m2"
            )
            return {
                "value_m2": value,
                "field": field,
                "source": "design_payload.generation_context",
                "source_label": "도면 생성 payload (확정)",
            }

    site = _summarize_site_analysis(state.get("site_analysis"))
    diffusion = site.get("diffusion_output") or {}
    if building_type == "multi_family":
        value = diffusion.get("private_area_m2")
        field = "private_area_m2"
        label = "대지 분석 — 전용면적 (건축대장)"
    elif building_type == "single_family":
        value = diffusion.get("building_area_m2")
        field = "building_area_m2"
        label = "대지 분석 — 건축면적 (건축대장)"
    else:
        return {
            "value_m2": None,
            "field": None,
            "source": None,
            "source_label": None,
            "note": "building_type 미설정 시 생성 기준 면적을 특정할 수 없습니다.",
        }

    if value is None:
        return {
            "value_m2": None,
            "field": field,
            "source": "site_analysis.diffusion_output",
            "source_label": label,
            "note": "대지 분석 후 planning 검증을 거쳐 payload에 반영됩니다.",
        }

    return {
        "value_m2": value,
        "field": field,
        "source": "site_analysis.diffusion_output",
        "source_label": label,
        "note": "연면적(floor_area_m2)이 아닌 위 필드가 도면 생성 기준으로 사용됩니다.",
    }


def derive_workflow_stage(state: Dict[str, Any]) -> WorkflowStage:
    """state에 저장하지 않고 매 턴 파생 계산."""
    pending = normalize_pending_action(state)
    if pending == "concept_confirmation":
        return "awaiting_concept_confirmation"
    if pending == "area_decision":
        return "awaiting_area_decision"
    if pending == "area_mode":
        return "awaiting_area_mode"
    if pending == "manual_area_input":
        return "awaiting_manual_area"
    if pending == "area_abnormal_confirmation":
        return "awaiting_area_abnormal_confirm"

    if state.get("design_payload") is not None or is_awaiting_design_handoff_confirmation(state):
        return "awaiting_design_confirm"

    spaces = state.get("spaces") or []
    if not spaces:
        return "needs_requirements"
    if not state.get("output_name") or not state.get("building_type"):
        return "needs_requirements"
    if not state.get("site_analysis"):
        return "needs_site_analysis"

    return "ready_for_planning_check"


def flow_guidance(state: Dict[str, Any]) -> str:
    stage = derive_workflow_stage(state)
    return _WORKFLOW_GUIDANCE.get(stage, "")


def _last_assistant_excerpt(messages: List[BaseMessage], limit: int = 400) -> str:
    for message in reversed(messages or []):
        if message.type not in ("ai", "assistant"):
            continue
        text = message.content if isinstance(message.content, str) else str(message.content or "")
        if text.strip():
            return text.strip()[:limit]
    return ""


def _compact_spaces_summary(spaces: List[Any]) -> Dict[str, Any]:
    return {
        "count": len(spaces),
        "room_types": [s.get("room_type") for s in spaces if isinstance(s, dict) and s.get("room_type")],
        "ids": [s.get("id") for s in spaces if isinstance(s, dict) and s.get("id")],
    }


def build_supervisor_context(state: Dict[str, Any]) -> str:
    """Supervisor 라우팅용 경량 context (spaces/edges 본문·raw site 제외)."""
    site = _summarize_site_analysis(state.get("site_analysis"))
    sketch = state.get("sketch_result")
    pending = normalize_pending_action(state)
    stage = derive_workflow_stage(state)
    area = _derive_area_for_generation(state)
    payload = state.get("design_payload")

    site_key_values = None
    if site.get("present"):
        site_key_values = {
            key: site[key]
            for key in ("building_area_m2", "private_area_m2", "floor_area_m2", "site_area_m2")
            if site.get(key) is not None
        }

    context = {
        "workflow_stage": stage,
        "pending_action": pending,
        "has_design_payload": payload is not None,
        "building_type": state.get("building_type"),
        "output_name": state.get("output_name"),
        "spaces_summary": _compact_spaces_summary(state.get("spaces") or []),
        "edge_count": len(state.get("edges") or []),
        "has_site_analysis": site.get("present", False),
        "site_area_key_values": site_key_values,
        "has_sketch_result": bool(isinstance(sketch, dict) and sketch.get("spaces")),
        "area_for_generation": {
            "value_m2": area.get("value_m2"),
            "source_label": area.get("source_label"),
        },
        "ready_for_design": state.get("ready_for_design"),
        "missing_requirements_count": len(state.get("missing_requirements") or []),
    }
    return json.dumps(context, ensure_ascii=False, indent=2)


def build_session_context(state: Dict[str, Any]) -> str:
    pending = normalize_pending_action(state)
    payload_summary = _summarize_design_payload(state.get("design_payload"))
    area_reco = state.get("area_recommendation_result") or {}
    stage = derive_workflow_stage(state)

    context = {
        "workflow_stage": stage,
        "workflow_stage_label": _WORKFLOW_GUIDANCE.get(stage, ""),
        "flow_guidance": flow_guidance(state),
        "pending_action": pending,
        "pending_label": _PENDING_LABELS.get(pending, pending),
        "pending_flow_route_if_continue": _PENDING_FLOW_ROUTES.get(pending),
        "concept": state.get("concept"),
        "spaces": indoor_spaces(state.get("spaces", [])),
        "edges": state.get("edges", []),
        "output_name": state.get("output_name"),
        "building_type": state.get("building_type"),
        "missing_requirements": state.get("missing_requirements", []),
        "ready_for_design": state.get("ready_for_design"),
        "has_design_payload": state.get("design_payload") is not None,
        "design_payload_summary": payload_summary,
        "site_analysis_summary": _summarize_site_analysis(state.get("site_analysis")),
        "sketch_result_summary": _summarize_sketch_result(state.get("sketch_result")),
        "area_for_generation": _derive_area_for_generation(state),
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

_FLOW_REVIEW_MARKERS = (
    "왜",
    "이상",
    "말고",
    "다시",
    "?",
    "몰라",
    "확인해",
    "설명",
    "어디서",
    "출처",
    "기준",
)

_CONCEPT_MODIFY_MARKERS = (
    "바꿔",
    "수정",
    "다른",
    "말고",
    "대신",
    "다시",
    "말해",
    "보여",
)

_CONCEPT_CONFIRM_TOKENS = (
    "확인",
    "좋아",
    "진행",
    "그래",
    "맞아",
    "ok",
    "승인",
)

_AREA_INPUT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²|평)?|"
    r"(거실|주방|부엌|침실|화장실|욕실|현관|발코니|베란다|다이닝|서재|창고)",
    re.IGNORECASE,
)

_ADDRESS_LOT_PATTERN = re.compile(
    r"[가-힣0-9]{1,20}(?:동|가)\s*산?\s*\d{1,5}(?:\s*[-~]\s*\d{1,5})?\s*(?:번지)?"
)

_ADDRESS_ADMIN_PATTERN = re.compile(
    r"[가-힣]+(?:시|군|구)\s+[가-힣0-9]{1,20}(?:동|가)\s*산?\s*\d"
)

_BUNJI_PATTERN = re.compile(r"\d{1,5}(?:-\d{1,5})?\s*번지")

_REFERENCE_INTENT_MARKERS = (
    "레퍼런스",
    "reference",
    "사례",
    "예시",
    "유사사례",
    "건축사례",
    "케이스",
    "casestudy",
    "case study",
    "무드",
    "mood",
    "핀터레스트",
    "pinterest",
    "Archdaily",
    "스타일",
    "style",
    "컨셉",
    "concept",
    "느낌",
    "이미지",
    "image",
    "사진",
)

_STATUS_QUERY_MARKERS = (
    "뭐 하는",
    "뭐하는",
    "지금 단계",
    "현재 단계",
    "어디까지",
    "진행 상황",
    "진행상황",
    "뭐 해야",
    "뭐해야",
    "다음 단계",
    "무슨 단계",
    "지금 뭐",
    "현재 뭐",
)

_SOURCE_QUERY_MARKERS = (
    "출처",
    "기준 면적",
    "기준면적",
    "생성 기준",
    "생성기준",
    "어디서",
    "기준이",
    "면적이 왜",
)


def _normalize_user_text(text: str) -> str:
    return (text or "").strip().lower().replace(" ", "")


def _is_flow_review_message(user_text: str) -> bool:
    raw = (user_text or "").strip()
    if not raw:
        return False
    return any(marker in raw for marker in _FLOW_REVIEW_MARKERS)


def _parse_yes_no(user_text: str) -> Optional[Literal["yes", "no"]]:
    normalized = (user_text or "").lower()
    yes_tokens = ["네", "예", "응", "ㅇㅇ", "yes", "y"]
    no_tokens = ["아니", "아니오", "no", "n", "괜찮", "필요없"]
    if any(token in normalized for token in [t.lower() for t in yes_tokens]):
        return "yes"
    if any(token in normalized for token in [t.lower() for t in no_tokens]):
        return "no"
    return None


def _parse_area_mode(
    user_text: str,
    *,
    limited_site: bool = False,
) -> Optional[Literal["manual", "recommend", "site_analysis"]]:
    normalized = (user_text or "").lower().replace(" ", "")
    site_tokens = ["대지분석", "대지조사", "siteanalysis", "siteagent"]
    manual_tokens = ["직접입력", "수동입력", "직접", "manual"]
    recommend_tokens = ["추천값", "추천", "기본값", "recommend"]

    if limited_site:
        if normalized == "1":
            return "site_analysis"
        if normalized == "2":
            return "manual"
        if normalized == "3":
            return "recommend"
    else:
        if normalized == "1":
            return "manual"
        if normalized == "2":
            return "recommend"

    if any(token in normalized for token in site_tokens) or normalized == "대지":
        return "site_analysis"
    if any(token in normalized for token in manual_tokens):
        return "manual"
    if any(token in normalized for token in recommend_tokens):
        return "recommend"
    return None


def _looks_like_manual_area_input(user_text: str) -> bool:
    raw = (user_text or "").strip()
    if not raw or _is_flow_review_message(raw):
        return False
    if _contains_address_pattern(raw):
        return False
    if not _AREA_INPUT_PATTERN.search(raw):
        return False
    return bool(re.search(r"\d", raw))


def _is_clear_concept_flow_reply(user_text: str) -> bool:
    """컨셉 확인 pending: 명시적 승인만 pre-check. 수정/탐색 요청은 Supervisor에 맡김."""
    raw = (user_text or "").strip()
    if not raw or _is_flow_review_message(raw):
        return False
    if any(marker in raw for marker in _CONCEPT_MODIFY_MARKERS):
        return False

    normalized = _normalize_user_text(raw)
    if _parse_yes_no(user_text) is not None:
        return True
    return any(token in normalized for token in _CONCEPT_CONFIRM_TOKENS)


def _contains_address_pattern(user_text: str) -> bool:
    raw = (user_text or "").strip()
    if not raw:
        return False
    return bool(
        _ADDRESS_LOT_PATTERN.search(raw)
        or _ADDRESS_ADMIN_PATTERN.search(raw)
        or _BUNJI_PATTERN.search(raw)
    )


def _has_reference_or_case_intent(user_text: str) -> bool:
    """주소가 있어도 레퍼런스/사례 탐색이면 site_agent pre-check 제외."""
    raw = (user_text or "").strip()
    if not raw:
        return False
    normalized = _normalize_user_text(raw)
    if any(marker.lower().replace(" ", "") in normalized for marker in _REFERENCE_INTENT_MARKERS):
        return True
    if "비슷한" in raw and any(token in raw for token in ("찾", "보", "검색", "레퍼", "사례", "예시")):
        return True
    return False


def _looks_like_site_address_input(user_text: str) -> bool:
    """신규 대지 분석 요청으로 보이는 주소/지번 입력."""
    raw = (user_text or "").strip()
    if not raw or len(raw) < 4:
        return False
    if _is_flow_review_message(raw):
        return False
    if _has_reference_or_case_intent(raw):
        return False
    if not _contains_address_pattern(raw):
        return False
    return True


# 조건(면적/지역)으로 "대지·주소를 찾아 달라"는 후보 탐색형 표현.
# 이런 자연어는 검색/요구/레퍼런스 의도가 섞이므로 deterministic 라우팅 대신
# Supervisor(또는 site_agent 내부 clarification)에 위임한다.
_SITE_CANDIDATE_MARKERS = (
    "있을까",
    "있나",
    "있어",
    "있는",
    "추천",
    "골라",
    "구해",
    "찾아",
)


def _looks_like_short_address_query(user_text: str) -> bool:
    """'짧은 주소/지번 단독 입력'만 site_agent로 deterministic 라우팅.

    조건으로 후보 대지를 찾아 달라는 자연어(예: "강동구 천호동에 30평 되는 주소 있을까?")는
    여기서 제외하고 Supervisor가 판단하도록 둔다.
    """
    raw = (user_text or "").strip()
    if not _looks_like_site_address_input(raw):
        return False
    if any(marker in raw for marker in _SITE_CANDIDATE_MARKERS):
        return False
    # 너무 길면 복합 의도로 보고 Supervisor에 위임 (짧은 단독 입력 위주)
    if len(raw) > 40:
        return False
    return True


def _is_status_or_source_query(user_text: str) -> bool:
    raw = (user_text or "").strip()
    if not raw:
        return False
    normalized = raw.replace(" ", "")
    if any(marker.replace(" ", "") in normalized for marker in _STATUS_QUERY_MARKERS):
        return True
    if any(marker.replace(" ", "") in normalized for marker in _SOURCE_QUERY_MARKERS):
        return True
    if "면적" in raw and any(marker in raw for marker in ("왜", "출처", "기준", "어디서")):
        return True
    if ("손도면" in raw or "스케치" in raw) and any(
        marker in raw for marker in ("면적", "출처", "기준", "생성")
    ):
        return True
    return False


def _format_area_source_section(state: Dict[str, Any]) -> str:
    lines: List[str] = []
    area_info = _derive_area_for_generation(state)
    site = _summarize_site_analysis(state.get("site_analysis"))
    sketch = _summarize_sketch_result(state.get("sketch_result"))

    lines.append("**도면 생성 기준 면적**")
    if area_info.get("value_m2") is not None:
        lines.append(f"- 값: **{area_info['value_m2']}㎡**")
        label = area_info.get("source_label") or area_info.get("source") or "세션 기준"
        lines.append(f"- 출처: {label}")
        note = area_info.get("note")
        if note:
            lines.append(f"- 참고: {note}")
    else:
        note = area_info.get("note") or "아직 확정되지 않았습니다."
        lines.append(f"- {note}")

    if site.get("present"):
        lines.append("")
        lines.append("**대지 분석 (건축대장/마트 DB)** — site_agent 결과")
        for key, label in (
            ("building_area_m2", "건축면적"),
            ("private_area_m2", "전용면적"),
            ("floor_area_m2", "연면적(참고)"),
        ):
            if site.get(key) is not None:
                lines.append(f"- {label}: {site[key]}㎡")

    if sketch.get("present"):
        lines.append("")
        lines.append("**손도면 분석** — 레이아웃(공간·연결)만 제공")
        lines.append("- 손도면은 diffusion_output·생성 기준 면적을 만들지 **않습니다**.")
        lines.append(
            f"- 인식 공간: {sketch.get('space_count', 0)}개, "
            f"연결: {sketch.get('edge_count', 0)}개"
        )
    elif state.get("sketch_result") or state.get("image_type") == "hand_sketch":
        lines.append("")
        lines.append("**손도면** — 공간 배치만 추출하며, 생성 기준 면적 출처가 **아닙니다**.")

    return "\n".join(lines)


def try_template_status_answer(state: Dict[str, Any]) -> Optional[str]:
    """단순 상태/출처/단계 질문 → LLM 없이 템플릿 응답."""
    user_text = _last_user_text(state).strip()
    if not user_text or not _is_status_or_source_query(user_text):
        return None
    if _looks_like_site_address_input(user_text):
        return None
    if _looks_like_manual_area_input(user_text):
        return None

    parts: List[str] = []
    guidance = flow_guidance(state)
    if guidance:
        parts.append(guidance)

    normalized = user_text.replace(" ", "")
    is_status = any(marker.replace(" ", "") in normalized for marker in _STATUS_QUERY_MARKERS)
    is_source = any(
        marker.replace(" ", "") in normalized for marker in _SOURCE_QUERY_MARKERS
    ) or ("면적" in user_text and any(m in user_text for m in ("왜", "출처", "기준", "어디서")))
    is_sketch = ("손도면" in user_text or "스케치" in user_text) and any(
        m in user_text for m in ("면적", "출처", "기준", "생성")
    )

    if is_status:
        pending = normalize_pending_action(state)
        if pending != "none":
            parts.append(f"\n**대기 중인 입력**: {_PENDING_LABELS.get(pending, pending)}")
        reminder = pending_reminder(state).strip()
        if reminder:
            parts.append(reminder)

    if is_source or is_sketch or "출처" in user_text or "기준" in user_text:
        parts.append("")
        parts.append(_format_area_source_section(state))

    answer = "\n".join(part for part in parts if part).strip()
    return answer or None


def try_site_agent_precheck(state: Dict[str, Any]) -> Optional[str]:
    """짧은 주소/지번 단독 입력만 → LLM 없이 site_agent.

    조건 기반 후보 탐색형 자연어는 Supervisor가 판단한다.
    """
    user_text = _last_user_text(state)
    if not user_text.strip():
        return None
    if _looks_like_short_address_query(user_text):
        return "site_agent"
    return None


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

    if _is_flow_review_message(raw):
        return False

    if any(token in normalized for token in _HANDOFF_CONFIRM_TOKENS):
        return True

    return len(normalized) <= 4 and normalized in {"네", "예", "응", "ok", "y"}


def try_handoff_to_design_precheck(state: Dict[str, Any]) -> Optional[str]:
    """design_payload + 최종 확인 문맥 + 명확한 승인 → LLM 없이 handoff."""
    messages = state.get("messages") or []
    if not messages:
        return None

    user_text = _last_user_text(state)
    if not is_awaiting_design_handoff_confirmation(state):
        return None
    if not is_clear_handoff_confirmation(user_text):
        return None
    return "handoff_to_design"


def try_pending_flow_precheck(state: Dict[str, Any]) -> Optional[str]:
    """pending + 명확한 flow 답변만 deterministic 라우팅. 질문/검토는 Supervisor에 맡김."""
    pending = normalize_pending_action(state)
    if pending == "none":
        return None

    user_text = _last_user_text(state)
    if not user_text.strip():
        return None

    # manual_area_input 루프 중에도 '추천값' 전환은 허용 (직접 입력 루프 탈출).
    # "다시/말고" 등 review 마커가 섞여도 추천 전환은 planning_agent가 처리.
    # 단, 질문/출처 문의("추천값 출처가 뭐야?")는 전환이 아니라 설명 요청이므로 제외.
    if (
        pending == "manual_area_input"
        and _parse_area_mode(user_text) == "recommend"
        and not _has_reference_or_case_intent(user_text)
        and not _is_status_or_source_query(user_text)
        and "?" not in user_text
    ):
        return "planning_agent"

    if _is_flow_review_message(user_text):
        return None

    if pending == "area_decision" and _parse_yes_no(user_text) is not None:
        return "planning_agent"
    if pending == "area_abnormal_confirmation" and _parse_yes_no(user_text) is not None:
        return "planning_agent"
    if pending == "area_mode" and _parse_area_mode(
        user_text,
        limited_site=not has_recommendation_inputs(state),
    ) is not None:
        return "planning_agent"
    if pending == "manual_area_input" and _looks_like_manual_area_input(user_text):
        return "extract_requirements"
    if pending == "concept_confirmation" and _is_clear_concept_flow_reply(user_text):
        return "reference_agent"

    return None


def resolve_entry_route(
    state: Dict[str, Any],
    llm: BaseChatModel,
) -> str:
    """deterministic pre-check 후 Supervisor LLM으로 진입 route 결정."""
    for precheck in (
        try_handoff_to_design_precheck,
        try_pending_flow_precheck,
        try_site_agent_precheck,
    ):
        route = precheck(state)
        if route:
            return route
    return resolve_supervisor_route(state, llm)


def resolve_supervisor_route(
    state: Dict[str, Any],
    llm: BaseChatModel,
) -> str:
    """Supervisor: 세션 상태 + pending + 사용자 의도를 보고 route 결정."""
    messages = state.get("messages") or []
    conversation = _messages_to_text(messages[-10:])
    session_context = build_supervisor_context(state)
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
- workflow_stage = {derive_workflow_stage(state)!r}
- if user continues pending flow only, typical route = {flow_route!r}

Few-shot:
- pending area_decision + "네" -> planning_agent
- pending area_decision + "25평으로 해달라고 했는데 251.92가 나왔어" -> general_answer
- pending area_decision + "251.92 말고 25평 기준으로" -> extract_requirements
- no pending + "왜 생성 기준 면적이 251.92야" -> general_answer
- no pending + "역삼동 747 건폐율 조회해줘" -> site_agent
- no pending + "강동구 천호동에 건축면적 30평 되는 주소 있을까?" -> site_agent
- no pending + "부모님이 살만한 2층 주택이면 좋겠어" -> general_answer (vague wish, ask clarifying intent)
- no pending + "다음에 침실 하나 더 추가해줘" -> extract_requirements
- no pending + "천호동 28-29 같은 주택 사례 찾아줘" -> reference_agent
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


def general_answer_system_prompt() -> str:
    return _GENERAL_ANSWER_SYSTEM
