import json
from datetime import datetime, timezone
from typing import Annotated, TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from langchain_anthropic import ChatAnthropic
from reference_agent.core.config import settings
from reference_agent.connectors.image_search import search_reference_images

# 1. 상태(State) 정의
class GraphState(TypedDict):
    messages: Annotated[list, "대화 기록"]
    intent: str

    # 채민 - reference search 전용 state
    search_query: str
    search_results: List[Dict[str, Any]]

    # 채민 - concept/narrative 강화 전용 state 추가 (필요에 따라 자유롭게 수정)
    concept_result: str
    concept_keywords: List[str]
    design_intent: str
    narrative: str

    # 예린 - 컨셉 구조화 전용 state 추가
    concept_structured: Dict[str, Any] # 컨셉 구조화 결과
    concept_updated_at: str # 컨셉 구조화 시간  


# 2. LLM 초기화
high_llm = ChatAnthropic(
    # 채민 - 3-5 버전이 안 돌아가서 4-5로 변경
    model="claude-sonnet-4-5-20250929", 
    # 예린 - factchat-cloud 모델 사용
    anthropic_api_url=settings.ANTHROPIC_BASE_URL,
    anthropic_api_key=settings.ANTHROPIC_AUTH_TOKEN,

    #anthropic_api_key=settings.ANTHROPIC_API_KEY,
    max_retries=3,
    default_headers={"anthropic-version": "2023-06-01"}
)
# 채민 - 라우팅 및 쿼리 관련 작업은 저사양 모델로 빠르게 처리
low_llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",

    # 예린 - factchat-cloud 모델 사용
    anthropic_api_url=settings.ANTHROPIC_BASE_URL,
    anthropic_api_key=settings.ANTHROPIC_AUTH_TOKEN,
    # anthropic_api_key=settings.ANTHROPIC_API_KEY,
    max_retries=3,
    default_headers={"anthropic-version": "2023-06-01"}
)

# 3. 라우팅 노드: 사용자의 의도를 파악하고 영어 검색어를 추출합니다.
def route_node(state: GraphState):
    # 채민 - 검색어 추출은 query processing 노드로 옮기고, route_node는 단순히 의도 파악과 라우팅 역할만 하도록 변경
    user_input = state["messages"][-1].content

    prompt = f"""
    사용자의 요청을 분석해서 아래 둘 중 하나로만 분류하세요.

    - reference_search: 건축/인테리어 레퍼런스 이미지, 사례, 분위기 자료를 찾아달라는 요청
    - concept_develop: 건축 컨셉, 설계 의도, 내러티브, 의미 부여, 공간 서사를 강화해달라는 요청

    사용자 입력:
    {user_input}

    출력 형식:
    reference_search 또는 concept_develop 중 하나만 출력
    """

    # 채민 - 라우팅은 저사양 모델로 처리
    response = low_llm.invoke([HumanMessage(content=prompt)])
    intent = response.content.strip()

    if intent not in ["reference_search", "concept_develop"]:
        intent = "reference_search"

    return {"intent": intent}

# 채민 - route node의 결과에 따라 다음 노드를 결정하는 조건부 라우터
def conditional_router(state: GraphState):
    if state.get("intent") == "concept_develop":
        return "concept_node"
    return "query_processing_node"

# 4. 검색 노드: SerpApi 커넥터를 호출하여 이미지를 가져오고 브리핑을 생성합니다.
def search_node(state: GraphState):
    query = state.get("search_query", "")
    
    # SerpApi 연동 커넥터 호출
    results = search_reference_images(query=query, limit=5)
    
    if not results:
        error_msg = AIMessage(content="죄송합니다. 해당 컨셉의 레퍼런스 이미지를 찾는 데 실패했습니다. 다른 키워드로 검색해 보시겠어요?")
        return {"messages": [error_msg], "search_results": []}

    # 검색된 결과에 대한 간단한 에이전트 브리핑 생성
    briefing_prompt = f"""
    사용자가 찾고자 하는 컨셉({query})에 대해 이미지들을 찾았습니다.
    이 이미지들이 사용자의 건축/인테리어 컨셉 구상에 어떤 영감을 줄 수 있는지 3~4문장으로 짧고 전문적으로 브리핑해주세요.
    """
    
    # 채민 - 브리핑은 고사양 모델로 처리
    response = high_llm.invoke([HumanMessage(content=briefing_prompt)])
    ai_message = AIMessage(content=response.content)
    
    # 최종 결과 반환 (이 결과가 프론트엔드로 전달됩니다)
    return {
        "messages": [ai_message],
        "search_results": results
    }

