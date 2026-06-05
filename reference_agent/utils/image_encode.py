from __future__ import annotations

import base64
from pathlib import Path
from typing import Tuple


def encode_image_file(image_path: str) -> Tuple[str, str]:
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


def resolve_image_source(
    *,
    image_path: str | None = None,
    image_base64: str | None = None,
    image_media_type: str | None = None,
) -> Tuple[str, str]:
    if image_base64:
        media_type = image_media_type or "image/jpeg"
        payload = image_base64.strip()
        if payload.startswith("data:"):
            header, _, data = payload.partition(",")
            if ";" in header:
                media_type = header.split(";", 1)[0].replace("data:", "")
            payload = data
        return payload, media_type

    if image_path:
        return encode_image_file(image_path)

    raise ValueError("image_path 또는 image_base64가 필요합니다.")
