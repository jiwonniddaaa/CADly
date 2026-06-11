from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage

from design.orchestrator import build_design_orchestrator
from CADly.agent.session_utils import (
    EPHEMERAL_STATE_KEYS,
    build_persisted_fields,
    get_last_ai_text,
    merge_session_blob,
    persist_upload_image,
    read_svg_content,
    split_session_blob,
)

_design_app = build_design_orchestrator()

_HANDOFF_SUCCESS_TAIL = "이제 도면 생성, 수정, CAD 연동 작업을 진행할 수 있습니다."
_DESIGN_FAILURE_STATUSES = frozenset(
    {"validation_failed", "save_failed", "sampling_failed", "error"}
)


def _is_design_failure(status: str) -> bool:
    return status in _DESIGN_FAILURE_STATUSES


def _failure_detail(result: Dict[str, Any]) -> str:
    errors = result.get("validation_errors") or []
    if errors:
        return str(errors[0]).strip()
    return (result.get("message") or "").strip()


def _compose_handoff_failure_response(handoff_text: str, result: Dict[str, Any]) -> str:
    detail = _failure_detail(result)
    failure_block = "다만 도면 파일 생성에 실패했습니다."
    if detail:
        failure_block = f"{failure_block}\n{detail}"

    if _HANDOFF_SUCCESS_TAIL in handoff_text:
        prefix = handoff_text.split(_HANDOFF_SUCCESS_TAIL, 1)[0].rstrip()
        return f"{prefix}\n{failure_block}"

    return f"{handoff_text.rstrip()}\n\n{failure_block}"


def _build_design_response_text(result: Dict[str, Any]) -> str:
    status = result.get("status", "")
    message = (result.get("message") or "").strip()
    svg_path = result.get("svg_path")
    dxf_path = result.get("dxf_path")

    if status == "completed" and svg_path:
        lines = ["도면 생성이 완료되었습니다."]
        if svg_path:
            lines.append(f"SVG: {svg_path}")
        if dxf_path:
            lines.append(f"DXF: {dxf_path}")
        return "\n".join(lines)

    if _is_design_failure(status):
        detail = _failure_detail(result)
        if detail:
            return f"도면 생성에 실패했습니다.\n{detail}"
        return "도면 생성에 실패했습니다."

    if message:
        return message

    return "설계 파이프라인을 실행했습니다."


def _resolve_design_response_text(
    messages: List[Any],
    result: Dict[str, Any],
) -> str:
    status = result.get("status", "")

    if _is_design_failure(status):
        handoff_text = get_last_ai_text(messages)
        if handoff_text and "설계 단계로 넘어갑니다" in handoff_text:
            return _compose_handoff_failure_response(handoff_text, result)
        return _build_design_response_text(result)

    design_text = _build_design_response_text(result)
    if status == "completed" and result.get("svg_path"):
        return design_text

    return get_last_ai_text(messages) or design_text


