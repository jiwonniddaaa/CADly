from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _infer_total_area(
    spaces: List[Dict[str, Any]],
    building_type: Optional[str],
    site_analysis: Optional[Dict[str, Any]],
) -> Tuple[float, str]:
    diffusion_output = (site_analysis or {}).get("diffusion_output") or {}
    if building_type == "single_family" and diffusion_output.get("building_area_m2"):
        return float(diffusion_output["building_area_m2"]), "site_analysis_building_area"
    if building_type == "multi_family" and diffusion_output.get("private_area_m2"):
        return float(diffusion_output["private_area_m2"]), "site_analysis_private_area"

    specified_sum = 0.0
    for space in spaces:
        area = space.get("area")
        if isinstance(area, (int, float)) and area > 0:
            specified_sum += float(area)
    if specified_sum > 0:
        return round(specified_sum * 1.15, 1), "user_specified_area_sum"

    room_count = len([s for s in spaces if s.get("room_type") != "outside"])
    if room_count <= 0:
        room_count = 3

    if building_type == "single_family":
        estimate = _clamp(65 + 18 * (room_count - 2), 50, 180)
        return float(round(estimate, 1)), "single_family_heuristic"
    if building_type == "multi_family":
        estimate = _clamp(45 + 12 * (room_count - 2), 35, 120)
        return float(round(estimate, 1)), "multi_family_heuristic"

    estimate = _clamp(55 + 15 * (room_count - 2), 40, 150)
    return float(round(estimate, 1)), "generic_heuristic"


def _room_weight(room_type: str) -> float:
    weights = {
        "living_room": 1.9,
        "kitchen": 1.3,
        "bedroom": 1.6,
        "bathroom": 0.7,
        "entrance": 0.5,
        "dining_room": 1.0,
        "study_room": 0.9,
        "storage": 0.5,
        "balcony": 0.6,
        "corridor": 0.5,
        "unknown": 0.7,
        "outside": 0.0,
    }
    return weights.get(room_type, 0.8)


def recommend_area_plan(
    spaces: List[Dict[str, Any]],
    building_type: Optional[str],
    site_analysis: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    usable_spaces = [space for space in spaces if space.get("room_type") != "outside"]
    if not usable_spaces:
        return {
            "status": "failed",
            "message": "면적 추천을 위해 최소 1개 이상의 실내 공간 정보가 필요합니다.",
        }

    total_area_m2, source = _infer_total_area(usable_spaces, building_type, site_analysis)

    total_weight = 0.0
    for space in usable_spaces:
        total_weight += _room_weight(space.get("room_type", "unknown"))
    if total_weight <= 0:
        total_weight = float(len(usable_spaces))

    recommended_spaces: List[Dict[str, Any]] = []
    for space in usable_spaces:
        room_type = space.get("room_type", "unknown")
        weight = _room_weight(room_type)
        ratio = weight / total_weight
        recommended_area = round(total_area_m2 * ratio, 1)
        recommended_spaces.append(
            {
                "id": space.get("id"),
                "room_type": room_type,
                "recommended_area_m2": recommended_area,
                "ratio": round(ratio, 3),
                "reason": f"{room_type}의 일반적 면적 비중({round(ratio * 100, 1)}%)을 반영했습니다.",
            }
        )

    assumptions = [
        "추천 면적은 초기 기획용 가이드이며, 실제 법규/구조/예산 검토 후 조정이 필요합니다.",
        "공간별 세부 치수, 채광, 동선, 가구 배치 요구가 확정되면 정확도가 높아집니다.",
    ]
    if source.startswith("site_analysis"):
        assumptions.append("대지 분석 결과의 면적 값을 우선 기준으로 사용했습니다.")
    elif source == "user_specified_area_sum":
        assumptions.append("사용자가 지정한 공간 면적 합계를 기준으로 공용/여유 면적을 반영했습니다.")
    else:
        assumptions.append("현재 정보가 제한되어 룸 개수 기반 휴리스틱을 사용했습니다.")

    return {
        "status": "success",
        "recommended_total_area_m2": total_area_m2,
        "source": source,
        "recommended_spaces": recommended_spaces,
        "assumptions": assumptions,
    }
