from __future__ import annotations

import json
from typing import TypedDict, Optional, Literal, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from pathlib import Path
from reference_agent.agents.reference_agent import ReferenceAgent
from site_agent.site_agent import SiteAgent
from site_agent.site_analyzer import SiteAnalyzer
from site_agent.config import PublicDataConfig
from site_agent.public_data_client import PublicDataClient
from verification_agent import VerificationAgent
from generator.orchestrator import build_design_orchestrator
from planner.area_recommender import recommend_area_plan
from langchain_anthropic import ChatAnthropic

# 기본 초기화
high_llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929", 
)
low_llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

dataset_path = PROJECT_ROOT / "data" / "mart_djy_03_clean.csv"
db_path = PROJECT_ROOT / "data" / "mart_building_data.db"

reference_agent = ReferenceAgent()

config = PublicDataConfig()
public_client = PublicDataClient(config)
site_analyzer = SiteAnalyzer(
    public_client=public_client,
    dataset_path=str(dataset_path),
    db_path=str(db_path),
)
site_agent = SiteAgent(analyzer=site_analyzer)

verification_agent = VerificationAgent()

# State 정의
class SpaceRequirement(TypedDict, total=False):
    id: str
    room_type: str
    area: Optional[float]
    notes: Optional[str]

class PlanningState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]

    route: Literal[
        "reference_agent",
        "site_agent",
        "extract_requirements",
        # 예린 - 면적 추천 관련 노드 추가 
        "ask_area_recommendation",
        "area_recommendation",
        "area_recommendation_declined",

        "handoff_to_design",
        "general_answer",
    ]

    # planning context
    concept: Optional[str]
    references: Optional[List[Dict[str, Any]]]
    site_analysis: Optional[Dict[str, Any]]

    # design requirements
    spaces: List[SpaceRequirement]
    edges: List[List[str]]
    building_type: Optional[str]
    output_name: Optional[str]

    # checker results
    missing_requirements: List[str]
    ready_for_design: bool
    design_confirmation: bool

    # final handoff payload
    design_payload: Optional[Dict[str, Any]]

    # design orchestrator result
    design_result: Optional[Dict[str, Any]]


    # 예린 - area recommendation state 추가
    area_recommendation_pending: bool
    area_recommendation_opt_in: Optional[bool]
    area_recommendation_result: Optional[Dict[str, Any]]


# 유틸리티 함수
def messages_to_text(messages: List[BaseMessage]) -> str:
    lines = []
    for msg in messages:
        role = msg.type
        content = msg.content
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

