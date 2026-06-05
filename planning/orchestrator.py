from __future__ import annotations

import json
import base64
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
from planning.planning_agent import PlanningAgent
from design.orchestrator import build_design_orchestrator
from langchain_anthropic import ChatAnthropic

from image_modules import sketch_agent
from image_modules.image_understanding_node import image_understanding_node

sketch_agent_instance = sketch_agent.SketchAgent()

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

planning_agent = PlanningAgent()

# State 정의
class SpaceRequirement(TypedDict, total=False):
    id: str
    room_type: str
    area: Optional[float]
    notes: Optional[str]

class PlanningState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]

    route: Literal[
        "image_understanding", 
        "sketch_analysis_node",      
        "sketch_extract_node",   
        "reference_agent",
        "site_agent",
        "extract_requirements",
        "planning_agent",
        "handoff_to_design",
        "general_answer",
    ]

    # planning context
    concept: Optional[str]
    # 예린 - 컨셉 키워드, 설계 의도, 내러티브, 구조화 결과, 업데이트 시간 추가
    concept_keywords: Optional[List[str]]
    design_intent: Optional[str]
    narrative: Optional[str]
    concept_structured: Optional[Dict[str, Any]]
    concept_updated_at: Optional[str]
    awaiting_concept_confirmation: bool

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

    # area recommendation state
    area_recommendation_result: Optional[Dict[str, Any]]
    area_decision_pending: bool
    area_mode_pending: bool
    next_step: Optional[str]
    awaiting_manual_area_input: bool

    # [추가] 이미지 처리용 컨텍스트 정보
    image_path: Optional[str]
    user_input: Optional[str]
    image_type: Optional[str]
    image_classification: Optional[Dict[str, Any]]
    sketch_analysis: Optional[Dict[str, Any]]
    sketch_result: Optional[Dict[str, Any]]

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

def _encode_image(image_path: str) -> Tuple[str, str]:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = mime_map.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(f"지원하지 않는 이미지 형식입니다: {path.suffix}")

    image_data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return image_data, media_type

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

# 노드 정의
def router_node(state: PlanningState) -> PlanningState:
    if state.get("image_path"):
        return {
            "route": "image_understanding"
        }

    user_query = state["messages"][-1].content if state["messages"] else ""
    
    extracted_image_path = None
    words = user_query.split()
    for word in words:
        if word.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            extracted_image_path = word
            break

    # 2. 이미지 경로가 발견되면, state를 업데이트하고 즉시 이미지 이해 노드로 강제 라우팅
    if extracted_image_path:
        # 다음 노드들이 사용할 수 있도록 image_path를 상태에 저장하고 라우팅 지시
        return {
            "route": "image_understanding",
            "image_path": extracted_image_path
        }

    # "직접 입력"을 선택한 직후 턴은 무조건 요구사항 추출 노드로 보냅니다.
    if state.get("awaiting_manual_area_input"):
        return {"route": "extract_requirements"}

    # PlanningAgent가 사용자 면적 의사결정(yes/no 또는 입력 방식 선택)을 기다리는 상태면
    # LLM 라우팅을 우회하고 planning_agent로 직접 보냅니다.
    if state.get("area_decision_pending") or state.get("area_mode_pending"):
        return {"route": "planning_agent"}

    # 컨셉 확인(레퍼런스 검색 여부) 대기 중이면 reference_agent로 보냅니다.
    if state.get("awaiting_concept_confirmation"):
        return {"route": "reference_agent"}

    conversation = messages_to_text(state["messages"])
    system_prompt = """
You are the planning orchestrator router for CADly.

Choose exactly one route.

Routes:

1. reference_agent
- User asks for architectural/interior design references, styles, ideas, or examples.
- User wants to develop, clarify, or improve a design concept (e.g., "도시적", "모던한", "세련된 느낌").

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

4. planning_agent
- follow-up response for area decision flow (yes/no, manual/recommend)

5. handoff_to_design
- Choose this if a has_design_payload is true
- and the previous assistant message asked for final generation confirmation
- and the user clearly confirms generation

6. general_answer
- general response that does not need another agent

CRITICAL ROUTING PRIORITIES & RULES:
- If has_design_payload is true and the previous assistant message asked for confirmation and the user confirms, route to handoff_to_design.
- If design_confirmation is false and the user asks to make/generate a drawing, route to extract_requirements first.
- Return only JSON.

Few-Shot Examples:
- "강남구 역삼동 땅에 지을만한 세련된 아파트 사진이나 사례 좀 찾아봐" -> reference_agent (Focus is on visual concepts/examples)
- "역삼동 747 아파트 규제 법규나 건폐율 알려줘" -> site_agent
- "방 3개랑 거실 구조로 도면 한번 설계해볼래?" -> extract_requirements (Initial request without confirmed payload)
- "그래, 그 조건대로 도면 바로 생성해줘." (When payload is ready) -> handoff_to_design
- "너 이름이 뭐야?" -> general_answer

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
"""

    response = low_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    parsed = safe_json_loads(response.content)
    route = parsed.get("route", "general_answer")
    # 예린 - 라우터가 허용된 값만 반환하도록 화이트리스트로 방어
    allowed_routes = {
        "image_understanding",
        "reference_agent",
        "site_agent",
        "extract_requirements",
        "planning_agent",
        "handoff_to_design",
        "general_answer",
    }
    if route not in allowed_routes:
        route = "general_answer"

    return {
        "route": route,
    }