# 채민 - 쿼리 관련 작업 노드
def query_processing_node(state: GraphState):
    # 채민 - 기존 route_node의 기능을 이 노드로 옮겨서, route_node는 단순히 의도 파악과 라우팅 역할만 하도록 변경
    # 채민 - 예린 님 구현 방식에 따라 아래 내용은 자유롭게 수정하셔도 됩니다
    messages = state["messages"]
    user_input = messages[-1].content

    prompt = f"""
    당신은 건축/인테리어 레퍼런스 이미지를 찾아주는 전문 에이전트입니다.
    사용자의 입력을 분석하여 구글 이미지 검색에 사용할 핵심 영어 키워드를 추출하세요.
    
    사용자 입력: {user_input}
    
    출력 형식 (반드시 아래 형식의 단일 문자열로만 응답하세요):
    SEARCH: [영어 검색어]
    
    예시:
    입력: 밝은 분위기의 나무 소재 집 찾아줘
    출력: SEARCH: bright wooden house exterior interior
    """
    
    # 채민 - 쿼리 추출은 저사양 모델로 처리
    response = low_llm.invoke([HumanMessage(content=prompt)])

    content = response.content.strip()
    
    if content.startswith("SEARCH:"):
        query = content.replace("SEARCH:", "").strip()
        return {"search_query": query}
    else:
        return {"search_query": "modern architecture interior"}
    return state

# 예린 - concept/narrtive 구조화 노드
def concept_node(state: GraphState):
    user_input = state["messages"][-1].content
    previous_concept_state = {
        "concept_result": state.get("concept_result", ""),
        "concept_keywords": state.get("concept_keywords", []),
        "design_intent": state.get("design_intent", ""),
        "narrative": state.get("narrative", ""),
    }

    prompt = f"""
    당신은 건축 컨셉 디렉터입니다.

    [역할]
    - 사용자 입력을 바탕으로 건축적 의도, 공간의 존재 이유(reason), 사용자 경험 흐름(journey)을 구조화합니다.

    [입력]
    1) 사용자 원문:
    {user_input}

    2) 이전 컨셉 state(있다면 참고):
    {previous_concept_state}

    [출력 규칙]
    - 반드시 JSON 객체 하나만 출력하세요. 설명 문장, 코드블록, 마크다운 금지.
    - 추측/과장/근거 없는 수치(면적, 비용, 성능 등)를 만들지 마세요.
    - 입력에 없는 사실은 생성하지 말고, 필요한 경우 uncertainties에 명시하세요.

    [품질 기준]
    - spatial_reasoning에는 각 공간의 존재 이유(reason)가 반드시 포함되어야 합니다.
    - user_journey에는 사용자의 경험 흐름(journey)이 단계적으로 반드시 포함되어야 합니다.

    [JSON 스키마]
    {{
    "concept_title": "string",
    "concept_keywords": ["string", "string"],
    "design_intent": "2~4문장",
    "spatial_reasoning": [
        {{
        "space": "string",
        "reason": "string"
        }}
    ],
    "user_journey": [
        {{
        "step": 1,
        "scene": "string",
        "experience": "string",
        "design_response": "string"
        }}
    ],
    "narrative": "4~7문장",
    "uncertainties": ["string"]
    }}

    [추가 제약]
    - concept_keywords는 4~8개로 작성하세요.
    - user_journey는 최소 3단계 이상 작성하세요.
    - spatial_reasoning은 최소 3개 항목 작성하세요.
    """

    # 채민 - 컨셉 강화 작업은 고사양 모델로 처리
    response = high_llm.invoke([HumanMessage(content=prompt)])

    # 예린 - 컨셉 구조화 결과 추출
    raw_content = response.content.strip()

    try:
        start = raw_content.find("{")
        end = raw_content.rfind("}")
        if start != -1 and end != -1 and end > start:
            structured = json.loads(raw_content[start:end + 1])
        else:
            structured = {}
    except Exception:
        structured = {}

    concept_keywords = structured.get("concept_keywords", [])
    if not isinstance(concept_keywords, list):
        concept_keywords = []
    concept_keywords = [str(k).strip() for k in concept_keywords if str(k).strip()]

    design_intent = str(structured.get("design_intent", "")).strip()
    narrative = str(structured.get("narrative", "")).strip()
    concept_title = str(structured.get("concept_title", "컨셉 제안")).strip() or "컨셉 제안"

    if not design_intent:
        design_intent = "사용자 요청을 바탕으로 공간의 목적과 관계를 중심으로 설계 의도를 정리했습니다."
    if not narrative:
        narrative = "진입-체류-전환 흐름을 기준으로 사용자 경험을 단계적으로 구성했습니다."

    user_message = (
        f"[{concept_title}]\n\n"
        f"설계 의도:\n{design_intent}\n\n"
        f"공간 내러티브:\n{narrative}"
    )
    if concept_keywords:
        user_message += "\n\n디자인 키워드:\n- " + "\n- ".join(concept_keywords)

    return {
        "messages": [AIMessage(content=user_message)],
        "concept_result": user_message,
        "concept_keywords": concept_keywords,
        "design_intent": design_intent,
        "narrative": narrative,
        "concept_structured": structured if structured else {"raw_response": raw_content},
        "concept_updated_at": datetime.now(timezone.utc).isoformat(),
        "search_results": []
    }

