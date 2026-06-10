from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple


# 공동주택 용적률 기반 연면적 상한에 곱하는 보정계수.
# 법정 상한(대지면적 × 용적률)이 아니라, 알고리즘 안전성을 위해 보수적으로
# 낮춘 "실효상한(Effective Limit)"을 정의하기 위한 값이다. (권장 범위 0.7~0.8)
MULTI_FAMILY_EFFECTIVE_LIMIT_FACTOR = 0.75


# 공간 유형별 (최소, 권장, 최대) 면적(㎡) 기준표.
# 일반적인 국내 주거 건축 관행을 바탕으로 한 초안 값이며,
# - 휴리스틱 총면적 추정(실 개수 대신 프로그램 합산)
# - 총면적 추정치의 clamp 경계(최소합~최대합)
# - 빈 공간 배분 시 하한 보정
# 에 공통으로 재사용된다.
# 동선/완충(복도, 진입)을 별도 grossing 계수 없이 표에 흡수해 둔다.
ROOM_AREA_TABLE: Dict[str, Tuple[float, float, float]] = {
    "living_room": (14.0, 22.0, 36.0),
    "kitchen": (6.0, 10.0, 16.0),
    "bedroom": (9.0, 13.0, 20.0),
    "bathroom": (3.5, 5.0, 8.0),
    "entrance": (2.5, 4.0, 7.0),
    "storage": (2.0, 4.0, 8.0),
    "dining_room": (6.0, 10.0, 16.0),
    "study": (6.0, 9.0, 14.0),
    "balcony": (2.0, 4.0, 8.0),
    "corridor": (2.0, 4.0, 8.0),
    "utility_room": (2.0, 4.0, 8.0),
    "unknown": (3.0, 6.0, 10.0),
}

# ROOM_AREA_TABLE 튜플 인덱스 의미.
_AREA_MIN_IDX = 0
_AREA_REC_IDX = 1
_AREA_MAX_IDX = 2

# 휴리스틱 추정 시 건물 유형별 면적 스케일.
# 공동주택 세대는 동일 구성이라도 단독주택보다 다소 작게 계획되는 경향을 반영한다.
BUILDING_TYPE_AREA_FACTOR: Dict[str, float] = {
    "single_family": 1.0,
    "multi_family": 0.9,
}

# 입력 면적이 공간 유형별 표준 최대치의 이 배수를 초과하면 비정상 입력으로 간주한다.
# (예: 욕실 8㎡ × 3.0 = 24㎡ 초과 입력은 오타 가능성이 높다고 판단)
ABNORMAL_AREA_MULTIPLIER = 3.0


# ------------------------------------------------------------
# 유틸 함수
# ------------------------------------------------------------

def _room_area_bounds(room_type: Optional[str]) -> Tuple[float, float, float]:
    """공간 유형의 (최소, 권장, 최대) 면적 기준을 반환한다. 미정의 유형은 unknown으로 대체."""
    return ROOM_AREA_TABLE.get(room_type or "unknown", ROOM_AREA_TABLE["unknown"])


def _sum_room_area(spaces: List[Dict[str, Any]], idx: int) -> float:
    """공간 목록에 대해 ROOM_AREA_TABLE의 특정 기준(min/rec/max) 면적을 합산한다."""
    return sum(_room_area_bounds(space.get("room_type")) [idx] for space in spaces)


def _program_area_bounds(
    spaces: List[Dict[str, Any]],
    building_type: Optional[str],
) -> Tuple[float, float, float]:
    """
    공간 구성(프로그램)에 기반한 (최소합, 권장합, 최대합) 면적을 계산한다.
    건물 유형 스케일을 반영하며, 휴리스틱 추정과 clamp 경계 계산에 함께 사용된다.
    """
    factor = BUILDING_TYPE_AREA_FACTOR.get(building_type or "", 1.0)
    min_sum = _sum_room_area(spaces, _AREA_MIN_IDX) * factor
    rec_sum = _sum_room_area(spaces, _AREA_REC_IDX) * factor
    max_sum = _sum_room_area(spaces, _AREA_MAX_IDX) * factor
    return round(min_sum, 1), round(rec_sum, 1), round(max_sum, 1)


