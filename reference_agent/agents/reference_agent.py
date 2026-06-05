# reference_agent/agents/reference_agent.py
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from reference_agent.graph.workflow import app
from reference_agent.utils.message_content import build_human_message

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
        user_input: str = "",
        chat_history: Optional[List[BaseMessage]] = None,
        concept_state: Optional[Dict[str, Any]] = None,
        *,
        image_path: Optional[str] = None,
        image_base64: Optional[str] = None,
        image_media_type: Optional[str] = None,
    ) -> dict:
        """
        텍스트 또는 이미지(경로/base64)로 레퍼런스 에이전트를 실행합니다.
        이미지가 있으면 Vision으로 검색 키워드를 추출한 뒤 유사 레퍼런스를 검색합니다.
        """
        if chat_history is None:
            chat_history = []

        has_image = bool(image_path or image_base64)
        if not has_image and not (user_input or "").strip():
            return {
                "response": "검색할 텍스트 또는 이미지를 입력해 주세요.",
                "search_results": [],
                "intent": "",
                "input_mode": "text",
            }

        user_message = build_human_message(
            text=user_input,
            image_path=image_path,
            image_base64=image_base64,
            image_media_type=image_media_type,
        )
        messages = list(chat_history) + [user_message]

        initial_state: Dict[str, Any] = {"messages": messages}
        if has_image:
            if image_path:
                initial_state["image_path"] = image_path
            if image_base64:
                initial_state["image_base64"] = image_base64
            if image_media_type:
                initial_state["image_media_type"] = image_media_type
            user_provided_text = (user_input or "").strip()
            initial_state["user_provided_text"] = user_provided_text
            initial_state["input_mode"] = (
                "image_text" if user_provided_text else "image"
            )

        if concept_state:
            for key in _CONCEPT_STATE_KEYS:
                if key in concept_state:
                    initial_state[key] = concept_state[key]

        final_state = self.graph.invoke(initial_state)

        return {
            "response": self._build_response_text(final_state),
            "search_results": final_state.get("search_results", []),
            "intent": final_state.get("intent", ""),
            "search_query": final_state.get("search_query", ""),
            "input_mode": final_state.get("input_mode", "text"),
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
