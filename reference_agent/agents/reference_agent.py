from reference_agent.graph.workflow import app
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

class ReferenceAgent:
    def __init__(self):
        self.graph = app

    def chat(self, user_input: str, chat_history: list[BaseMessage] | None = None) -> dict:
        """
        사용자의 입력을 받아 LangGraph를 실행하고 결과를 반환합니다.
        """
        if chat_history is None:
            chat_history = []
            
        # 새로운 사용자 메시지 추가
        messages = chat_history + [HumanMessage(content=user_input)]
        
        # LangGraph 실행 (초기 state 전달)
        initial_state = {"messages": messages}
        final_state = self.graph.invoke(initial_state)
        
        # 채민 - 최종 state에서 AI 메시지와 검색 결과 추출
        final_messages = final_state.get("messages", [])

        last_ai_message = None
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage):
                last_ai_message = msg
                break

        response_text = (
            last_ai_message.content
            if last_ai_message
            else "응답을 생성하지 못했습니다."
        )

        search_results = final_state.get("search_results", [])

        return {
            "response": response_text,
            "search_results": search_results,
            "concept_result": final_state.get("concept_result"),
        }