def _detect_abnormal_inputs(spaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    입력 면적이 공간 유형별 표준 최대치(ROOM_AREA_TABLE max)의
    ABNORMAL_AREA_MULTIPLIER 배를 초과하면 비정상 입력 후보로 반환한다.
    오타(예: 4500㎡)나 단위 혼동을 추천 진행 전에 걸러내기 위함이다.
    """
    abnormal: List[Dict[str, Any]] = []
    for space in spaces:
        area = space.get("area")
        if isinstance(area, (int, float)) and area > 0:
            room_type = space.get("room_type", "unknown")
            room_max = _room_area_bounds(room_type)[_AREA_MAX_IDX]
            threshold = room_max * ABNORMAL_AREA_MULTIPLIER
            if float(area) > threshold:
                abnormal.append(
                    {
                        "id": space.get("id"),
                        "room_type": room_type,
                        "area": float(area),
                        "typical_max_m2": room_max,
                        "threshold_m2": round(threshold, 1),
                    }
                )
    return abnormal

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
    weights: Dict[str, float],
) -> Tuple[float, str]:
    """
    추천 총면적을 추정한다.

    우선순위:
    1. Site Agent 분석 결과에 면적 정보가 있으면 해당 값을 우선 사용
    2. 사용자가 일부 공간 면적을 입력했다면, 입력 공간이 전체에서 차지하는
       예상 비중(가중치 비율)을 역산해 총면적을 추정
    3. 정보가 부족하면 공간 유형별 권장 면적(ROOM_AREA_TABLE) 합으로 추정

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

    # 사용자가 일부 공간 면적을 직접 입력한 경우: 가중치 비율 역산으로 총면적을 추정한다.
    # 입력 공간이 전체에서 차지하는 예상 비중으로 나눈다.
    specified_spaces = [
        space for space in spaces
        if isinstance(space.get("area"), (int, float)) and space["area"] > 0
    ]
    specified_sum = sum(float(space["area"]) for space in specified_spaces)

    if specified_sum > 0:
        input_weight = sum(
            weights.get(space.get("room_type", "unknown"), 0.8)
            for space in specified_spaces
        )
        total_weight = sum(
            weights.get(space.get("room_type", "unknown"), 0.8) for space in spaces
        )

        if input_weight > 0 and total_weight > 0:
            input_ratio = input_weight / total_weight
            estimated_total = specified_sum / input_ratio
        else:
            estimated_total = specified_sum

        # 입력 공간은 실제 입력값으로 고정하고, 빈 공간만 테이블 기준으로 범위를 잡는다.
        # (전체 테이블 max 합으로 상한을 잡으면, 큰 값을 입력했을 때 부당하게 잘린다.)
        empty_spaces = [
            space for space in spaces
            if not (isinstance(space.get("area"), (int, float)) and space["area"] > 0)
        ]
        factor = BUILDING_TYPE_AREA_FACTOR.get(building_type or "", 1.0)
        empty_min = _sum_room_area(empty_spaces, _AREA_MIN_IDX) * factor
        empty_max = _sum_room_area(empty_spaces, _AREA_MAX_IDX) * factor
        lower = specified_sum + empty_min
        upper = specified_sum + empty_max
        estimated_total = _clamp(estimated_total, lower, upper)
        return round(estimated_total, 1), "user_specified_weighted_backcalc"

    # 면적 정보가 없는 경우, 공간 구성(프로그램)별 권장 면적의 합으로 추정한다.
    # 실 개수만 보던 기존 휴리스틱과 달리 공간 유형(침실/욕실 등)을 반영한다.
    indoor = [s for s in spaces if s.get("room_type") != "outside"]
    if not indoor:
        # 공간 정보가 전혀 없으면 unknown 3개 구성으로 가정해 최소한의 추정을 제공
        indoor = [{"room_type": "unknown"} for _ in range(3)]

    _, rec_sum, _ = _program_area_bounds(indoor, building_type)
    return float(round(rec_sum, 1)), "room_program_heuristic"


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
    - 법정 연면적 상한 = 대지면적 × 용적률
    - 단, 추천면적은 법정 상한이 아니라 보정계수를 곱한
      "실효상한(Effective Limit)" 수준으로 보수적으로 제한

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

    # 공동주택은 법정 연면적 상한이 아니라 보정계수를 곱한 실효상한을 사용
    if building_type == "multi_family" and max_floor_area:
        effective_limit = max_floor_area * MULTI_FAMILY_EFFECTIVE_LIMIT_FACTOR
        capped = min(capped, effective_limit)

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
    allow_abnormal: bool = False,
) -> Dict[str, Any]:
    """
    사용자 입력 공간 목록, 건물 유형, 대지 분석 결과를 바탕으로
    추천 총면적과 공간별 권장 면적을 계산한다.

    allow_abnormal:
        True이면 비정상 입력 sanity check를 건너뛴다.
        (사용자가 큰 입력값을 확인/승인한 뒤 재진행할 때 사용)

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

    # 비정상 입력(오타/단위 혼동 등)이 있으면 추천을 진행하지 않고 확인을 요청한다.
    # 단, 사용자가 이미 확인했다면(allow_abnormal) 입력값을 그대로 신뢰한다.
    abnormal_inputs = [] if allow_abnormal else _detect_abnormal_inputs(usable_spaces)
    if abnormal_inputs:
        detail_lines = "\n".join(
            f"- {item['room_type']}: 입력 {item['area']}㎡ "
            f"(일반적 최대 약 {item['typical_max_m2']}㎡)"
            for item in abnormal_inputs
        )
        return {
            "status": "needs_confirmation",
            "abnormal_inputs": abnormal_inputs,
            "message": (
                "입력하신 면적 중 일반적인 범위를 크게 벗어난 값이 있어 확인이 필요합니다.\n"
                f"{detail_lines}\n\n"
                "값이 맞다면 다시 알려주시고, 오기입이라면 수정해 주세요."
            ),
        }

    # 대지 분석 결과에서 면적/법규 정보를 추출함
    context = _extract_site_context(site_analysis)

    # 가중치는 총면적 추정(가중치 역산)에도 쓰이므로 먼저 계산한다.
    # bedroom 개수를 기준으로 가구 유형을 추정함
    household = _household_profile(usable_spaces)

    # 건물 유형과 가구 유형에 따른 기본 공간 가중치를 가져옴
    weights = _program_base_weights(building_type, household)

    # 용도지역/주용도 정보를 반영해 공간별 가중치를 보정함
    _apply_zone_and_purpose_adjustments(weights, context)

    # 추천 총면적을 추정하고, 추정 기준 source를 함께 받음 (가중치 역산 포함)
    total_area_m2, source = _infer_total_area(
        usable_spaces,
        building_type,
        site_analysis,
        weights,
    )

    # 대지면적/건폐율/용적률 기반으로 추천 총면적을 보정함
    total_area_m2, cap_notes = _regulatory_cap(
        total_area_m2,
        context,
        building_type
    )

    # 면적이 이미 입력된 공간과 비어 있는 공간을 분리한다.
    # 입력값은 그대로 보존하고, 잔여 면적(remaining)을 빈 공간끼리만 배분한다.
    specified_spaces: List[Dict[str, Any]] = []
    empty_spaces: List[Dict[str, Any]] = []
    for space in usable_spaces:
        area = space.get("area")
        if isinstance(area, (int, float)) and area > 0:
            specified_spaces.append(space)
        else:
            empty_spaces.append(space)

    specified_sum = sum(float(space["area"]) for space in specified_spaces)

    # 빈 공간이 ROOM_AREA_TABLE 기준으로 필요로 하는 최소 면적 합(하한).
    factor = BUILDING_TYPE_AREA_FACTOR.get(building_type or "", 1.0)
    empty_min_sum = round(_sum_room_area(empty_spaces, _AREA_MIN_IDX) * factor, 1)

    # 빈 공간에 배분할 잔여 면적을 계산하고, 경계 상황을 보정한다.
    remaining_area = round(total_area_m2 - specified_sum, 1)
    distribution_notes: List[str] = []

    if empty_spaces and remaining_area < empty_min_sum:
        # 입력 면적이 추정 총면적에 근접/초과해 빈 공간 최소치를 못 채우는 경우
        remaining_area = empty_min_sum
        total_area_m2 = round(specified_sum + remaining_area, 1)
        distribution_notes.append(
            "입력 면적이 추정 총면적에 근접/초과하여, 빈 공간의 최소 면적을 "
            "확보하도록 총면적을 상향 조정했습니다."
        )
    elif not empty_spaces:
        # 모든 공간이 입력된 경우: 배분할 빈 공간이 없으므로 여유 버퍼는 의미가 없다.
        # 총면적을 입력합과 일치시켜 (총면적 == 공간 합) 일관성을 유지한다.
        remaining_area = 0.0
        total_area_m2 = round(specified_sum, 1)

    # 빈 공간 가중치 합 (0 이하 방어)
    empty_weight = sum(
        weights.get(space.get("room_type", "unknown"), 0.8) for space in empty_spaces
    )
    if empty_weight <= 0:
        empty_weight = float(len(empty_spaces)) if empty_spaces else 1.0

    # 각 빈 공간은 최소 면적을 보장하고, 그 위의 잉여분만 가중치 비율로 배분한다.
    leftover_area = max(0.0, round(remaining_area - empty_min_sum, 1))

    def _ratio_of(area_value: float) -> float:
        return round(area_value / total_area_m2, 3) if total_area_m2 > 0 else 0.0

    # 입력 순서를 보존하며 공간별 결과를 구성한다.
    recommended_spaces: List[Dict[str, Any]] = []
    for space in usable_spaces:
        room_type = space.get("room_type", "unknown")
        area = space.get("area")
        is_specified = isinstance(area, (int, float)) and area > 0

        if is_specified:
            recommended_area = round(float(area), 1)
            recommended_spaces.append(
                {
                    "id": space.get("id"),
                    "room_type": room_type,
                    "recommended_area_m2": recommended_area,
                    "ratio": _ratio_of(recommended_area),
                    "source": "user_input",
                    "reason": "사용자가 입력한 면적을 그대로 유지했습니다.",
                }
            )
            continue

        weight = weights.get(room_type, 0.8)
        share_ratio = weight / empty_weight
        room_min = round(_room_area_bounds(room_type)[_AREA_MIN_IDX] * factor, 1)
        recommended_area = round(room_min + leftover_area * share_ratio, 1)

        recommended_spaces.append(
            {
                "id": space.get("id"),
                "room_type": room_type,
                "recommended_area_m2": recommended_area,
                "ratio": _ratio_of(recommended_area),
                "source": "recommended",
                "reason": (
                    f"빈 공간 잔여 면적을 {room_type}의 프로그램 비중"
                    f"({round(share_ratio * 100, 1)}%)으로 배분하고 최소 면적을 보장했습니다."
                ),
            }
        )

    # 추천 결과를 해석할 때 필요한 전제 조건을 정리
    assumptions = [
        "추천 면적은 초기 기획용 가이드이며, 실제 법규/구조/예산 검토 후 조정이 필요합니다.",
        "공간별 세부 치수, 채광, 동선, 가구 배치 요구가 확정되면 정확도가 높아집니다.",
        f"가구 프로파일 추정: {household}",
    ]
    if specified_spaces:
        assumptions.append("입력된 공간 면적은 변경 없이 유지하고, 나머지 공간에만 잔여 면적을 배분했습니다.")
    assumptions.extend(distribution_notes)

    # 추천 총면적을 어떤 기준으로 산정했는지 설명
    if source.startswith("site_analysis"):
        assumptions.append("대지 분석 결과의 면적 값을 우선 기준으로 사용했습니다.")
    elif source == "user_specified_weighted_backcalc":
        assumptions.append("입력한 공간 면적이 전체에서 차지하는 예상 비중을 역산해 총면적을 추정했습니다.")
    else:
        assumptions.append("현재 정보가 제한되어 공간 유형별 권장 면적의 합으로 추정했습니다.")

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