# 5. 그래프(Workflow) 구성
workflow = StateGraph(GraphState)

workflow.add_node("route_node", route_node)
workflow.add_node("search_node", search_node)
# 채민 - 노드 추가
workflow.add_node("query_processing_node", query_processing_node)
workflow.add_node("concept_node", concept_node)

# 흐름: 시작 -> 검색어 추출 -> SerpApi 이미지 검색 및 응답 생성 -> 종료
# 채민 - 노드 간 흐름 추가
workflow.set_entry_point("route_node")
workflow.add_conditional_edges(
    "route_node",
    conditional_router,
    {
        "query_processing_node": "query_processing_node",
        "concept_node": "concept_node"
    }
)
workflow.add_edge("query_processing_node", "search_node")
workflow.add_edge("search_node", END)
workflow.add_edge("concept_node", END)

app = workflow.compile()


# -- 클로드 api가 돌아가지 않을 때, 서치 api만 확인하는 코드 --

# from langgraph.graph import StateGraph, END
# from langchain_core.messages import AIMessage
# from app.models.schemas import AgentState
# from app.connectors.archdaily import search_archdaily
# from app.connectors.pinterest import search_pinterest
# import json

# def route_node(state: AgentState):
#     """
#     [임시 테스트 모드] LLM을 거치지 않고, 사용자가 입력한 자연어 그대로 검색어로 설정합니다.
#     """
#     last_user_message = state["messages"][-1].content
#     print(f"=== [임시] 사용자의 입력 그대로 검색을 진행합니다: {last_user_message} ===")
#     return {"intent": "search", "search_query": last_user_message}

# def search_node(state: AgentState):
#     """
#     GCP Custom Search API를 직접 호출하여 ArchDaily와 Pinterest에서 이미지를 가져옵니다.
#     """
#     query = state.get("search_query", "")
    
#     # 구글 이미지 검색 엔진 가동
#     archdaily_results = search_archdaily(query, num=3)
#     pinterest_results = search_pinterest(query, num=3)
#     combined_results = archdaily_results + pinterest_results
    
#     # LLM이 바빠서 대답을 못 하므로, 텍스트 답변은 가짜 디자이너 멘트로 대체합니다.
#     fake_ai_response = AIMessage(
#         content=f"안녕하세요! 요청하신 '{query}' 컨셉에 맞는 건축 레퍼런스 이미지를 ArchDaily와 Pinterest에서 실시간으로 찾아 하단에 첨부해 드렸습니다. 마음에 드시는 분위기가 있는지 확인해 보세요!"
#     )
    
#     return {
#         "messages": [fake_ai_response], 
#         "search_results": combined_results
#     }

# def concept_node(state: AgentState):
#     # 테스트 중에는 사용되지 않음
#     return state

# def conditional_router(state: AgentState):
#     # 무조건 이미지 검색 노드로 직진합니다.
#     return "search_node"

# # LangGraph 그래프 빌드
# workflow = StateGraph(AgentState)

# # 노드 등록
# workflow.add_node("route_node", route_node)
# workflow.add_node("search_node", search_node)
# workflow.add_node("concept_node", concept_node)

# # 진입점 및 경로 설정 (무조건 search_node로 이동)
# workflow.set_entry_point("route_node")
# workflow.add_conditional_edges(
#     "route_node",
#     conditional_router,
#     {
#         "search_node": "search_node",
#         "concept_node": "concept_node"
#     }
# )

# workflow.add_edge("search_node", END)
# app = workflow.compile()