def _pick_first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _find_number_by_keys(data: Any, target_keys: set[str]) -> float | None:
    """
    dict/list 내부를 재귀적으로 탐색해서 target_keys에 해당하는 숫자 값을 찾는다.
    area_recommendation_result / design_payload 구조가 조금 달라도 대응하기 위함.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key in target_keys:
                number = _pick_first_number(value)
                if number is not None:
                    return number

        for value in data.values():
            found = _find_number_by_keys(value, target_keys)
            if found is not None:
                return found

    if isinstance(data, list):
        for item in data:
            found = _find_number_by_keys(item, target_keys)
            if found is not None:
                return found

    return None


def _sum_room_areas_from_graph(graph_data: Any) -> float | None:
    if not isinstance(graph_data, dict):
        return None

    rooms = graph_data.get("rooms")
    if not isinstance(rooms, list):
        return None

    total = 0.0
    found = False

    for room in rooms:
        if not isinstance(room, dict):
            continue

        area = _pick_first_number(
            room.get("area"),
            room.get("area_m2"),
            room.get("target_area"),
            room.get("targetArea"),
            room.get("sqm"),
            room.get("size"),
        )

        if area is not None and area > 0:
            total += area
            found = True

    return round(total, 1) if found else None


def _build_design_metrics(
    *,
    result: Dict[str, Any],
    design_state: Dict[str, Any],
    planning_fields: Dict[str, Any],
) -> Dict[str, Any]:
    result_metrics = result.get("metrics")

    existing_total_area = None
    existing_usable_area = None
    existing_space_efficiency = None

    if isinstance(result_metrics, dict):
        existing_total_area = _pick_first_number(
            result_metrics.get("total_area"),
            result_metrics.get("totalArea"),
            result_metrics.get("area"),
            result_metrics.get("building_area"),
            result_metrics.get("buildingArea"),
            result_metrics.get("gross_area"),
            result_metrics.get("grossArea"),
        )

        existing_usable_area = _pick_first_number(
            result_metrics.get("usable_area"),
            result_metrics.get("usableArea"),
        )

        existing_space_efficiency = _pick_first_number(
            result_metrics.get("space_efficiency"),
            result_metrics.get("spaceEfficiency"),
            result_metrics.get("space_ratio"),
            result_metrics.get("spaceRatio"),
            result_metrics.get("efficiency"),
        )

    graph_data = (
        result.get("graph_data")
        or design_state.get("graph_data")
        or planning_fields.get("graph_data")
        or {}
    )

    area_recommendation_result = (
        result.get("area_recommendation_result")
        or design_state.get("area_recommendation_result")
        or planning_fields.get("area_recommendation_result")
        or {}
    )

    design_payload = (
        result.get("design_payload")
        or design_state.get("design_payload")
        or planning_fields.get("design_payload")
        or {}
    )

    site_analysis = (
        result.get("site_analysis")
        or design_state.get("site_analysis")
        or planning_fields.get("site_analysis")
        or {}
    )

    requirements = (
        result.get("requirements")
        or design_state.get("requirements")
        or planning_fields.get("requirements")
        or {}
    )

    # 1. usable_area: 실제 방들의 면적 합계
    usable_area = (
        existing_usable_area
        or _pick_first_number(
            result.get("usable_area"),
            result.get("net_area"),
            design_state.get("usable_area"),
            design_state.get("net_area"),
            planning_fields.get("usable_area"),
            planning_fields.get("net_area"),
        )
    )

    if usable_area is None:
        usable_area = _sum_room_areas_from_graph(graph_data)

    # 2. total_area: planning/chat 단계에서 나온 전체 면적을 우선 사용
    total_area = (
        existing_total_area
        or _pick_first_number(
            result.get("total_area"),
            result.get("totalArea"),
            result.get("building_area"),
            result.get("buildingArea"),
            result.get("gross_area"),
            result.get("grossArea"),
            result.get("gross_floor_area"),
            result.get("grossFloorArea"),
            result.get("area"),

            design_state.get("total_area"),
            design_state.get("totalArea"),
            design_state.get("building_area"),
            design_state.get("buildingArea"),
            design_state.get("gross_area"),
            design_state.get("grossArea"),
            design_state.get("gross_floor_area"),
            design_state.get("grossFloorArea"),
            design_state.get("area"),

            planning_fields.get("total_area"),
            planning_fields.get("totalArea"),
            planning_fields.get("building_area"),
            planning_fields.get("buildingArea"),
            planning_fields.get("gross_area"),
            planning_fields.get("grossArea"),
            planning_fields.get("gross_floor_area"),
            planning_fields.get("grossFloorArea"),
            planning_fields.get("area"),
        )
    )

    # 3. 직접 못 찾으면 area_recommendation_result 내부에서 전체 면적 후보 찾기
    # 여기서는 generic "area"는 일부러 재귀 탐색하지 않음.
    # 방 하나의 area=20.0 같은 값을 total_area로 잘못 잡을 수 있기 때문.
    strong_total_area_keys = {
        "total_area",
        "totalArea",
        "recommended_total_area",
        "recommendedTotalArea",
        "recommended_area",
        "recommendedArea",
        "target_total_area",
        "targetTotalArea",
        "building_area",
        "buildingArea",
        "gross_area",
        "grossArea",
        "gross_floor_area",
        "grossFloorArea",
        "site_area",
        "siteArea",
    }

    if total_area is None:
        total_area = _find_number_by_keys(
            area_recommendation_result,
            strong_total_area_keys,
        )

    if total_area is None:
        total_area = _find_number_by_keys(
            design_payload,
            strong_total_area_keys,
        )

    if total_area is None:
        total_area = _find_number_by_keys(
            site_analysis,
            strong_total_area_keys,
        )

    if total_area is None:
        total_area = _find_number_by_keys(
            requirements,
            strong_total_area_keys,
        )

    # 4. space_efficiency: 없으면 계산
    space_efficiency = existing_space_efficiency or _pick_first_number(
        result.get("space_efficiency"),
        result.get("spaceEfficiency"),
        result.get("space_ratio"),
        result.get("spaceRatio"),
        result.get("efficiency"),

        design_state.get("space_efficiency"),
        design_state.get("spaceEfficiency"),
        design_state.get("space_ratio"),
        design_state.get("spaceRatio"),
        design_state.get("efficiency"),

        planning_fields.get("space_efficiency"),
        planning_fields.get("spaceEfficiency"),
        planning_fields.get("space_ratio"),
        planning_fields.get("spaceRatio"),
        planning_fields.get("efficiency"),
    )

    site_area = _find_site_area(
        result=result,
        design_state=design_state,
        planning_fields=planning_fields,
        site_analysis=site_analysis,
        area_recommendation_result=area_recommendation_result,
    )

    planned_area = total_area

    display_total_area = usable_area

    if space_efficiency is None and site_area and usable_area:
        space_efficiency = round((usable_area / site_area) * 100, 1)

    return {
        "total_area": display_total_area,
        "usable_area": usable_area,
        "site_area": site_area,
        "planned_area": planned_area,
        "space_efficiency": space_efficiency,
}

def _find_site_area(
    *,
    result: Dict[str, Any],
    design_state: Dict[str, Any],
    planning_fields: Dict[str, Any],
    site_analysis: Any,
    area_recommendation_result: Any,
) -> float | None:
    site_area = _pick_first_number(
        result.get("site_area"),
        result.get("siteArea"),
        result.get("land_area"),
        result.get("landArea"),
        result.get("lot_area"),
        result.get("lotArea"),
        result.get("parcel_area"),
        result.get("parcelArea"),

        design_state.get("site_area"),
        design_state.get("siteArea"),
        design_state.get("land_area"),
        design_state.get("landArea"),
        design_state.get("lot_area"),
        design_state.get("lotArea"),
        design_state.get("parcel_area"),
        design_state.get("parcelArea"),

        planning_fields.get("site_area"),
        planning_fields.get("siteArea"),
        planning_fields.get("land_area"),
        planning_fields.get("landArea"),
        planning_fields.get("lot_area"),
        planning_fields.get("lotArea"),
        planning_fields.get("parcel_area"),
        planning_fields.get("parcelArea"),
    )

    if site_area is not None:
        return site_area

    site_area_keys = {
        "site_area",
        "siteArea",
        "site_area_m2",
        "siteAreaM2",
        "land_area",
        "landArea",
        "land_area_m2",
        "landAreaM2",
        "lot_area",
        "lotArea",
        "lot_area_m2",
        "lotAreaM2",
        "parcel_area",
        "parcelArea",
        "parcel_area_m2",
        "parcelAreaM2",
        "대지면적",
    }

    site_area = _find_number_by_keys(site_analysis, site_area_keys)
    if site_area is not None:
        return site_area

    site_area = _find_number_by_keys(area_recommendation_result, site_area_keys)
    if site_area is not None:
        return site_area

    return None

async def run_design_chat(
    *,
    query: str = "",
    session_state: Optional[Dict[str, Any]] = None,
    image_path: Optional[str] = None,
    image_base64: Optional[str] = None,
    image_media_type: Optional[str] = None,
    append_user_message: bool = True,
) -> Dict[str, Any]:
    """Design 파이프라인 실행.

    HouseDiffusion 입력은 query가 아니라 design_state.graph_data(rooms/edges)입니다.
    query는 채팅 기록용이며, handoff 직후 자동 실행 시 append_user_message=False로 중복을 막습니다.
    """
    user_text = (query or "").strip()
    messages, _, design_state, planning_fields = split_session_blob(session_state)

    if not design_state.get("graph_data"):
        return {
            "response": "설계 데이터가 없습니다. 기획 단계에서 도면 생성을 먼저 확정해 주세요.",
            "search_results": [],
            "planning_state": session_state or {},
            "active_orchestrator": "planning",
            "route": "design",
            "agent_type": "design",
        }

    if append_user_message and user_text:
        messages = [*messages, HumanMessage(content=user_text)]

    resolved_image_path = image_path
    if image_base64 and not resolved_image_path:
        resolved_image_path = persist_upload_image(image_base64, image_media_type)

    invoke_state: Dict[str, Any] = {
        **design_state,
        "messages": messages,
        "user_input": user_text,
    }
    if resolved_image_path:
        invoke_state["image_path"] = resolved_image_path

    # 디버깅용
    print("\n========== DESIGN CHAT DEBUG ==========")
    print("design_state:", design_state)
    print("graph_data:", design_state.get("graph_data"))
    print("======================================\n")

    result = await _design_app.ainvoke(invoke_state)

    # 디버깅용
    print("\n========== DESIGN RESULT DEBUG ==========")
    print("status:", result.get("status"))
    print("message:", result.get("message"))
    print("svg_path:", result.get("svg_path"))
    print("dxf_path:", result.get("dxf_path"))
    print("errors:", result.get("validation_errors"))
    print("warnings:", result.get("verification_warnings"))
    print("========================================\n")

    persist_exclude = EPHEMERAL_STATE_KEYS | frozenset({"messages"})
    updated_design_state = build_persisted_fields(design_state, result, persist_exclude)

    result_messages = result.get("messages", [])
    if result_messages:
        messages = [*messages, *result_messages]

    response_text = _resolve_design_response_text(messages, result)
    if response_text and not any(isinstance(m, AIMessage) and m.content == response_text for m in messages):
        messages = [*messages, AIMessage(content=response_text)]

    planning_state = merge_session_blob(
        planning_fields,
        messages,
        "design",
        updated_design_state,
    )

    svg_content = read_svg_content(result.get("svg_path"))

    metrics = _build_design_metrics(
        result=result,
        design_state=updated_design_state,
        planning_fields=planning_fields,
    )

    print("metrics:", metrics)
    print("metric source graph_data:", updated_design_state.get("graph_data"))
    print("area_recommendation_result:", planning_fields.get("area_recommendation_result"))
    print("design_payload:", planning_fields.get("design_payload"))

    return {
        "response": response_text,
        "search_results": [],
        "references": [],
        "route": "design",
        "agent_type": "design",
        "planning_state": planning_state,
        "active_orchestrator": "design",
        "design_state": updated_design_state,
        "cad_svg_content": svg_content,
        "dxf_path": result.get("dxf_path"),
        "svg_path": result.get("svg_path"),
        "status": result.get("status"),
        "metrics": metrics,
    }