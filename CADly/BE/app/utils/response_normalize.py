from typing import Any, Dict, List, Tuple

ROUTE_LABELS = {
    "image_understanding": "이미지 분석",
    "reference_agent": "레퍼런스 검색",
    "site_agent": "대지 조사",
    "extract_requirements": "요구사항 정리",
    "planning_agent": "기획",
    "handoff_to_design": "설계 전환",
    "general_answer": "일반 답변",
    "design": "도면 생성",
    "agent": "에이전트",
}

_ORCHESTRATOR_LABELS = {
    "planning": "기획",
    "design": "설계",
}


def normalize_agent_metadata(
    agent_response: Dict[str, Any],
    references: List[Any],
) -> Tuple[str, str, str, str]:
    """route / agent_type / route_label / active_orchestrator 정규화."""
    route = (agent_response.get("route") or "").strip()

    agent_type = agent_response.get("agent_type")
    if not agent_type:
        if route:
            agent_type = route
        elif references:
            agent_type = "reference_agent"
        else:
            agent_type = "agent"

    label_key = route or agent_type
    route_label = ROUTE_LABELS.get(label_key, label_key or "에이전트")

    active_orchestrator = agent_response.get("active_orchestrator") or "planning"
    return route, agent_type, route_label, active_orchestrator


def build_debug_payload(agent_response: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "route": agent_response.get("route", ""),
        "intent": agent_response.get("intent", ""),
        "search_query": agent_response.get("search_query", ""),
        "input_mode": agent_response.get("input_mode", ""),
        "proceed_to_search": agent_response.get("proceed_to_search", False),
        "image_type": agent_response.get("image_type"),
        "active_orchestrator": agent_response.get("active_orchestrator"),
        "orchestrator_label": _ORCHESTRATOR_LABELS.get(
            agent_response.get("active_orchestrator") or "planning",
            agent_response.get("active_orchestrator") or "planning",
        ),
    }