def safe_json_loads(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
        raise ValueError(f"JSON parsing failed: {text}")

# 예린 - 면적 추천 요청 판별 함수
def is_area_recommendation_request(text: str) -> bool:
    normalized = text.lower()
    return (
        "면적 추천" in text
        or "면적 제안" in text
        or "면적 권장" in text
        or ("면적" in text and "추천" in text)
        or "몇 평" in text
        or "평수 추천" in text
        or ("area" in normalized and "recommend" in normalized)
    )

# 예린 - 예/아니오 판별 함수
def is_affirmative(text: str) -> bool:
    yes_tokens = ["네", "예", "좋아", "좋아요", "해줘", "해주세요", "응", "ㅇㅇ", "yes", "y"]
    return any(token in text.lower() for token in [t.lower() for t in yes_tokens])
    
def is_negative(text: str) -> bool:
    no_tokens = ["아니", "괜찮", "필요없", "skip", "no", "n"]
    return any(token in text.lower() for token in [t.lower() for t in no_tokens])

def room_type_to_label(room_type: str) -> int:
    mapping = {
        "living_room": 0,
        "kitchen": 1,
        "bedroom": 2,
        "bathroom": 3,
        "balcony": 4,
        "entrance": 5,
        "dining_room": 6,
        "study_room": 7,
        "storage": 8,
        "unknown": 9,
        "outside": 10,
    }
    return mapping.get(room_type, 9)

def convert_planning_payload_to_generator_graph(payload: dict) -> dict:
    spaces = payload["design_requirements"]["spaces"]
    edges = payload["design_requirements"]["edges"]
    area_for_generation = payload["generation_context"]["area_m2"]

    rooms = []
    for space in spaces:
        rooms.append(
            {
                "id": space["id"],
                "type": room_type_to_label(space["room_type"]),
                "area": space.get("area"),
            }
        )

    graph_edges = []
    for edge in edges:
        graph_edges.append(
            {
                "source": edge[0],
                "target": edge[1],
            }
        )

    return {
        "rooms": rooms,
        "edges": graph_edges,
        "area_for_generation": area_for_generation,
    }

def save_generator_graph_json(graph_data: dict, name: str) -> str:
    output_dir = PROJECT_ROOT / "data" / "intermediate"
    output_dir.mkdir(parents=True, exist_ok=True)

    graph_json_path = output_dir / f"{name}.json"

    with open(graph_json_path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)

    return str(graph_json_path)

# 노드 정의
def router_node(state: PlanningState) -> PlanningState:
    # 예린 - 면적 추천 요청 여부와 사용자의 동의 상태를 확인해, 면적 추천 실행·거절·재확인 경로로 분기
    user_query = state["messages"][-1].content

    if state.get("area_recommendation_pending"):
        if is_affirmative(user_query):
            return {
                "route": "area_recommendation",
                "area_recommendation_pending": False,
                "area_recommendation_opt_in": True,
            }
        if is_negative(user_query):
            return {
                "route": "area_recommendation_declined",
                "area_recommendation_pending": False,
                "area_recommendation_opt_in": False,
            }
        return {"route": "ask_area_recommendation"}

    if is_area_recommendation_request(user_query):
        if state.get("area_recommendation_opt_in") is True:
            return {"route": "area_recommendation"}
        return {
            "route": "ask_area_recommendation",
            "area_recommendation_pending": True,
            "area_recommendation_opt_in": None,
        }

    # 예린 - 면적 추천 요청이 아닌 경우, 일반적인 계획 수립 경로로 분기
    conversation = messages_to_text(state["messages"])

    # 예린 - 면적 추천 요청 필요 여부 판별, 면적 추천 실행 노드, 면적 추천 거절 노드, 면적 추천 재확인 노드 판별 추가
    system_prompt = """
You are the planning orchestrator router for CADly.

Choose exactly one route.

Routes:

1. reference_agent
- user asks for architectural references
- user asks to improve or develop a design concept

2. site_agent
- user asks about site analysis
- user asks about legal regulation, zoning, setbacks, FAR, BCR
- user asks about sunlight, road, surroundings, land constraints
- user asks about location, address, site, land, candidate site

3. extract_requirements
- user gives spatial requirements
- user describes desired rooms, adjacency, size, area
- user provides or changes output file name
- user wants to organize the current plan
- user asks to generate a drawing but has not confirmed a prepared design payload yet

4. ask_area_recommendation
- user asks for area recommendation but has not explicitly opted in yet

5. area_recommendation
- user explicitly opted in for area recommendation

6. handoff_to_design
- Choose this if a has_design_payload is true
- and the previous assistant message asked for final generation confirmation
- and the user clearly confirms generation

7. general_answer
- general response that does not need another agent

Important:
- If has_design_payload is true and the previous assistant message asked for confirmation and the user confirms, route to handoff_to_design.
- If design_confirmation is false and the user asks to make/generate a drawing, route to extract_requirements first.
- Return only JSON.

{
  "route": "..."
}
"""

    user_prompt = f"""
Conversation:
{conversation}

Current state:
has_design_payload = {state.get("design_payload") is not None}
has_site_analysis = {state.get("site_analysis") is not None}
current_spaces = {json.dumps(state.get("spaces", []), ensure_ascii=False)}
current_edges = {json.dumps(state.get("edges", []), ensure_ascii=False)}
current_output_name = {state.get("output_name")}
current_building_type = {state.get("building_type")}

area_recommendation_pending = {state.get("area_recommendation_pending", False)}
area_recommendation_opt_in = {state.get("area_recommendation_opt_in")}
"""

    response = low_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    parsed = safe_json_loads(response.content)
    route = parsed.get("route", "general_answer")
    # 예린 - 라우터가 허용된 값만 반환하도록 화이트리스트로 방어
    allowed_routes = {
        "reference_agent",
        "site_agent",
        "extract_requirements",
        "ask_area_recommendation",
        "area_recommendation",
        "handoff_to_design",
        "general_answer",
    }
    if route not in allowed_routes:
        route = "general_answer"

    # 사용자가 명시적으로 동의하지 않았으면 면적 추천 실행을 차단하고,반드시 동의 확인 질문 노드로 되돌립니다.
    if route == "area_recommendation" and state.get("area_recommendation_opt_in") is not True:
        return {
            "route": "ask_area_recommendation",
            "area_recommendation_pending": True,
            "area_recommendation_opt_in": None,
        }

    return {
        "route": route,
    }

def reference_agent_node(state: PlanningState) -> PlanningState:
    user_query = state["messages"][-1].content

    result = reference_agent.chat(user_query)

    return {
        "references": result.get("search_results", result.get("images", [])),
        "messages": [
            AIMessage(content=result.get("response", "레퍼런스 분석을 완료했습니다."))
        ],
    }

async def site_agent_node(state: PlanningState) -> PlanningState:
    user_query = state["messages"][-1].content

    result = await site_agent.run(user_query)

    if result.get("status") != "success":
        return {
            "site_analysis": None,
            "messages": [
                AIMessage(content=result.get("message", "대지 분석에 실패했습니다."))
            ],
        }
    
    return {
        "site_analysis": result,
        "messages": [
            AIMessage(
                content=result.get("message", "대지 분석을 완료했습니다.")
            )
        ],
    }

def extract_requirements_node(state: PlanningState) -> PlanningState:
    conversation = messages_to_text(state["messages"])

    current_spaces = state.get("spaces", [])
    current_edges = state.get("edges", [])
    current_output_name = state.get("output_name")
    current_building_type = state.get("building_type")

    system_prompt = """
You are CADly's architectural requirement extractor.

Extract and update the user's design requirements from the conversation.

Important:
- Preserve previous requirements unless the user clearly changes them.
- Use stable room ids in snake_case.
- edges mean adjacency or direct relationship between rooms.
- area is optional. If unknown, use null.
- Do not invent rooms unless strongly implied.
- Extract output_name if the user explicitly mentions a file name.
- Extract building_type if the user mentions building type.

Room normalization:
- 거실 -> living_room
- 주방, 부엌 -> kitchen
- 침실 -> bedroom
- 화장실 -> bathroom
- 현관 -> entrance
- 발코니, 베란다 -> balcony
- 다이닝룸 -> dining_room
- 서재 -> study_room
- 창고 -> storage

Building type normalization:
- 단독주택, 전원주택, 주택, 단독형 주거 -> single_family
- 공동주택, 아파트, 다세대주택, 세대형 주거 -> multi_family
- 상가, 근린생활시설, 문화시설, 업무시설, 그 외 -> non_residential

Return only JSON:
{
  "spaces": [
    {
      "id": "living_room1",
      "room_type": "living_room",
      "area": null,
      "notes": "..."
    }
  ],
  "edges": [
    ["living_room1", "outside"],
  ],
  "output_name": null,
  "building_type": null,
}
"""

    user_prompt = f"""
Current extracted spaces:
{json.dumps(current_spaces, ensure_ascii=False, indent=2)}

Current extracted edges:
{json.dumps(current_edges, ensure_ascii=False, indent=2)}

Current output_name:
{current_output_name}

Current building_type:
{current_building_type}

Conversation:
{conversation}
"""

    response = high_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    parsed = safe_json_loads(response.content)

    return {
        "spaces": parsed.get("spaces", current_spaces),
        "edges": parsed.get("edges", current_edges),
        "output_name": parsed.get("output_name") or current_output_name,
        "building_type": parsed.get("building_type") or current_building_type,
        "design_confirmation": False,
    }

# 예린 - 면적 추천 요청 노드
def ask_area_recommendation_node(state: PlanningState) -> PlanningState:
    return {
        "area_recommendation_pending": True,
        "area_recommendation_opt_in": None,
        "messages": [
            AIMessage(
                content=(
                    "면적 추천을 진행해볼까요?\n"
                    "원하시면 현재 입력된 공간 구성, 건물 유형, 대지 분석 결과를 바탕으로 "
                    "공간별 권장 면적을 제안해드릴게요. (네/아니오)"
                )
            )
        ],
    }

# 예린 - 면적 추천 실행 노드
def area_recommendation_node(state: PlanningState) -> PlanningState:
    result = recommend_area_plan(
        spaces=state.get("spaces", []),
        building_type=state.get("building_type"),
        site_analysis=state.get("site_analysis"),
    )

    if result.get("status") != "success":
        return {
            "area_recommendation_result": result,
            "area_recommendation_pending": False,
            "area_recommendation_opt_in": True,
            "messages": [
                AIMessage(content=result.get("message", "면적 추천을 생성하지 못했습니다."))
            ],
        }

    lines = []
    for item in result.get("recommended_spaces", []):
        lines.append(
            f"- {item.get('id')} ({item.get('room_type')}): {item.get('recommended_area_m2')}㎡"
        )

    assumptions = result.get("assumptions", [])
    assumption_text = "\n".join(f"- {item}" for item in assumptions)

    # 면적 추천 결과 산출 기준 텍스트 생성
    trace = result.get("rule_trace") or {}
    criteria_lines = [
        f"- 총면적 산출 소스: {trace.get('source', result.get('source'))}",
        f"- 가구 프로파일: {trace.get('household_profile', 'unknown')}",
    ]
    if trace.get("main_purpose"):
        criteria_lines.append(f"- 주용도: {trace.get('main_purpose')}")
    if trace.get("legal_zone"):
        criteria_lines.append(f"- 용도지역: {trace.get('legal_zone')}")
    if trace.get("bc_rat"):
        criteria_lines.append(f"- 건폐율 참조: {trace.get('bc_rat')}%")
    if trace.get("vl_rat"):
        criteria_lines.append(f"- 용적률 참조: {trace.get('vl_rat')}%")
    criteria_text = "\n".join(criteria_lines)

    message = (
        "[면적 추천 결과]\n"
        f"- 권장 총면적: {result.get('recommended_total_area_m2')}㎡\n"
        f"- 산출 기준: {result.get('source')}\n\n"
        "[적용 기준]\n"
        f"{criteria_text}\n\n"
        "[공간별 권장 면적]\n"
        f"{chr(10).join(lines) if lines else '- 추천 가능한 공간이 없습니다.'}\n\n"
        "[가정 및 참고]\n"
        f"{assumption_text if assumption_text else '- 없음'}\n\n"
        "원하시면 이 추천값을 기준으로 공간 요구사항을 구체화해 드릴게요."
    )

    return {
        "area_recommendation_result": result,
        "area_recommendation_pending": False,
        "area_recommendation_opt_in": True,
        "messages": [AIMessage(content=message)],
    }

# 예린 - 면적 추천 거절 노드
def area_recommendation_declined_node(state: PlanningState) -> PlanningState:
    return {
        "area_recommendation_pending": False,
        "area_recommendation_opt_in": False,
        "messages": [
            AIMessage(
                content=(
                    "알겠습니다. 면적 추천은 생략할게요.\n"
                    "필요하실 때 '면적 추천해줘'라고 말씀해주시면 다시 진행할 수 있습니다."
                )
            )
        ],
    }

def verification_agent_node(state: PlanningState) -> PlanningState:
    spaces = state.get("spaces", [])
    edges = state.get("edges", [])
    output_name = state.get("output_name")
    building_type = state.get("building_type")
    site_analysis = state.get("site_analysis")

    result = verification_agent.verify(
       spaces=spaces,
       edges=edges,
       output_name=output_name,
       building_type=building_type,
       site_analysis=site_analysis,
    )

    ready_for_design = result.get("ready_for_design", False)
    missing_requirements = result.get("missing_requirements", [])

    message = result.get("message")

    if not message:
        if ready_for_design:
            message = "도면 생성 조건을 모두 확인하였습니다."
        else:
            message = "도면 생성 전에 추가 정보가 필요합니다.\n\n"
            for idx, item in enumerate(missing_requirements, start=1):
                message += f"{idx}. {item}\n"

    return {
        "ready_for_design": ready_for_design,
        "missing_requirements": missing_requirements,
        "messages": [
            AIMessage(content=message)
        ],
    }

def build_design_payload_node(state: PlanningState) -> PlanningState:
    spaces = state.get("spaces", [])
    edges = state.get("edges", [])
    building_type = state.get("building_type")

    if len(spaces) == 1 and not edges: # house diffusion을 위한 최소한의 edge 정보 추가
        spaces = spaces + [
            {
                "id": "outside",
                "room_type": "outside",
                "area": None,
                "notes": "auto-added boundary node",
            }
        ]
        edges = [[spaces[0]["id"], "outside"]]

    site_analysis = state.get("site_analysis") or {}
    diffusion_output = site_analysis.get("diffusion_output", {})

    building_area_m2 = diffusion_output.get("building_area_m2")
    private_area_m2 = diffusion_output.get("private_area_m2")

    if building_type == "multi_family":
        area_for_generation = private_area_m2
    elif building_type == "single_family":
        area_for_generation = building_area_m2
    else:
        return {
            "messages": [
                AIMessage(
                    content="건물 유형이 명확하지 않아 도면을 생성할 수 없습니다. 단독주택인지 공동주택인지 알려주세요."
                )
            ],
        }

    payload = {
        "design_requirements": {
            "spaces": spaces,
            "edges": edges,
        },
        "generation_context": {
            "room_type": [space["room_type"] for space in spaces],
            "area_m2": area_for_generation,
            "area": {
                space["id"]: space.get("area")
                for space in spaces
                if space.get("area") is not None
            },
            "edges": edges,
        },
    }

    message = (
        "다음 조건을 바탕으로 도면 생성을 준비했습니다.\n\n"
        f"[저장 파일명]\n- {state.get('output_name')}\n\n"
        f"[건물 유형]\n- {building_type}\n\n"
        f"[생성 기준 면적]\n- {area_for_generation}㎡\n\n"
        "[공간 구성]\n"
        + "\n".join(
            f"- {space.get('room_type')}"
            + (f" ({space.get('area')}㎡)" if space.get("area") is not None else "")
            for space in spaces
        )
        + "\n\n[공간 연결]\n"
        + "\n".join(
            f"- {edge[0]} ↔ {edge[1]}"
            for edge in edges
            if isinstance(edge, list) and len(edge) == 2
        )
        + "\n\n이 조건으로 도면 생성을 시작해도 될까요?\n"
    )

    return {
        "design_payload": payload,
        "messages": [
            AIMessage(content=message)
        ],
    }

def handoff_to_design_node(state: PlanningState) -> PlanningState:
    payload = state.get("design_payload")

    raw_name = state.get("output_name") or "CADly_Result_001"
    name = (
        raw_name
        .strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )

    graph_data = convert_planning_payload_to_generator_graph(payload)

    graph_json_path = save_generator_graph_json(
        graph_data=graph_data,
        name=name,
    )

    generator = build_design_orchestrator()

    result = generator.invoke(
        {
            "graph_json_path": graph_json_path,
            "model_path": "ckpts/exp/model250000.pt",
            "out_dir": "outputs/cadly",
            "name": name,
        }
    )

    return {
        "design_result": result,
        "messages": [
            AIMessage(
                content=(
                    "도면 생성을 시작합니다.\n\n"
                    f"파일명: {name}\n"
                    f"SVG 경로: {result.get('svg_path')}\n"
                    f"DXF 경로: {result.get('dxf_path')}\n"
                    "생성된 도면을 확인해주세요."
                )
            )
        ],
    }

def general_answer_node(state: PlanningState) -> PlanningState:
    user_query = state["messages"][-1].content

    response = high_llm.invoke([
        SystemMessage(content="You are CADly's planning assistant. Answer clearly in Korean."),
        HumanMessage(content=user_query),
    ])

    return {
        "messages": [
            AIMessage(content=response.content)
        ]
    }

# conditional 라우팅 함수
def route_after_router(state: PlanningState) -> str:
    return state.get("route", "general_answer")

def route_after_verification(state: PlanningState) -> str:
    if state.get("ready_for_design"):
        return "build_design_payload"
    return "end"

# graph 빌드 함수
def build_planning_orchestrator():
    graph = StateGraph(PlanningState)

    graph.add_node("router", router_node)
    graph.add_node("reference_agent", reference_agent_node)
    graph.add_node("site_agent", site_agent_node)
    graph.add_node("extract_requirements", extract_requirements_node)
    # 예린 - 면적 추천 관련 노드 추가
    graph.add_node("ask_area_recommendation", ask_area_recommendation_node)
    graph.add_node("area_recommendation", area_recommendation_node)
    graph.add_node("area_recommendation_declined", area_recommendation_declined_node)
    
    graph.add_node("verification_agent", verification_agent_node)
    graph.add_node("build_design_payload", build_design_payload_node)
    graph.add_node("handoff_to_design", handoff_to_design_node)
    graph.add_node("general_answer", general_answer_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "reference_agent": "reference_agent",
            "site_agent": "site_agent",
            "extract_requirements": "extract_requirements",
            "ask_area_recommendation": "ask_area_recommendation",
            "area_recommendation": "area_recommendation",
            "area_recommendation_declined": "area_recommendation_declined",
            "handoff_to_design": "handoff_to_design",
            "general_answer": "general_answer",
        },
    )

    graph.add_edge("reference_agent", END)
    graph.add_edge("site_agent", END)
    graph.add_edge("general_answer", END)
    graph.add_edge("ask_area_recommendation", END)
    graph.add_edge("area_recommendation", END)
    graph.add_edge("area_recommendation_declined", END)

    graph.add_edge("extract_requirements", "verification_agent")

    graph.add_conditional_edges(
        "verification_agent",
        route_after_verification,
        {
            "build_design_payload": "build_design_payload",
            "end": END,
        },
    )
    
    graph.add_edge("build_design_payload", END)
    graph.add_edge("handoff_to_design", END)

    return graph.compile()


planning_orchestrator = build_planning_orchestrator()