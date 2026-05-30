from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple


# ------------------------------------------------------------
# 유틸 함수
# ------------------------------------------------------------

def _clamp(value: float, min_value: float, max_value: float) -> float:
    """
    value가 min_value보다 작으면 min_value를 반환하고,
    max_value보다 크면 max_value를 반환하여 값의 범위를 제한한다.
    """
    return max(min_value, min(max_value, value))


def _parse_percent(value: Any) -> Optional[float]:
    """
    공공데이터에서 가져온 건폐율/용적률 값을 숫자(float)로 변환한다.
    예: "60%" -> 60.0, "200" -> 200.0
    변환이 불가능하거나 0 이하이면 None을 반환한다.
    """
    if value is None:
        return None

    # 이미 숫자 타입이면 바로 양수 여부만 확인
    if isinstance(value, (int, float)):
        if float(value) <= 0:
            return None
        return float(value)

    # 문자열인 경우 % 기호를 제거한 뒤 float으로 변환
    text = str(value).strip().replace("%", "")
    try:
        parsed = float(text)
        return parsed if parsed > 0 else None
    except Exception:
        return None


# ------------------------------------------------------------
# 대지 분석 결과에서 면적/법규 관련 정보 추출
# ------------------------------------------------------------

def _extract_site_context(site_analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Site Agent의 분석 결과에서 면적 추천에 필요한 핵심 정보를 추출한다.

    추출 대상:
    - 대지면적
    - 건축면적
    - 연면적
    - 전용면적
    - 공용면적
    - 주용도
    - 용도지역
    - 건폐율
    - 용적률
    """
    root = site_analysis or {}

    # raw_site_output 내부에 공공데이터 기반 상세 정보가 들어있을 수 있음
    raw = root.get("raw_site_output") or {}

    # 건축물 식별/법규 관련 정보
    identifiers = raw.get("building_identifiers") or {}

    # diffusion_output은 생성 모델에 넘기기 위해 정리된 면적 정보일 가능성이 높음
    diffusion = raw.get("diffusion_output") or root.get("diffusion_output") or {}

    return {
        "site_area_m2": diffusion.get("site_area_m2"),
        "building_area_m2": diffusion.get("building_area_m2"),
        "floor_area_m2": diffusion.get("floor_area_m2"),
        "private_area_m2": diffusion.get("private_area_m2"),
        "common_area_m2": diffusion.get("common_area_m2"),
        "main_purpose": identifiers.get("main_purpose"),
        "legal_zone": identifiers.get("legal_zone"),
        "bc_rat": _parse_percent(identifiers.get("bc_rat")),  # 건폐율
        "vl_rat": _parse_percent(identifiers.get("vl_rat")),  # 용적률
    }


# ------------------------------------------------------------
# 가구 유형 추정
# ------------------------------------------------------------

def _household_profile(spaces: List[Dict[str, Any]]) -> str:
    """
    입력된 공간 목록에서 bedroom 개수를 기준으로 가구 유형을 추정한다.

    bedroom 0~1개: 1~2인 가구
    bedroom 2개: 소가족
    bedroom 3개 이상: 가족 이상
    """
    bedroom_count = sum(1 for s in spaces if s.get("room_type") == "bedroom")

    if bedroom_count <= 1:
        return "one_or_two_person"
    if bedroom_count == 2:
        return "small_family"
    return "family_plus"


# ------------------------------------------------------------
# 공간별 기본 가중치 설정
# ------------------------------------------------------------

def _program_base_weights(
    building_type: Optional[str],
    household_profile: str
) -> Dict[str, float]:
    """
    건물 유형과 가구 유형에 따라 공간별 기본 면적 비중을 설정한다.

    이 가중치는 총면적을 각 공간에 배분할 때 사용된다.
    예를 들어 living_room의 가중치가 높으면 거실에 더 많은 면적이 배정된다.
    """

    # 공동주택의 경우 상대적으로 공용/전용 효율을 고려한 비중을 사용
    if building_type == "multi_family":
        base = {
            "living_room": 1.6,
            "kitchen": 1.1,
            "bedroom": 1.6,
            "bathroom": 0.8,
            "entrance": 0.5,
            "dining_room": 0.8,
            "study_room": 0.8,
            "storage": 0.6,
            "balcony": 0.5,
            "corridor": 0.5,
            "unknown": 0.7,
            "outside": 0.0,
        }

    # 단독주택 또는 기타 유형의 경우 거실/주방/식당 비중을 조금 더 크게 둠
    else:
        base = {
            "living_room": 1.9,
            "kitchen": 1.3,
            "bedroom": 1.5,
            "bathroom": 0.8,
            "entrance": 0.6,
            "dining_room": 1.0,
            "study_room": 0.9,
            "storage": 0.6,
            "balcony": 0.6,
            "corridor": 0.5,
            "unknown": 0.7,
            "outside": 0.0,
        }

    # 소가족인 경우 침실, 욕실, 수납공간의 비중을 소폭 증가시킴
    if household_profile == "small_family":
        base["bedroom"] += 0.2
        base["bathroom"] += 0.1
        base["storage"] += 0.1

    # 가족 규모가 더 큰 경우 침실, 욕실, 수납, 서재 비중을 추가로 증가시킴
    elif household_profile == "family_plus":
        base["bedroom"] += 0.4
        base["bathroom"] += 0.2
        base["storage"] += 0.2
        base["study_room"] += 0.1

    return base


# ------------------------------------------------------------
# 용도지역/주용도 기반 가중치 보정
# ------------------------------------------------------------

def _apply_zone_and_purpose_adjustments(
    weights: Dict[str, float],
    context: Dict[str, Any]
) -> None:
    """
    용도지역과 건축물 주용도에 따라 공간별 가중치를 보정한다.

    예:
    - 준주거/상업지역: 진입부, 수납 비중 증가
    - 주거지역: 거실, 침실 비중 증가
    - 공동주택: 복도 비중 증가
    - 단독주택: 식당 비중 증가

    weights를 직접 수정하는 함수이므로 반환값은 없다.
    """
    legal_zone = str(context.get("legal_zone") or "")
    main_purpose = str(context.get("main_purpose") or "")

    # 준주거/상업지역은 외부 접근성과 수납/완충공간 필요성을 고려함
    if "준주거" in legal_zone or "상업" in legal_zone:
        weights["living_room"] = weights.get("living_room", 1.0) * 0.95
        weights["storage"] = weights.get("storage", 0.5) * 1.10
        weights["entrance"] = weights.get("entrance", 0.5) * 1.05

    # 주거지역은 거주 중심 공간의 비중을 소폭 높임   
    if "주거" in legal_zone:
        weights["living_room"] = weights.get("living_room", 1.0) * 1.05
        weights["bedroom"] = weights.get("bedroom", 1.0) * 1.05

    # 공동주택은 공용 동선/복도 비중을 조금 더 고려
    if "공동주택" in main_purpose:
        weights["corridor"] = weights.get("corridor", 0.5) * 1.10

    # 단독주택은 식당/가족 활동 공간의 비중을 소폭 높임
    if "단독주택" in main_purpose:
        weights["dining_room"] = weights.get("dining_room", 1.0) * 1.05


# ------------------------------------------------------------
# 추천 총면적 추정
# ------------------------------------------------------------

def _infer_total_area(
    spaces: List[Dict[str, Any]],
    building_type: Optional[str],
    site_analysis: Optional[Dict[str, Any]],
) -> Tuple[float, str]:
    """
    추천 총면적을 추정한다.

    우선순위:
    1. Site Agent 분석 결과에 면적 정보가 있으면 해당 값을 우선 사용
    2. 사용자가 각 공간의 면적을 입력했다면 그 합계에 여유분 15%를 반영
    3. 정보가 부족하면 건물 유형과 실 개수 기반 휴리스틱으로 추정

    반환:
    - 추천 총면적
    - 어떤 기준으로 추정했는지 나타내는 source 문자열
    """
    context = _extract_site_context(site_analysis)

    # 단독주택은 대지 분석 결과의 건축면적을 우선 사용
    if building_type == "single_family" and context.get("building_area_m2"):
        return float(context["building_area_m2"]), "site_analysis_building_area"

    # 공동주택은 전용면적을 우선 사용
    if building_type == "multi_family" and context.get("private_area_m2"):
        return float(context["private_area_m2"]), "site_analysis_private_area"

    # 사용자가 일부 공간 면적을 직접 지정한 경우, 합계에 15% 여유면적을 더함
    specified_sum = 0.0
    for space in spaces:
        area = space.get("area")
        if isinstance(area, (int, float)) and area > 0:
            specified_sum += float(area)

    if specified_sum > 0:
        return round(specified_sum * 1.15, 1), "user_specified_area_sum"

    # 면적 정보가 없는 경우 실내 공간 개수를 기준으로 추정
    room_count = len([s for s in spaces if s.get("room_type") != "outside"])
    if room_count <= 0:
        room_count = 3

    # 단독주택 휴리스틱: 기본 65㎡에서 실 개수에 따라 증가, 50~180㎡ 범위 제한
    if building_type == "single_family":
        estimate = _clamp(65 + 18 * (room_count - 2), 50, 180)
        return float(round(estimate, 1)), "single_family_heuristic"

    # 공동주택 휴리스틱: 기본 45㎡에서 실 개수에 따라 증가, 35~120㎡ 범위 제한
    if building_type == "multi_family":
        estimate = _clamp(45 + 12 * (room_count - 2), 35, 120)
        return float(round(estimate, 1)), "multi_family_heuristic"

    # 건물 유형이 불명확한 경우 일반적인 기준으로 추정
    estimate = _clamp(55 + 15 * (room_count - 2), 40, 150)
    return float(round(estimate, 1)), "generic_heuristic"


# ------------------------------------------------------------
# 법규 기반 상한 보정
# ------------------------------------------------------------

def _regulatory_cap(
    total_area_m2: float,
    context: Dict[str, Any],
    building_type: Optional[str]
) -> Tuple[float, List[str]]:
    """
    대지면적, 건폐율, 용적률을 기반으로 추천 총면적의 상한을 보정한다.

    단독주택:
    - 건축면적 상한 = 대지면적 × 건폐율

    공동주택:
    - 연면적 상한 = 대지면적 × 용적률
    - 단, 추천면적은 연면적 상한의 75% 수준으로 보수적으로 제한

    반환:
    - 보정된 총면적
    - 보정이 발생했을 때 사용자에게 보여줄 설명 노트
    """
    notes: List[str] = []
    site_area = context.get("site_area_m2")
    bc_rat = context.get("bc_rat")
    vl_rat = context.get("vl_rat")

    # 대지면적이 없으면 법규 기반 보정을 수행할 수 없으므로 원래 값을 반환
    if not isinstance(site_area, (int, float)) or site_area <= 0:
        return total_area_m2, notes

    max_building_area = None
    max_floor_area = None

    # 건폐율 기반 최대 건축면적 계산함
    if isinstance(bc_rat, (int, float)) and bc_rat > 0:
        max_building_area = site_area * (bc_rat / 100.0)

    # 용적률 기반 최대 연면적 계산함
    if isinstance(vl_rat, (int, float)) and vl_rat > 0:
        max_floor_area = site_area * (vl_rat / 100.0)

    capped = total_area_m2

    # 단독주택은 건폐율 기반 건축면적 상한을 우선 고려
    if building_type == "single_family" and max_building_area:
        capped = min(capped, max_building_area)

    # 공동주택은 용적률 기반 연면적 상한의 일부만 추천 총면적으로 사용
    if building_type == "multi_family" and max_floor_area:
        capped = min(capped, max_floor_area * 0.75)

    # 건물 유형이 불명확한 경우 용적률 기반 상한을 일반적으로 적용
    if building_type not in {"single_family", "multi_family"} and max_floor_area:
        capped = min(capped, max_floor_area)

    # 실제로 면적이 줄어든 경우 사용자에게 설명할 노트를 추가함
    if capped < total_area_m2:
        notes.append("대지면적/건폐율/용적률 기반 상한을 반영해 추천 총면적을 보정했습니다.")

    return round(capped, 1), notes


# ------------------------------------------------------------
# 메인 함수: 공간별 추천 면적 산출
# ------------------------------------------------------------

def recommend_area_plan(
    spaces: List[Dict[str, Any]],
    building_type: Optional[str],
    site_analysis: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    사용자 입력 공간 목록, 건물 유형, 대지 분석 결과를 바탕으로
    추천 총면적과 공간별 권장 면적을 계산한다.

    최종 반환값:
    - status
    - recommended_total_area_m2
    - recommended_spaces
    - assumptions
    - rule_trace
    """

    # 외부공간(outside)은 면적 배분 대상에서 제외
    usable_spaces = [space for space in spaces if space.get("room_type") != "outside"]

    # 실내 공간 정보가 없으면 면적 추천을 수행할 수 없음
    if not usable_spaces:
        return {
            "status": "failed",
            "message": "면적 추천을 위해 최소 1개 이상의 실내 공간 정보가 필요합니다.",
        }

    # 대지 분석 결과에서 면적/법규 정보를 추출함
    context = _extract_site_context(site_analysis)

    # 추천 총면적을 추정하고, 추정 기준 source를 함께 받음
    total_area_m2, source = _infer_total_area(
        usable_spaces,
        building_type,
        site_analysis
    )

    # 대지면적/건폐율/용적률 기반으로 추천 총면적을 보정함
    total_area_m2, cap_notes = _regulatory_cap(
        total_area_m2,
        context,
        building_type
    )

    # bedroom 개수를 기준으로 가구 유형을 추정함
    household = _household_profile(usable_spaces)

    # 건물 유형과 가구 유형에 따른 기본 공간 가중치를 가져옴
    weights = _program_base_weights(building_type, household)

    # 용도지역/주용도 정보를 반영해 공간별 가중치를 보정함
    _apply_zone_and_purpose_adjustments(weights, context)

    # 입력된 공간들의 전체 가중치 합계를 계산함
    total_weight = 0.0
    for space in usable_spaces:
        total_weight += weights.get(space.get("room_type", "unknown"), 0.8)

    # 혹시 가중치 합이 0 이하가 되면 공간 개수 기준으로 나누도록 보정함
    if total_weight <= 0:
        total_weight = float(len(usable_spaces))

    # 각 공간별 추천 면적을 계산함
    recommended_spaces: List[Dict[str, Any]] = []
    for space in usable_spaces:
        room_type = space.get("room_type", "unknown")
        weight = weights.get(room_type, 0.8)
        ratio = weight / total_weight
        recommended_area = round(total_area_m2 * ratio, 1)

        recommended_spaces.append(
            {
                "id": space.get("id"),
                "room_type": room_type,
                "recommended_area_m2": recommended_area,
                "ratio": round(ratio, 3),
                "reason": (
                    f"{room_type}의 프로그램 비중({round(ratio * 100, 1)}%)을 반영했으며, "
                    f"{household} 가구 프로파일과 용도/지역 조정을 반영했습니다."
                ),
            }
        )

    # 추천 결과를 해석할 때 필요한 전제 조건을 정리
    assumptions = [
        "추천 면적은 초기 기획용 가이드이며, 실제 법규/구조/예산 검토 후 조정이 필요합니다.",
        "공간별 세부 치수, 채광, 동선, 가구 배치 요구가 확정되면 정확도가 높아집니다.",
        f"가구 프로파일 추정: {household}",
    ]

    # 추천 총면적을 어떤 기준으로 산정했는지 설명
    if source.startswith("site_analysis"):
        assumptions.append("대지 분석 결과의 면적 값을 우선 기준으로 사용했습니다.")
    elif source == "user_specified_area_sum":
        assumptions.append("사용자가 지정한 공간 면적 합계를 기준으로 공용/여유 면적을 반영했습니다.")
    else:
        assumptions.append("현재 정보가 제한되어 룸 개수 기반 휴리스틱을 사용했습니다.")

    # 법규 기반 상한 보정이 발생한 경우 설명을 추가함
    assumptions.extend(cap_notes)

    # 디버깅/설명 가능성을 위해 어떤 규칙이 적용되었는지 기록함
    rule_trace = {
        "source": source,
        "household_profile": household,
        "main_purpose": context.get("main_purpose"),
        "legal_zone": context.get("legal_zone"),
        "bc_rat": context.get("bc_rat"),
        "vl_rat": context.get("vl_rat"),
    }

    # 최종 추천 결과 반환함
    return {
        "status": "success",
        "recommended_total_area_m2": total_area_m2,
        "source": source,
        "recommended_spaces": recommended_spaces,
        "assumptions": assumptions,
        "rule_trace": rule_trace,
    }