from app.graph.workflow import app
from langchain_core.messages import HumanMessage

class ReferenceAgent:
    def __init__(self):
        self.graph = app

    def chat(self, user_input: str, chat_history: list = None) -> dict:
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
        
        # 결과값 파싱
        ai_message = final_state["messages"][-1].content
        search_results = final_state.get("search_results", [])
        
        return {
            "response": ai_message,
            "images": search_results
        }