def reference_agent_node(state: PlanningState) -> PlanningState:
    # 예린 - 마지막 메시지는 현재 사용자 입력, 이전 메시지는 채팅 기록하여 이전 대화 흐름까지 참조하도록 수정 
    messages = state["messages"]
    user_query = messages[-1].content
    chat_history = messages[:-1]

    concept_state = {
        "concept_result": state.get("concept") or "",
        "concept_keywords": state.get("concept_keywords") or [],
        "design_intent": state.get("design_intent") or "",
        "narrative": state.get("narrative") or "",
        "concept_structured": state.get("concept_structured") or {},
        "awaiting_concept_confirmation": state.get("awaiting_concept_confirmation", False),
    }

    result = reference_agent.chat(
        user_query,
        chat_history=chat_history,
        concept_state=concept_state,
    )

    update: PlanningState = {
        "references": result.get("search_results", result.get("images", [])),
        "concept": result.get("concept_result") or state.get("concept"),
        "messages": [
            AIMessage(content=result.get("response", "레퍼런스 분석을 완료했습니다."))
        ],
        "awaiting_concept_confirmation": result.get(
            "awaiting_concept_confirmation", False
        ),
    }

    # 예린 - 컨셉 개발 의도가 있거나 컨셉 결과가 있으면 컨셉 상태를 업데이트함
    if result.get("intent") == "concept_develop" or result.get("concept_result"):
        update.update(
            {
                "concept": result.get("concept_result") or state.get("concept"),
                "concept_keywords": result.get("concept_keywords", []),
                "design_intent": result.get("design_intent", ""),
                "narrative": result.get("narrative", ""),
                "concept_structured": result.get("concept_structured", {}),
                "concept_updated_at": result.get("concept_updated_at", ""),
            }
        )

    return update

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
        "awaiting_manual_area_input": False,
        "design_confirmation": False,
    }

