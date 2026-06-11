# CADly/agent/session_utils.py
from __future__ import annotations

import base64
import uuid
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage, messages_from_dict, messages_to_dict

EPHEMERAL_STATE_KEYS = frozenset(
    {
        "image_path",
        "image_base64",
        "image_media_type",
        "user_input",
        "sketch_apply_ok",
        "template_answer",
    }
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024

HEIC_MEDIA_TYPES = frozenset(
    {
        "image/heic",
        "image/heif",
        "image/heic-sequence",
        "image/heif-sequence",
    }
)

ANTHROPIC_IMAGE_MEDIA_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

MEDIA_TYPE_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

UNSUPPORTED_IMAGE_HINT = (
    "JPG, PNG, WebP, GIF, HEIC 형식의 이미지만 업로드할 수 있습니다."
)

_heif_registered = False


def decode_image_base64(image_base64: str) -> bytes:
    raw = image_base64.strip()
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")
    return base64.b64decode(raw)


def _ensure_heif_support() -> None:
    global _heif_registered
    if _heif_registered:
        return
    try:
        from pillow_heif import register_heif_opener
    except ImportError as exc:
        raise ValueError(
            "HEIC 이미지 변환을 위해 pillow-heif 패키지가 필요합니다. "
            "pip install pillow-heif 로 설치하거나 JPG/PNG로 변환해 주세요."
        ) from exc

    register_heif_opener()
    _heif_registered = True


def sniff_image_media_type(data: bytes) -> Optional[str]:
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        brand = data[8:12].decode("ascii", errors="ignore").lower()
        if brand.startswith("avif"):
            return "image/avif"
        if brand.startswith(("heic", "heix", "mif1", "msf1")):
            return "image/heic"
    return None


def _is_heic_payload(data: bytes, declared_media_type: Optional[str] = None) -> bool:
    declared = (declared_media_type or "").lower()
    if declared in HEIC_MEDIA_TYPES:
        return True
    return sniff_image_media_type(data) == "image/heic"


def _convert_heic_to_jpeg(data: bytes) -> bytes:
    _ensure_heif_support()
    from PIL import Image

    try:
        with Image.open(BytesIO(data)) as img:
            rgb = img.convert("RGB")
            out = BytesIO()
            rgb.save(out, format="JPEG", quality=85, optimize=True)
            return out.getvalue()
    except Exception as exc:
        raise ValueError(
            "HEIC 이미지를 JPEG로 변환하지 못했습니다. "
            "다른 형식으로 다시 시도해 주세요."
        ) from exc


def _fit_image_size(data: bytes, media_type: str) -> tuple[bytes, str]:
    if len(data) <= MAX_IMAGE_BYTES:
        return data, media_type

    from PIL import Image

    with Image.open(BytesIO(data)) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size

        for quality in (85, 75, 65, 55):
            for scale in (1.0, 0.75, 0.5, 0.35):
                resized = rgb
                if scale < 1.0:
                    resized = rgb.resize(
                        (max(1, int(width * scale)), max(1, int(height * scale))),
                        Image.Resampling.LANCZOS,
                    )
                out = BytesIO()
                resized.save(out, format="JPEG", quality=quality, optimize=True)
                if len(out.getvalue()) <= MAX_IMAGE_BYTES:
                    return out.getvalue(), "image/jpeg"

    raise ValueError("이미지 크기가 5MB를 초과합니다. 더 작은 파일을 업로드해 주세요.")


def normalize_upload_image(
    data: bytes,
    declared_media_type: Optional[str] = None,
) -> tuple[bytes, str]:
    if not data:
        raise ValueError("빈 이미지 파일입니다.")

    if _is_heic_payload(data, declared_media_type):
        data = _convert_heic_to_jpeg(data)
        media_type = "image/jpeg"
    else:
        sniffed = sniff_image_media_type(data)
        declared = (declared_media_type or "").lower()
        if sniffed == "image/avif" or declared == "image/avif":
            raise ValueError(
                "AVIF 형식은 지원하지 않습니다. JPG, PNG, WebP, GIF, HEIC로 변환해 주세요."
            )
        media_type = sniffed or declared or None
        if media_type not in ANTHROPIC_IMAGE_MEDIA_TYPES:
            raise ValueError(
                f"지원하지 않는 이미지 형식입니다 ({media_type or '알 수 없음'}). "
                f"{UNSUPPORTED_IMAGE_HINT}"
            )

    return _fit_image_size(data, media_type)


def media_type_to_suffix(image_media_type: Optional[str]) -> str:
    normalized = (image_media_type or "").lower()
    return MEDIA_TYPE_SUFFIX.get(normalized, ".jpg")


def prepare_image_payload(
    data: bytes,
    declared_media_type: Optional[str] = None,
) -> tuple[str, str]:
    normalized, media_type = normalize_upload_image(data, declared_media_type)
    return base64.b64encode(normalized).decode("utf-8"), media_type


def persist_upload_image(image_base64: str, image_media_type: Optional[str]) -> str:
    data = decode_image_base64(image_base64)
    normalized, media_type = normalize_upload_image(data, image_media_type)
    upload_dir = Path(gettempdir()) / "cadly" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    image_path = upload_dir / f"{uuid.uuid4().hex}{MEDIA_TYPE_SUFFIX[media_type]}"
    image_path.write_bytes(normalized)
    return str(image_path)


def serialize_messages(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    return messages_to_dict(messages)


def deserialize_messages(raw_messages: Any) -> List[BaseMessage]:
    if not isinstance(raw_messages, list):
        return []
    return messages_from_dict(raw_messages)


def get_last_ai_text(messages: List[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, str) and content.strip():
                return content
    return ""


def read_svg_content(svg_path: Optional[str]) -> Optional[str]:
    if not svg_path:
        return None
    path = Path(svg_path)
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def split_session_blob(session: Optional[Dict[str, Any]]) -> Tuple[
    List[BaseMessage],
    str,
    Dict[str, Any],
    Dict[str, Any],
]:
    """messages, active_orchestrator, design_state, planning_fields"""
    merged = dict(session or {})
    messages = deserialize_messages(merged.pop("messages", []))
    active_orchestrator = merged.pop("active_orchestrator", "planning") or "planning"
    design_state = merged.pop("design_state", None)
    if not isinstance(design_state, dict):
        design_state = {}
    return messages, active_orchestrator, design_state, merged


def merge_session_blob(
    planning_fields: Dict[str, Any],
    messages: List[BaseMessage],
    active_orchestrator: str,
    design_state: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        **planning_fields,
        "messages": serialize_messages(messages),
        "active_orchestrator": active_orchestrator,
        "design_state": design_state,
    }


def build_persisted_fields(
    state_fields: Dict[str, Any],
    result: Dict[str, Any],
    exclude_keys: Optional[frozenset[str]] = None,
) -> Dict[str, Any]:
    excluded = exclude_keys or EPHEMERAL_STATE_KEYS
    return {
        key: value
        for key, value in {**state_fields, **result}.items()
        if key not in excluded
    }
