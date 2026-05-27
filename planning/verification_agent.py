from __future__ import annotations

from typing import Any, Dict, List, Optional


class VerificationAgent:
    def verify(
        self,
        spaces: List[Dict[str, Any]],
        edges: List[List[str]],
        output_name: Optional[str],
        building_type: Optional[str],
        site_analysis: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        missing: List[str] = []

        self._check_spaces(spaces, missing)
        self._check_edges(spaces, edges, missing)
        self._check_output_name(output_name, missing)
        self._check_building_type(building_type, missing)
        self._check_site_analysis(site_analysis, building_type, missing)

        ready_for_design = len(missing) == 0

        if ready_for_design:
            message = "도면 생성 조건을 모두 확인했습니다."
        else:
            message = self._build_missing_message(missing)

        return {
            "ready_for_design": ready_for_design,
            "missing_requirements": missing,
            "message": message,
        }

    def _check_spaces(
        self,
        spaces: List[Dict[str, Any]],
        missing: List[str],
    ) -> None:
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
            missing.append(
                "공간 간 인접 관계가 없습니다. 예: 거실-주방 연결, 침실-화장실 인접 등."
            )
            return

        room_ids = {
            space.get("id")
            for space in spaces
            if space.get("id")
        }

        invalid_edges = []

        for edge in edges:
            if not isinstance(edge, list) or len(edge) != 2:
                invalid_edges.append(edge)
                continue

            source, target = edge

            if source not in room_ids or target not in room_ids:
                invalid_edges.append(edge)

        if invalid_edges:
            missing.append(
                f"존재하지 않는 공간을 참조하는 연결 관계가 있습니다: {invalid_edges}"
            )

    def _check_output_name(
        self,
        output_name: Optional[str],
        missing: List[str],
    ) -> None:
        if not output_name:
            missing.append("저장할 파일명이 필요합니다. 예: `파일명은 cabin_v1로 해줘`")

    def _check_building_type(
        self,
        building_type: Optional[str],
        missing: List[str],
    ) -> None:
        if not building_type:
            missing.append("건물 유형이 필요합니다. 단독주택인지 공동주택인지 알려주세요.")
            return

        if building_type not in ["single_family", "multi_family"]:
            missing.append(
                "현재 도면 생성은 주거 시설만 지원합니다. 단독주택 또는 공동주택 기준으로 입력해주세요."
            )
            return

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
            missing.append(
                "단독주택 도면 생성을 위해 건축면적(building_area_m2)이 필요합니다."
            )

        if building_type == "multi_family" and private_area_m2 is None:
            missing.append(
                "공동주택 도면 생성을 위해 전용면적(private_area_m2)이 필요합니다."
            )

    def _build_missing_message(self, missing: List[str]) -> str:
        message = "도면 생성 전에 추가 정보가 필요합니다.\n\n"

        for idx, item in enumerate(missing, start=1):
            message += f"{idx}. {item}\n"

        message += "\n부족한 정보를 알려주시면 다시 도면 생성 조건을 확인하겠습니다."
        return message