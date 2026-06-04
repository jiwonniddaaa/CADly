# reference_agent/agents/reference_agent.py
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from reference_agent.graph.workflow import app

_CONCEPT_STATE_KEYS = (
    "concept_result",
    "concept_keywords",
    "design_intent",
    "narrative",
    "concept_structured",
    "awaiting_concept_confirmation",
)


class ReferenceAgent:
    def __init__(self, graph=None):
        self.graph = graph or app

    def _build_response_text(self, final_state: Dict[str, Any]) -> str:
        final_messages = final_state.get("messages", [])
        if final_messages:
            return final_messages[-1].content
        return "응답을 생성하지 못했습니다."

    def chat(
        self,
        user_input: str,
        chat_history: Optional[List] = None,
        concept_state: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """
        사용자의 입력을 받아 LangGraph를 실행하고 결과를 반환합니다.
        멀티턴 컨셉 보강을 위해 chat_history와 concept_state를 함께 전달할 수 있습니다.
        """
        if chat_history is None:
            chat_history = []

        messages = chat_history + [HumanMessage(content=user_input)]

        initial_state: Dict[str, Any] = {"messages": messages}
        if concept_state:
            for key in _CONCEPT_STATE_KEYS:
                if key in concept_state:
                    initial_state[key] = concept_state[key]

        final_state = self.graph.invoke(initial_state)

        return {
            "response": self._build_response_text(final_state),
            "search_results": final_state.get("search_results", []),
            "intent": final_state.get("intent", ""),
            "concept_result": final_state.get("concept_result", ""),
            "concept_keywords": final_state.get("concept_keywords", []),
            "design_intent": final_state.get("design_intent", ""),
            "narrative": final_state.get("narrative", ""),
            "concept_structured": final_state.get("concept_structured", {}),
            "concept_updated_at": final_state.get("concept_updated_at", ""),
            "awaiting_concept_confirmation": final_state.get(
                "awaiting_concept_confirmation", False
            ),
            "proceed_to_search": final_state.get("proceed_to_search", False),
        }
