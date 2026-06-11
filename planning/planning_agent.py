# planning/planning_agent.py
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from planning.area_recommender import recommend_area_plan
from planning.pending_state import (
    PendingAction,
    clear_pending,
    is_pending,
    normalize_pending_action,
    set_pending,
)
from reference_agent.utils.message_content import extract_user_text


def has_recommendation_inputs(state: Dict[str, Any]) -> bool:
    """대지 분석·법규 필드가 추천 상한 보정까지 가능한 수준인지 판별."""
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
    pending_action: PendingAction
    allow_abnormal_area: bool
    proceed_without_site_analysis: bool


class PlanningAgent:
    """검증 + 면적 의사결정 + 면적 추천을 담당하는 내부 LangGraph 에이전트.

    세부 공간 면적의 자연어 파싱은 담당하지 않습니다.
    직접 입력이 필요하면 ``pending_action=manual_area_input`` 만 세팅하고,
    다음 사용자 턴은 orchestrator ``router_node`` 가 ``extract_requirements`` 로 보냅니다.
    """

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
            "pending_action": normalize_pending_action(state),
            "allow_abnormal_area": bool(state.get("allow_abnormal_area", False)),
            "proceed_without_site_analysis": bool(
                state.get("proceed_without_site_analysis", False)
            ),
        }
        return self.app.invoke(initial_state)

    @staticmethod
    def _manual_area_input_prompt() -> str:
        return (
            "각 공간의 면적을 직접 입력해 주세요.\n"
            "예: 거실 24, 주방 12, 침실1 14, 침실2 12, 화장실 5"
        )

    @staticmethod
    def _limited_site_area_mode_prompt() -> str:
        return (
            "세부 공간 면적이 비어 있습니다.\n\n"
            "대지 분석이 없거나 법규 정보가 부족해, 추천 시 전체 면적은 공간 구성 기준으로 추정됩니다. "
            "대지 분석을 완료하면 건축면적·법규 상한을 반영해 더 정확해집니다.\n\n"
            "원하시는 방식을 선택해 주세요.\n"
            "1) 대지 분석 진행\n"
            "2) 공간별 면적 직접 입력\n"
            "3) 추천값으로 계산\n\n"
            "답변 예: '대지 분석', '직접 입력', '추천값'"
        )

    def _area_mode_retry_message(self, state: PlanningState) -> str:
        if not self._has_recommendation_inputs(state):
            return (
                "진행 방식을 '대지 분석', '직접 입력', '추천값' 중 하나로 답해 주세요."
            )
        return "진행 방식을 '직접 입력' 또는 '추천값'으로 답해 주세요."

    # verification_node
    def verification_node(self, state: PlanningState) -> PlanningState:
        # 면적 입력 대기 중이면 파싱하지 않고 pending만 유지 (파싱은 extract_requirements)
        if is_pending(state, "manual_area_input"):
            # 직접 입력 루프 중 '추천값' 전환 요청은 추천 계산으로 빠져나간다.
            # 단, 질문/출처 문의는 전환이 아니라 설명 요청이므로 제외.
            manual_text = self._last_user_text(state)
            if (
                self._parse_area_mode(manual_text) == "recommend"
                and not self._is_question_or_source(manual_text)
            ):
                return {
                    **clear_pending(),
                    "next_step": "area_recommendation",
                    "proceed_without_site_analysis": not self._has_recommendation_inputs(
                        state
                    ),
                    "messages": [
                        AIMessage(content="추천값(기본값)으로 계산하여 반영하겠습니다.")
                    ],
                }
            return {
                "ready_for_design": False,
                "next_step": "end",
                **set_pending("manual_area_input"),
            }

        # 1) 이전 턴에서 의사결정 질문 중이었다면 먼저 답변 해석
        if is_pending(state, "area_abnormal_confirmation"):
            return self._handle_area_abnormal_answer(state)
        if is_pending(state, "area_decision"):
            return self._handle_area_decision_answer(state)
        if is_pending(state, "area_mode"):
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

        if missing:
            return {
                "ready_for_design": False,
                "missing_requirements": missing,
                "next_step": "end",
                "messages": [AIMessage(content=self._build_missing_message(missing))],
            }

        # 3) 세부 면적이 비어 있으면 대지 분석 유무와 관계없이 면적 설정 흐름으로 진행
        if self._has_missing_space_area(state):
            if not self._has_recommendation_inputs(state):
                return {
                    "ready_for_design": False,
                    "missing_requirements": ["세부 공간 면적"],
                    **set_pending("area_mode"),
                    "next_step": "end",
                    "messages": [
                        AIMessage(content=self._limited_site_area_mode_prompt())
                    ],
                }
            return {
                "ready_for_design": True,
                "missing_requirements": [],
                "next_step": "end",
                **set_pending("area_decision"),
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

        # 4) 면적 확정 후 대지 분석 확인 (직접입력·추천값으로 진행한 경우는 생략)
        if state.get("proceed_without_site_analysis"):
            return {
                "ready_for_design": True,
                "missing_requirements": [],
                "next_step": "build_design_payload",
                **clear_pending(),
            }

        site_missing: List[str] = []
        self._check_site_analysis(site_analysis, building_type, site_missing)
        if site_missing:
            return {
                "ready_for_design": False,
                "missing_requirements": site_missing,
                "next_step": "end",
                "messages": [
                    AIMessage(
                        content=(
                            "공간별 면적은 준비되었습니다.\n"
                            "도면 생성을 위해 대지 분석이 필요합니다. "
                            "분석할 주소나 지번을 알려주세요. (예: 역삼동 747)"
                        )
                    )
                ],
            }

        return {
            "ready_for_design": True,
            "missing_requirements": [],
            "next_step": "build_design_payload",
            **clear_pending(),
        }

    # area_recommend_node
    def area_recommend_node(self, state: PlanningState) -> PlanningState:
        result = recommend_area_plan(
            spaces=state.get("spaces", []),
            building_type=state.get("building_type"),
            site_analysis=state.get("site_analysis"),
            allow_abnormal=bool(state.get("allow_abnormal_area", False)),
        )

        # 비정상 입력 감지 시: 추천을 중단하고 사용자 확인을 요청 (pending 유지)
        if result.get("status") == "needs_confirmation":
            return {
                "area_recommendation_result": result,
                "ready_for_design": False,
                **set_pending("area_abnormal_confirmation"),
                "next_step": "end",
                "messages": [
                    AIMessage(content=result.get("message", "입력 면적 확인이 필요합니다."))
                ],
            }

        if result.get("status") != "success":
            return {
                "area_recommendation_result": result,
                **clear_pending(),
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
            **clear_pending(),
            "next_step": "build_design_payload",
            "messages": [
                AIMessage(content=self._build_area_reco_message(result))
            ],
        }

    @staticmethod
    def _build_area_reco_message(result: Dict[str, Any]) -> str:
        """면적 추천 결과의 explanation을 사용자용 안내 문구로 구성한다."""
        base = "추천값(기본값)으로 세부 면적을 계산해 반영했습니다."
        explanation = result.get("explanation") or {}

        lines: List[str] = [base]

        summary = explanation.get("summary")
        if summary:
            lines.append("")
            lines.append(summary)

        warnings = explanation.get("warnings") or []
        if warnings:
            lines.append("")
            lines.append("확인이 필요한 사항:")
            lines.extend(f"- {warning}" for warning in warnings)

        return "\n".join(lines)

    def _route_after_verification_node(self, state: PlanningState) -> str:
        return state.get("next_step", "end")

    def _handle_area_abnormal_answer(self, state: PlanningState) -> PlanningState:
        user_text = self._last_user_text(state)
        decision = self._parse_yes_no(user_text)

        # 값이 맞다고 확인 → sanity check를 건너뛰고 입력값 그대로 추천 재진행
        if decision == "yes":
            return {
                **clear_pending(),
                "allow_abnormal_area": True,
                "next_step": "area_recommendation",
                "messages": [
                    AIMessage(content="입력값을 그대로 반영해 추천을 진행하겠습니다.")
                ],
            }

        # 오기입 → 직접 재입력 요청
        if decision == "no":
            return {
                "ready_for_design": False,
                **set_pending("manual_area_input"),
                "next_step": "end",
                "messages": [
                    AIMessage(
                        content=(
                            "알겠습니다. 면적을 다시 입력해 주세요.\n"
                            + self._manual_area_input_prompt()
                        )
                    )
                ],
            }

        return {
            **set_pending("area_abnormal_confirmation"),
            "next_step": "end",
            "messages": [
                AIMessage(
                    content=(
                        "입력하신 면적이 맞는지 확인해 주세요.\n"
                        "- 네: 입력값 그대로 진행\n"
                        "- 아니오: 면적 다시 입력"
                    )
                )
            ],
        }

    def _handle_area_decision_answer(self, state: PlanningState) -> PlanningState:
        user_text = self._last_user_text(state)
        decision = self._parse_yes_no(user_text)

        if decision == "no":
            return {
                **clear_pending(),
                "next_step": "area_recommendation",
                "messages": [
                    AIMessage(content="추천값(기본값)으로 계산하여 반영하겠습니다.")
                ],
            }
        if decision == "yes":
            return {
                **set_pending("area_mode"),
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
            **set_pending("area_decision"),
            "next_step": "end",
            "messages": [
                AIMessage(content="네/아니오로 답해 주세요. 구체적인 면적을 설정하시겠습니까?")
            ],
        }

    def _handle_area_mode_answer(self, state: PlanningState) -> PlanningState:
        user_text = self._last_user_text(state)
        limited_site = not self._has_recommendation_inputs(state)
        mode = self._parse_area_mode(user_text, limited_site=limited_site)

        if mode == "site_analysis":
            return {
                **clear_pending(),
                "proceed_without_site_analysis": False,
                "next_step": "end",
                "messages": [
                    AIMessage(
                        content=(
                            "대지 분석을 진행하겠습니다. "
                            "분석할 주소나 지번을 알려주세요. (예: 역삼동 747)"
                        )
                    )
                ],
            }
        if mode == "recommend":
            return {
                **clear_pending(),
                "proceed_without_site_analysis": limited_site,
                "next_step": "area_recommendation",
                "messages": [AIMessage(content="추천값을 계산해 반영하겠습니다.")],
            }
        if mode == "manual":
            return {
                **set_pending("manual_area_input"),
                "proceed_without_site_analysis": limited_site,
                "next_step": "end",
                "messages": [
                    AIMessage(content=self._manual_area_input_prompt())
                ],
            }

        return {
            **set_pending("area_mode"),
            "next_step": "end",
            "messages": [
                AIMessage(content=self._area_mode_retry_message(state))
            ],
        }

    def _last_user_text(self, state: PlanningState) -> str:
        messages = state.get("messages", []) or []
        if not messages:
            return ""
        return extract_user_text(messages[-1].content)

    def _parse_yes_no(self, text: str) -> Optional[Literal["yes", "no"]]:
        normalized = text.lower()
        yes_tokens = ["네", "예", "응", "ㅇㅇ", "yes", "y"]
        no_tokens = ["아니", "아니오", "no", "n", "괜찮", "필요없"]
        if any(token in normalized for token in [t.lower() for t in yes_tokens]):
            return "yes"
        if any(token in normalized for token in [t.lower() for t in no_tokens]):
            return "no"
        return None

    @staticmethod
    def _is_question_or_source(text: str) -> bool:
        raw = text or ""
        if "?" in raw:
            return True
        return any(marker in raw for marker in ("출처", "기준", "어디서", "왜"))

    def _parse_area_mode(
        self,
        text: str,
        *,
        limited_site: bool = False,
    ) -> Optional[Literal["manual", "recommend", "site_analysis"]]:
        normalized = text.lower().replace(" ", "")
        site_tokens = ["대지분석", "대지조사", "siteanalysis", "siteagent"]
        manual_tokens = ["직접입력", "수동입력", "직접", "manual"]
        recommend_tokens = ["추천값", "추천", "기본값", "recommend"]

        if limited_site:
            if normalized == "1":
                return "site_analysis"
            if normalized == "2":
                return "manual"
            if normalized == "3":
                return "recommend"
        else:
            if normalized == "1":
                return "manual"
            if normalized == "2":
                return "recommend"

        if any(token in normalized for token in site_tokens) or normalized == "대지":
            return "site_analysis"
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
        return has_recommendation_inputs(state)

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
