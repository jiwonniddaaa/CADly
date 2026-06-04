from __future__ import annotations

from typing import Any, List

from langchain_core.messages import BaseMessage, HumanMessage


def extract_user_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    parts.append(text)
        return " ".join(parts).strip()

    return str(content).strip() if content is not None else ""


def build_human_message(
    *,
    text: str = "",
    image_path: str | None = None,
    image_base64: str | None = None,
    image_media_type: str | None = None,
) -> HumanMessage:
    from reference_agent.utils.image_encode import resolve_image_source

    has_image = bool(image_path or image_base64)
    text = (text or "").strip()

    if not has_image:
        return HumanMessage(content=text)

    image_data, media_type = resolve_image_source(
        image_path=image_path,
        image_base64=image_base64,
        image_media_type=image_media_type,
    )

    content: List[dict] = []
    if text:
        content.append({"type": "text", "text": text})
    else:
        content.append(
            {
                "type": "text",
                "text": "이 이미지와 비슷한 건축/인테리어 레퍼런스를 찾아주세요.",
            }
        )

    content.append(
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data,
            },
        }
    )

    return HumanMessage(content=content)