def planning_agent_node(state: PlanningState) -> PlanningState:
    result = planning_agent.run(state)
    return {
        "ready_for_design": result.get("ready_for_design", False),
        "missing_requirements": result.get("missing_requirements", []),
        "spaces": result.get("spaces", state.get("spaces", [])),
        "area_recommendation_result": result.get("area_recommendation_result"),
        "area_decision_pending": result.get("area_decision_pending", False),
        "area_mode_pending": result.get("area_mode_pending", False),
        "awaiting_manual_area_input": result.get("awaiting_manual_area_input", False),
        "next_step": result.get("next_step"),
        "messages": result.get("messages", []),
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

    return {
        "active_orchestrator": "design",
        "design_state": {
            "graph_data": graph_data,
            "name": name,
        },
        "messages": [
            AIMessage(
                content=(
                    "기획 정보를 바탕으로 설계 단계로 넘어갑니다.\n\n"
                    f"파일명: {name}\n"
                    "이제 도면 생성, 수정, CAD 연동 작업을 진행할 수 있습니다."
                )
            )
        ],
    }

def general_answer_node(state: PlanningState) -> PlanningState:
    user_query = state["messages"][-1].content

    response = high_llm.invoke([
        SystemMessage(content="""
You are CADly, an AI architectural planning and design assistant.

CADly helps users with:
- architectural planning
- spatial programming
- design concept development
- site and zoning understanding
- floorplan generation workflows
- architectural reference exploration
- CAD-based design assistance

Always respond in natural Korean.

Guidelines:
- Be concise but helpful.
- Maintain the tone of a professional architectural design assistant.
- When users ask casual questions, respond naturally while maintaining CADly's identity.
- When users ask about architecture, space, buildings, planning, floorplans, design concepts, or CAD workflows, answer as an architectural planning/design assistant.
- Do not pretend to have completed actions that were not actually executed.
- If the user asks about capabilities, explain CADly as an architectural planning and design support system.
"""
),
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

def route_after_image_understanding(state: PlanningState) -> str:
    return state.get("route", "general_answer")

def route_after_planning_agent(state: PlanningState) -> str:
    if state.get("area_decision_pending") or state.get("area_mode_pending"):
        return "end"

    if state.get("next_step") == "build_design_payload":
        return "build_design_payload"

    if not state.get("ready_for_design"):
        return "end"

    return "end"

# graph 빌드 함수
def build_planning_orchestrator():
    graph = StateGraph(PlanningState)

    graph.add_node("router", router_node)
    graph.add_node("image_understanding", image_understanding_node)
    
    graph.add_node("sketch_analysis_node", sketch_agent_instance.analysis_node)          
    graph.add_node("sketch_extract_node", sketch_agent_instance.extract_node)    
    graph.add_node("reference_agent", reference_agent_node)
    graph.add_node("site_agent", site_agent_node)
    graph.add_node("extract_requirements", extract_requirements_node)
    graph.add_node("planning_agent", planning_agent_node)
    graph.add_node("build_design_payload", build_design_payload_node)
    graph.add_node("handoff_to_design", handoff_to_design_node)
    graph.add_node("general_answer", general_answer_node)

    graph.add_edge(START, "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "image_understanding": "image_understanding", # 이미지 진입 분기 추가
            "reference_agent": "reference_agent",
            "site_agent": "site_agent",
            "extract_requirements": "extract_requirements",
            "planning_agent": "planning_agent",
            "handoff_to_design": "handoff_to_design",
            "general_answer": "general_answer",
        },
    )
    
    # 이미지 전용 조건부 에지 맵 추가
    graph.add_conditional_edges(
        "image_understanding",
        route_after_image_understanding,
        {
            "sketch_agent_node": "sketch_analysis_node",
            "reference_agent": "reference_agent",
            "general_answer": "general_answer"
        }
    )

    # 손도면 흐름 연결 후 한 턴 대기종료
    graph.add_edge("sketch_analysis_node", "sketch_extract_node")
    graph.add_edge("sketch_extract_node", END)

    graph.add_edge("reference_agent", END)
    graph.add_edge("site_agent", END)
    graph.add_edge("general_answer", END)

    graph.add_edge("extract_requirements", "planning_agent")

    graph.add_conditional_edges(
        "planning_agent",
        route_after_planning_agent,
        {
            "build_design_payload": "build_design_payload",
            "end": END,
        },
    )
    graph.add_edge("build_design_payload", END)
    graph.add_edge("handoff_to_design", END)

    return graph.compile()


planning_orchestrator = build_planning_orchestrator()