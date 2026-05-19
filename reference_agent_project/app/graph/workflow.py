from typing import Annotated, TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from langchain_anthropic import ChatAnthropic
from app.core.config import settings
from app.connectors.image_search import search_reference_images

# 1. 상태(State) 정의
class GraphState(TypedDict):
    messages: Annotated[list, "대화 기록"]
    search_query: str
    search_results: List[Dict[str, Any]]

# 2. LLM 초기화
llm = ChatAnthropic(
    model="claude-3-5-sonnet-latest", 
    anthropic_api_key=settings.ANTHROPIC_API_KEY,
    max_retries=3,
    default_headers={"anthropic-version": "2023-06-01"}
)

# 3. 라우팅 노드: 사용자의 의도를 파악하고 영어 검색어를 추출합니다.
def route_node(state: GraphState):
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
    
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()
    
    if content.startswith("SEARCH:"):
        query = content.replace("SEARCH:", "").strip()
        return {"search_query": query}
    else:
        return {"search_query": "modern architecture interior"}

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
    
    response = llm.invoke([HumanMessage(content=briefing_prompt)])
    ai_message = AIMessage(content=response.content)
    
    # 최종 결과 반환 (이 결과가 프론트엔드로 전달됩니다)
    return {
        "messages": [ai_message],
        "search_results": results
    }

# 5. 그래프(Workflow) 구성
workflow = StateGraph(GraphState)

workflow.add_node("route_node", route_node)
workflow.add_node("search_node", search_node)

# 흐름: 시작 -> 검색어 추출 -> SerpApi 이미지 검색 및 응답 생성 -> 종료
workflow.set_entry_point("route_node")
workflow.add_edge("route_node", "search_node")
workflow.add_edge("search_node", END)

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