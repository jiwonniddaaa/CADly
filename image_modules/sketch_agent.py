from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, Tuple

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage

low_llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001"
)

high_llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929"
)

class SketchAgent:
    # 유틸리티 함수
    def _encode_image(self, image_path: str) -> Tuple[str, str]:
        path = Path(image_path)

        if not path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }

        media_type = mime_map.get(path.suffix.lower())

        if media_type is None:
            raise ValueError(f"지원하지 않는 이미지 형식입니다: {path.suffix}")

        image_data = base64.b64encode(path.read_bytes()).decode("utf-8")
        return image_data, media_type

    def _safe_json_loads(self, text: str) -> Dict[str, Any]:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except Exception:
            return {
                "status": "failed",
                "message": "JSON parsing failed",
                "raw_response": text,
            }

    # 노드 정의
    def analysis_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        손도면 이미지 분석 노드.
        이미지에서 보이는 공간/연결/문/창 등을 추출한다.
        """

        image_path = state.get("image_path")
        user_input = state.get("user_input", "")

        if not image_path:
            return {
                "status": "failed",
                "route": "unsupported_image",
                "final_answer": "손도면 이미지가 없습니다.",
            }

        try:
            image_data, media_type = self._encode_image(image_path)

            prompt = f"""
너는 CADly의 손도면 분석 전문가다.

목표:
손도면 이미지를 보고 실제로 보이는 공간 정보를 최대한 객관적으로 분석해라.

중요:
- 아직 CADly schema로 변환하지 마라.
- 이미지 관찰 결과만 정리해라.
- 확실하지 않은 내용은 uncertain_parts에 넣어라.
- 없는 정보를 지어내지 마라.

사용자 추가 요청:
{user_input}

반드시 JSON만 출력해라.

출력 형식:
{{
  "status": "success",
  "visible_spaces": [
    {{
      "raw_label": "거실",
      "interpreted_type": "living_room",
      "relative_position": "center",
      "approx_size": "large",
      "confidence": 0.0
    }}
  ],
  "visible_connections": [
    {{
      "from": "거실",
      "to": "주방",
      "relationship": "adjacent",
      "confidence": 0.0
    }}
  ],
  "visible_openings": [
    {{
      "type": "door",
      "connected_spaces": ["거실", "outside"],
      "confidence": 0.0
    }}
  ],
  "visible_windows": [],
  "overall_layout_description": "...",
  "uncertain_parts": []
}}
"""

            response = high_llm.invoke([
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                    ]
                )
            ])

            content = response.content
            analysis = self._safe_json_loads(content)

            if analysis.get("status") != "success":
                return {
                    "status": "failed",
                    "route": "unsupported_image",
                    "sketch_analysis": analysis,
                }

            return {
                "status": "sketch_analyzed",
                "route": "sketch_extract_node",
                "sketch_analysis": analysis,
            }

        except Exception as e:
            return {
                "status": "failed",
                "route": "unsupported_image",
                "final_answer": f"손도면 분석 중 오류 발생: {e}",
            }

    def extract_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        손도면 분석 결과를
        CADly schema로 정규화하는 노드.
        """

        sketch_analysis = state.get("sketch_analysis")
        user_input = state.get("user_input", "")

        if not sketch_analysis:
            return {
                "status": "failed",
                "route": "unsupported_image",
                "final_answer": "손도면 분석 결과가 없습니다.",
            }

        try:
            prompt = f"""
너는 CADly의 schema normalization 전문가다.

목표:
손도면 분석 결과를 CADly 표준 schema로 변환해라.

CADly schema:
{{
  "spaces": [
    {{
      "id": "living_room1",
      "room_type": "living_room",
      "area": null,
      "notes": "..."
    }}
  ],
  "edges": [
    ["living_room1", "outside"]
  ],
  "output_name": null,
  "building_type": null
}}

규칙:
- spaces에는 실내 공간만 넣어라.
- outside는 edges에서만 사용해라.
- area를 알 수 없으면 null.
- room_type은 아래 중 하나만:
  living_room
  kitchen
  bedroom
  bathroom
  entrance
  dining_room
  storage
  balcony
  corridor
  unknown

사용자 요청:
{user_input}

손도면 분석 결과:
{json.dumps(sketch_analysis, ensure_ascii=False, indent=2)}

반드시 JSON만 출력해라.
"""

            response = low_llm.invoke([
                HumanMessage(content=prompt)
            ])
        
            content = response.content
            cadly_schema = self._safe_json_loads(content)

            message = self._generate_user_response(
                user_input=user_input,
                sketch_analysis=sketch_analysis,
            )

            return {
                "status": "sketch_extracted",
                "sketch_result": cadly_schema,
                "final_answer": message,
                "messages": [
                AIMessage(content=message)
            ],
            }

        except Exception as e:
            return {
                "status": "failed",
                "route": "unsupported_image",
                "final_answer": f"CADly schema 변환 중 오류 발생: {e}",
            }
        
    def _generate_user_response(
        self,
        user_input: str,
        sketch_analysis: Dict[str, Any],
    ) -> str:
        prompt = f"""
    너는 CADly의 사용자 응답 생성 담당자다.

    목표:
    사용자의 텍스트 요청과 손도면 분석 결과, CADly schema를 바탕으로
    사용자에게 자연스럽고 명확한 응답을 작성해라.

    중요:
    - 단순히 JSON을 나열하지 마라.
    - 사용자가 요청한 내용을 반영해서 말해라.
    - 손도면에서 인식한 공간과 연결 관계를 간단히 설명해라.
    - 아직 확실하지 않은 부분이 있으면 조심스럽게 언급해라.
    - 너무 길게 쓰지 마라.

    사용자 요청:
    {user_input}

    손도면 분석 결과:
    {json.dumps(sketch_analysis, ensure_ascii=False, indent=2)}

    사용자에게 보여줄 응답만 작성해라.
    """

        response = low_llm.invoke([
            HumanMessage(content=prompt)
        ])

        return response.content