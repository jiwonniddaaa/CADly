from __future__ import annotations

import base64
import uuid
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
    }
)


def decode_image_base64(image_base64: str) -> bytes:
    raw = image_base64.strip()
    if raw.startswith("data:"):
        _, _, raw = raw.partition(",")
    return base64.b64decode(raw)


def media_type_to_suffix(image_media_type: Optional[str]) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mapping.get((image_media_type or "").lower(), ".jpg")


def persist_upload_image(image_base64: str, image_media_type: Optional[str]) -> str:
    upload_dir = Path(gettempdir()) / "cadly" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    image_path = upload_dir / f"{uuid.uuid4().hex}{media_type_to_suffix(image_media_type)}"
    image_path.write_bytes(decode_image_base64(image_base64))
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
