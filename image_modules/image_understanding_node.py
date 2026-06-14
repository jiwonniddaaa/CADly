# image_modules/image_understanding_node.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

from anthropic import BadRequestError
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage

from CADly.agent.session_utils import (
    decode_image_base64,
    prepare_image_payload,
)

llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001"
)

_IMAGE_ERROR_MESSAGE = (
    "업로드하신 이미지를 분석할 수 없습니다. "
    "JPG, PNG, WebP, GIF, HEIC 형식의 이미지를 다시 업로드해 주세요."
)


def _load_image_payload(state: Dict[str, Any]) -> tuple[str, str]:
    image_media_type = state.get("image_media_type")
    image_base64 = state.get("image_base64")
    image_path = state.get("image_path")

    if image_base64:
        data = decode_image_base64(image_base64)
    elif image_path:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")
        data = path.read_bytes()
    else:
        raise ValueError("분석할 이미지가 없습니다.")

    return prepare_image_payload(data, image_media_type)


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {
            "image_type": "unsupported_image",
            "reason": "JSON parsing failed",
        }


def _image_error_response(message: str) -> Dict[str, Any]:
    return {
        "route": "end",
        "image_type": "unsupported_image",
        "messages": [AIMessage(content=message)],
    }


def image_understanding_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    이미지가 손도면인지, 레퍼런스 이미지인지, 지원 불가 이미지인지 분류하는 노드.
    실제 분석은 sketch_agent 또는 reference_agent에서 수행한다.
    """
    user_input = state.get("user_input", "")

    try:
        image_data, media_type = _load_image_payload(state)
    except (FileNotFoundError, ValueError) as exc:
        return _image_error_response(str(exc))

    prompt = f"""
너는 CADly의 이미지 입력 라우터다.

사용자의 이미지가 어떤 유형인지 판단해라.

분류 기준:
1. hand_sketch
- 손으로 그린 평면도
- 방, 벽, 문, 창, 공간 이름이 있는 스케치
- 건축 도면처럼 보이는 러프한 이미지

2. reference_image
- 건축 레퍼런스 사진
- 실내/외 공간 사진
- 분위기, 재료, 스타일을 참고할 수 있는 이미지

3. unsupported_image
- 위 둘 다 아닌 경우
- 너무 흐리거나 분석 불가능한 이미지

사용자 입력:
{user_input}

반드시 JSON만 출력해라.

출력 형식:
{{
  "image_type": "hand_sketch | reference_image | unsupported_image",
  "confidence": 0.0,
  "reason": "판단 이유"
}}
"""

    try:
        response = llm.invoke([
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
                ],
            )
        ])
    except BadRequestError:
        return _image_error_response(_IMAGE_ERROR_MESSAGE)

    content = response.content
    result = _safe_json_loads(content)

    image_type = result.get("image_type", "unsupported_image")

    if image_type == "hand_sketch":
        route = "sketch_agent_node"
    elif image_type == "reference_image":
        route = "reference_agent"
    else:
        route = "general_answer"

    return {
        "route": route,
        "image_type": image_type,
        "image_classification": result,
    }
