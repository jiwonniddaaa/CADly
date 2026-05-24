from typing import TypedDict, Annotated, Sequence, List, Dict, Any
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    # 대화 기록 유지 (기존 메시지에 새 메시지 추가)
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # 라우팅 결과 (search 또는 concept)
    intent: str
    # 검색용으로 추출된 키워드
    search_query: str
    # 검색된 결과 데이터
    search_results: List[Dict[str, Any]]