from __future__ import annotations

from typing import Any, Dict, List, TypedDict, Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CADlyGenerationState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    user_input: str

    graph_json_path: str
    model_path: str
    out_dir: str
    name: str

    graph_data: Dict[str, Any]
    validation_errors: List[str]
    verification_warnings: List[str]

    svg_path: str
    dxf_path: str
    room_label_path: str

    status: str
    message: str

    repair_action: str
    repair_reason: str
    repair_history: List[Dict[str, Any]]
    retry_count: int
    max_retries: int
    export_repair_count: int
    max_export_repairs: int

    enable_cad_import: bool
    target_cad: str
    cad_import_status: str
    cad_import_result: Dict[str, Any]