# from langgraph.graph import StateGraph, END
# from langchain_anthropic import ChatAnthropic
# from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
# from app.models.schemas import AgentState
# from app.connectors.archdaily import search_archdaily
# from app.connectors.pinterest import search_pinterest
# from app.core.config import settings
# import json

# # LLM 초기화 (자동 재시도 설정 포함)
# llm = ChatAnthropic(
#     model="claude-3-sonnet-20240229", 
#     temperature=0,
#     api_key=settings.ANTHROPIC_API_KEY,
#     max_retries=3
# )

# def route_node(state: AgentState):
#     """
#     사용자의 입력을 분석하여 '검색(search)' 목적일지 '컨셉 구체화(concept)' 목적일지 판단합니다.
#     사용자가 특정 분위기, 소재, 스타일을 언급하면 우선적으로 'search'로 판단하여 이미지를 보여주도록 유도합니다.
#     """
#     messages = state.get("messages", [])
#     last_user_message = messages[-1].content
    
#     system_prompt = """
#     당신은 건축 레퍼런스 에이전트의 스마트한 라우터입니다. 
#     사용자의 메시지를 분석하여 의도(intent)를 "search" 또는 "concept" 중 하나로 분류하고 반드시 지정된 JSON 형식으로만 응답하세요.

#     [분류 가이드라인]
#     1. "search": 사용자가 특정 분위기(예: 밝은, 어두운), 소재(예: 콘크리트, 원목), 건축물 종류(예: 단독주택, 카페) 등을 언급하며 레퍼런스나 이미지를 보고 싶어 하는 뉘앙스가 조금이라도 있다면 무조건 "search"로 분류하세요.
#        - 예: "밝은 분위기의 집 설계하고 싶어" -> 밝은 분위기의 집 레퍼런스 검색 필요 ("search")
#     2. "concept": 구체적인 이미지 검색 없이, 순수하게 디자이너와 건축 철학이나 예산, 라이프스타일에 대해 질문하고 이야기 나누고 싶어 할 때만 "concept"으로 분류하세요.

#     [검색어 추출 규칙 (search_query)]
#     - 사용자의 의도가 "search"일 때, 구글 이미지 검색창에 입력하기 가장 적합한 핵심 건축 키워드 조합을 한국어로 간결하게 작성하세요.
#     - 예: "밝은 분위기의 집" -> "밝은 화이트 톤 단독주택"
#     - 예: "노출콘크리트 카페" -> "노출 콘크리트 모던 카페 건축"

#     반드시 아래의 JSON 형식만 반환하세요. 다른 설명은 금지합니다:
#     {"intent": "search", "search_query": "추출된 검색어"}
#     """
    
#     response = llm.invoke([
#         SystemMessage(content=system_prompt),
#         HumanMessage(content=last_user_message)
#     ])
    
#     # 모델의 응답 텍스트 정제 (혹시 모를 마크다운 block 제거)
#     content = response.content.strip()
#     if content.startswith("```json"):
#         content = content.split("```json")[1].split("```")[0].strip()
#     elif content.startswith("```"):
#         content = content.split("```")[1].split("```")[0].strip()

#     try:
#         parsed = json.loads(content)
#         intent = parsed.get("intent", "search")  # 기본값은 search로 변경
#         search_query = parsed.get("search_query", last_user_message)
#     except Exception:
#         intent = "search"
#         search_query = last_user_message
        
#     return {"intent": intent, "search_query": search_query}

# def search_node(state: AgentState):
#     """
#     추출된 키워드로 구글 서치 API를 연동해 이미지를 가져오고, 
#     가져온 이미지를 기반으로 디자이너로서 사용자에게 브리핑 대답을 생성합니다.
#     """
#     query = state.get("search_query", "")
    
#     # 1단계에서 세팅한 구글 엔진 가동 (각각 3개씩 검색)
#     archdaily_results = search_archdaily(query, num=3)
#     pinterest_results = search_pinterest(query, num=3)
#     combined_results = archdaily_results + pinterest_results
    
#     # 검색된 결과가 아예 없을 때를 대비한 안전망
#     if not combined_results:
#         system_prompt = f"사용자가 '{query}' 레퍼런스를 요청했으나 구글 검색 엔진에서 이미지를 찾지 못했습니다. 미안함을 전하고 어떤 식으로 다시 검색하면 좋을지 친절하게 안내하세요."
#         response = llm.invoke([
#             SystemMessage(content=system_prompt),
#             HumanMessage(content="레퍼런스 검색 결과를 브리핑해줘.")
#         ])
#         return {"messages": [response], "search_results": []}

