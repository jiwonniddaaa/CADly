from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from planning.area_recommender import recommend_area_plan


class PlanningState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    spaces: List[Dict[str, Any]]
    edges: List[List[str]]
    output_name: Optional[str]
    building_type: Optional[str]
    site_analysis: Optional[Dict[str, Any]]
    missing_requirements: List[str]
    ready_for_design: bool
    area_recommendation_result: Optional[Dict[str, Any]]
    next_step: Literal["end", "area_recommendation", "build_design_payload"]
    area_decision_pending: bool
    area_mode_pending: bool
    awaiting_manual_area_input: bool


class PlanningAgent:
    """검증 + 면적 의사결정 + 면적 추천을 담당하는 내부 LangGraph 에이전트."""

    def __init__(self) -> None:
        graph = StateGraph(PlanningState)
        graph.add_node("verification_node", self.verification_node)
        graph.add_node("area_recommend_node", self.area_recommend_node)
        graph.add_edge(START, "verification_node")
        graph.add_conditional_edges(
            "verification_node",
            self._route_after_verification_node,
            {
                "area_recommendation": "area_recommend_node",
                "build_design_payload": END,
                "end": END,
            },
        )
        graph.add_edge("area_recommend_node", END)
        self.app = graph.compile()

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        initial_state: PlanningState = {
            "messages": state.get("messages", []),
            "spaces": state.get("spaces", []),
            "edges": state.get("edges", []),
            "output_name": state.get("output_name"),
            "building_type": state.get("building_type"),
            "site_analysis": state.get("site_analysis"),
            "area_decision_pending": state.get("area_decision_pending", False),
            "area_mode_pending": state.get("area_mode_pending", False),
            "awaiting_manual_area_input": state.get("awaiting_manual_area_input", False),
        }
        return self.app.invoke(initial_state)

    # verification_node
    def verification_node(self, state: PlanningState) -> PlanningState:
        # 1) 이전 턴에서 의사결정 질문 중이었다면 먼저 답변 해석
        if state.get("area_decision_pending"):
            return self._handle_area_decision_answer(state)
        if state.get("area_mode_pending"):
            return self._handle_area_mode_answer(state)

        # 2) 일반 검증 수행
        spaces = state.get("spaces", [])
        edges = state.get("edges", [])
        output_name = state.get("output_name")
        building_type = state.get("building_type")
        site_analysis = state.get("site_analysis")

        missing: List[str] = []
        self._check_spaces(spaces, missing)
        self._check_edges(spaces, edges, missing)
        self._check_output_name(output_name, missing)
        self._check_building_type(building_type, missing)
        self._check_site_analysis(site_analysis, building_type, missing)

        ready_for_design = len(missing) == 0
        if not ready_for_design:
            return {
                "ready_for_design": False,
                "missing_requirements": missing,
                "next_step": "end",
                "messages": [AIMessage(content=self._build_missing_message(missing))],
            }

        # 3) 세부 면적이 비어있는 경우에만 사용자 의사 질문
        if self._has_missing_space_area(state):
            if not self._has_recommendation_inputs(state):
                return {
                    "ready_for_design": False,
                    "missing_requirements": ["세부 공간 면적"],
                    "next_step": "end",
                    "messages": [
                        AIMessage(
                            content=(
                                "세부 공간 면적이 비어 있지만 추천 계산에 필요한 대지/법규 정보가 부족합니다.\n"
                                "각 공간의 면적을 직접 입력해 주세요."
                            )
                        )
                    ],
                }
            return {
                "ready_for_design": True,
                "missing_requirements": [],
                "next_step": "end",
                "area_decision_pending": True,
                "area_mode_pending": False,
                "awaiting_manual_area_input": False,
                "messages": [
                    AIMessage(
                        content=(
                            "세부 공간 면적이 비어 있습니다. 구체적인 면적을 설정하시겠습니까? (네/아니오)\n"
                            "- 네: 직접 입력 또는 추천값 중 선택\n"
                            "- 아니오: 추천값(기본값)으로 계산해 반영"
                        )
                    )
                ],
            }

        # 4) 면적이 모두 있으면 바로 다음 단계로
        return {
            "ready_for_design": True,
            "missing_requirements": [],
            "next_step": "build_design_payload",
        }

    # area_recommend_node
    def area_recommend_node(self, state: PlanningState) -> PlanningState:
        result = recommend_area_plan(
            spaces=state.get("spaces", []),
            building_type=state.get("building_type"),
            site_analysis=state.get("site_analysis"),
        )

        if result.get("status") != "success":
            return {
                "area_recommendation_result": result,
                "next_step": "end",
                "messages": [
                    AIMessage(content=result.get("message", "면적 추천을 생성하지 못했습니다."))
                ],
            }

        current_spaces = state.get("spaces", []) or []
        reco_by_id = {
            item.get("id"): item.get("recommended_area_m2")
            for item in result.get("recommended_spaces", [])
            if item.get("id")
        }
        updated_spaces = []
        for space in current_spaces:
            next_space = dict(space)
            if next_space.get("id") in reco_by_id:
                area = next_space.get("area")
                if area is None or (isinstance(area, (int, float)) and area <= 0):
                    next_space["area"] = reco_by_id[next_space["id"]]
            updated_spaces.append(next_space)

        return {
            "area_recommendation_result": result,
            "spaces": updated_spaces,
            "area_decision_pending": False,
            "area_mode_pending": False,
            "awaiting_manual_area_input": False,
            "next_step": "build_design_payload",
            "messages": [AIMessage(content="추천값(기본값)으로 세부 면적을 계산해 반영했습니다.")],
        }

    def _route_after_verification_node(self, state: PlanningState) -> str:
        return state.get("next_step", "end")

    def _handle_area_decision_answer(self, state: PlanningState) -> PlanningState:
        user_text = self._last_user_text(state)
        decision = self._parse_yes_no(user_text)

        if decision == "no":
            # 아니오: 바로 추천값 반영
            return {
                "area_decision_pending": False,
                "area_mode_pending": False,
                "awaiting_manual_area_input": False,
                "next_step": "area_recommendation",
                "messages": [
                    AIMessage(content="추천값(기본값)으로 계산하여 반영하겠습니다.")
                ],
            }
        if decision == "yes":
            # 네: 직접 입력 또는 추천 선택
            return {
                "area_decision_pending": False,
                "area_mode_pending": True,
                "awaiting_manual_area_input": False,
                "next_step": "end",
                "messages": [
                    AIMessage(
                        content=(
                            "좋습니다. 진행 방식을 선택해 주세요.\n"
                            "1) 직접 입력\n"
                            "2) 추천값 사용\n"
                            "답변 예: '직접 입력' 또는 '추천값'"
                        )
                    )
                ],
            }

        return {
            "area_decision_pending": True,
            "awaiting_manual_area_input": False,
            "next_step": "end",
            "messages": [
                AIMessage(content="네/아니오로 답해 주세요. 구체적인 면적을 설정하시겠습니까?")
            ],
        }

    def _handle_area_mode_answer(self, state: PlanningState) -> PlanningState:
        user_text = self._last_user_text(state)
        mode = self._parse_area_mode(user_text)

        if mode == "recommend":
            return {
                "area_mode_pending": False,
                "awaiting_manual_area_input": False,
                "next_step": "area_recommendation",
                "messages": [AIMessage(content="추천값을 계산해 반영하겠습니다.")],
            }
        if mode == "manual":
            return {
                "area_mode_pending": False,
                "awaiting_manual_area_input": True,
                "next_step": "end",
                "messages": [
                    AIMessage(
                        content=(
                            "각 공간의 면적을 직접 입력해 주세요.\n"
                            "예: 거실 24, 주방 12, 침실1 14, 침실2 12, 화장실 5"
                        )
                    )
                ],
            }

        return {
            "area_mode_pending": True,
            "awaiting_manual_area_input": False,
            "next_step": "end",
            "messages": [
                AIMessage(content="진행 방식을 '직접 입력' 또는 '추천값'으로 답해 주세요.")
            ],
        }

    def _last_user_text(self, state: PlanningState) -> str:
        messages = state.get("messages", []) or []
        if not messages:
            return ""
        content = messages[-1].content
        return content if isinstance(content, str) else str(content)

    def _parse_yes_no(self, text: str) -> Optional[Literal["yes", "no"]]:
        normalized = text.lower()
        yes_tokens = ["네", "예", "응", "ㅇㅇ", "yes", "y"]
        no_tokens = ["아니", "아니오", "no", "n", "괜찮", "필요없"]
        if any(token in normalized for token in [t.lower() for t in yes_tokens]):
            return "yes"
        if any(token in normalized for token in [t.lower() for t in no_tokens]):
            return "no"
        return None

    def _parse_area_mode(self, text: str) -> Optional[Literal["manual", "recommend"]]:
        normalized = text.lower().replace(" ", "")
        manual_tokens = ["직접입력", "수동입력", "직접", "manual"]
        recommend_tokens = ["추천값", "추천", "기본값", "recommend"]
        if any(token in normalized for token in manual_tokens):
            return "manual"
        if any(token in normalized for token in recommend_tokens):
            return "recommend"
        return None

    def _has_missing_space_area(self, state: Dict[str, Any]) -> bool:
        spaces = state.get("spaces", []) or []
        for space in spaces:
            if space.get("room_type") == "outside":
                continue
            area = space.get("area")
            if area is None or (isinstance(area, (int, float)) and area <= 0):
                return True
        return False

    def _has_recommendation_inputs(self, state: Dict[str, Any]) -> bool:
        if state.get("building_type") not in {"single_family", "multi_family"}:
            return False

        site_analysis = state.get("site_analysis") or {}
        diffusion_output = site_analysis.get("diffusion_output") or {}
        raw = site_analysis.get("raw_site_output") or {}
        raw_diffusion = raw.get("diffusion_output") or {}
        identifiers = raw.get("building_identifiers") or {}

        required_diffusion = ["building_area_m2", "private_area_m2", "common_area_m2"]
        required_raw = ["site_area_m2", "building_area_m2", "private_area_m2", "common_area_m2"]
        required_identifiers = ["main_purpose", "legal_zone", "bc_rat", "vl_rat"]

        if not all(diffusion_output.get(key) is not None for key in required_diffusion):
            return False
        if not all(raw_diffusion.get(key) is not None for key in required_raw):
            return False
        if not all(identifiers.get(key) not in (None, "", "정보없음") for key in required_identifiers):
            return False
        return True

    def _check_spaces(self, spaces: List[Dict[str, Any]], missing: List[str]) -> None:
        if not spaces:
            missing.append("필요한 공간 목록이 아직 정리되지 않았습니다.")
            return
        for space in spaces:
            if not space.get("id"):
                missing.append("일부 공간에 id가 없습니다.")
            if not space.get("room_type"):
                missing.append("일부 공간에 room_type이 없습니다.")

    def _check_edges(
        self,
        spaces: List[Dict[str, Any]],
        edges: List[List[str]],
        missing: List[str],
    ) -> None:
        if not spaces:
            return
        if len(spaces) >= 2 and not edges:
            missing.append("공간 간 인접 관계가 없습니다. 예: 거실-주방 연결, 침실-화장실 인접 등.")
            return

        room_ids = {space.get("id") for space in spaces if space.get("id")}
        invalid_edges = []
        for edge in edges:
            if not isinstance(edge, list) or len(edge) != 2:
                invalid_edges.append(edge)
                continue
            source, target = edge
            if source not in room_ids or target not in room_ids:
                invalid_edges.append(edge)
        if invalid_edges:
            missing.append(f"존재하지 않는 공간을 참조하는 연결 관계가 있습니다: {invalid_edges}")

    def _check_output_name(self, output_name: Optional[str], missing: List[str]) -> None:
        if not output_name:
            missing.append("저장할 파일명이 필요합니다. 예: `파일명은 cabin_v1로 해줘`")

    def _check_building_type(self, building_type: Optional[str], missing: List[str]) -> None:
        if not building_type:
            missing.append("건물 유형이 필요합니다. 단독주택인지 공동주택인지 알려주세요.")
            return
        if building_type not in ["single_family", "multi_family"]:
            missing.append(
                "현재 도면 생성은 주거 시설만 지원합니다. 단독주택 또는 공동주택 기준으로 입력해주세요."
            )

    def _check_site_analysis(
        self,
        site_analysis: Optional[Dict[str, Any]],
        building_type: Optional[str],
        missing: List[str],
    ) -> None:
        if building_type not in ["single_family", "multi_family"]:
            return
        if not site_analysis:
            missing.append("대지 분석 결과가 없습니다. 먼저 대지 분석을 진행해주세요.")
            return

        diffusion_output = site_analysis.get("diffusion_output") or {}
        if not diffusion_output:
            missing.append("대지 분석 결과에 도면 생성용 면적 정보가 없습니다.")
            return

        building_area_m2 = diffusion_output.get("building_area_m2")
        private_area_m2 = diffusion_output.get("private_area_m2")
        if building_type == "single_family" and building_area_m2 is None:
            missing.append("단독주택 도면 생성을 위해 건축면적(building_area_m2)이 필요합니다.")
        if building_type == "multi_family" and private_area_m2 is None:
            missing.append("공동주택 도면 생성을 위해 전용면적(private_area_m2)이 필요합니다.")

    def _build_missing_message(self, missing: List[str]) -> str:
        message = "도면 생성 전에 추가 정보가 필요합니다.\n\n"
        for idx, item in enumerate(missing, start=1):
            message += f"{idx}. {item}\n"
        message += "\n부족한 정보를 알려주시면 다시 도면 생성 조건을 확인하겠습니다."
        return message