#     # 이미지가 정상적으로 검색되었을 때 LLM의 설명 가이드
#     system_prompt = f"""
#     당신은 전문 건축 디자이너 파트너입니다. 
#     사용자가 요청한 컨셉 관련해서 검색된 아래의 실제 레퍼런스 이미지 정보(메타데이터)를 바탕으로, 전문적이고 친절하게 인사를 건네며 레퍼런스를 추천해주세요.
    
#     [검색된 레퍼런스 데이터]
#     {json.dumps(combined_results, ensure_ascii=False)}

#     [답변 가이드]
#     - 질문만 던지지 말고, "요청하신 분위기에 맞는 좋은 레퍼런스들을 찾아왔습니다"라며 검색 결과의 특징을 요약해서 먼저 브리핑해 주세요.
#     - 대화의 마지막에는 사용자의 생각을 가볍게 물어보며 자연스럽게 대화를 이어가세요.
#     """
    
#     response = llm.invoke([
#         SystemMessage(content=system_prompt),
#         HumanMessage(content="검색된 레퍼런스 목록을 바탕으로 친절하게 설명해줘.")
#     ])
    
#     return {
#         "messages": [response], 
#         "search_results": combined_results
#     }

# def concept_node(state: AgentState):
#     """
#     컨셉 구체화를 위한 대화 노드
#     """
#     response = llm.invoke(state["messages"] + [
#         SystemMessage(content="당신은 사용자와 함께 건축 컨셉에 대해 깊이 있는 대화를 나누고 아이디어를 구체화하는 건축가입니다. 친절하고 전문적으로 답변하세요.")
#     ])
#     return {"messages": [response]}

# def conditional_router(state: AgentState):
#     """
#     라우트 노드의 결과에 따라 다음 노드를 결정하는 조건부 엣지 함수
#     """
#     if state["intent"] == "search":
#         return "search_node"
#     return "concept_node"

# # LangGraph 그래프 빌드
# workflow = StateGraph(AgentState)

# # 노드 등록
# workflow.add_node("route_node", route_node)
# workflow.add_node("search_node", search_node)
# workflow.add_node("concept_node", concept_node)

# # 엔트리 포인트 설정
# workflow.set_entry_point("route_node")

# # 조건부 엣지 등록
# workflow.add_conditional_edges(
#     "route_node",
#     conditional_router,
#     {
#         "search_node": "search_node",
#         "concept_node": "concept_node"
#     }
# )

# # 각 실행 노드가 끝나면 END로 이동
# workflow.add_edge("search_node", END)
# workflow.add_edge("concept_node", END)

# # 그래프 컴파일
# app = workflow.compile()

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
from app.models.schemas import AgentState
from app.connectors.archdaily import search_archdaily
from app.connectors.pinterest import search_pinterest
import json

def route_node(state: AgentState):
    """
    [임시 테스트 모드] LLM을 거치지 않고, 사용자가 입력한 자연어 그대로 검색어로 설정합니다.
    """
    last_user_message = state["messages"][-1].content
    print(f"=== [임시] 사용자의 입력 그대로 검색을 진행합니다: {last_user_message} ===")
    return {"intent": "search", "search_query": last_user_message}

def search_node(state: AgentState):
    """
    GCP Custom Search API를 직접 호출하여 ArchDaily와 Pinterest에서 이미지를 가져옵니다.
    """
    query = state.get("search_query", "")
    
    # 구글 이미지 검색 엔진 가동
    archdaily_results = search_archdaily(query, num=3)
    pinterest_results = search_pinterest(query, num=3)
    combined_results = archdaily_results + pinterest_results
    
    # LLM이 바빠서 대답을 못 하므로, 텍스트 답변은 가짜 디자이너 멘트로 대체합니다.
    fake_ai_response = AIMessage(
        content=f"안녕하세요! 요청하신 '{query}' 컨셉에 맞는 건축 레퍼런스 이미지를 ArchDaily와 Pinterest에서 실시간으로 찾아 하단에 첨부해 드렸습니다. 마음에 드시는 분위기가 있는지 확인해 보세요!"
    )
    
    return {
        "messages": [fake_ai_response], 
        "search_results": combined_results
    }

def concept_node(state: AgentState):
    # 테스트 중에는 사용되지 않음
    return state

def conditional_router(state: AgentState):
    # 무조건 이미지 검색 노드로 직진합니다.
    return "search_node"

# LangGraph 그래프 빌드
workflow = StateGraph(AgentState)

# 노드 등록
workflow.add_node("route_node", route_node)
workflow.add_node("search_node", search_node)
workflow.add_node("concept_node", concept_node)

# 진입점 및 경로 설정 (무조건 search_node로 이동)
workflow.set_entry_point("route_node")
workflow.add_conditional_edges(
    "route_node",
    conditional_router,
    {
        "search_node": "search_node",
        "concept_node": "concept_node"
    }
)

workflow.add_edge("search_node", END)
app = workflow.compile()