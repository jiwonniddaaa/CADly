from __future__ import annotations

from typing import Any, Dict, List, TypedDict, Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CADlyGenerationState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    user_input: str

    # generation input
    graph_json_path: str
    model_path: str
    out_dir: str
    name: str

    graph_data: Dict[str, Any]

    # generation output
    svg_path: str
    dxf_path: str
    room_label_path: str

    # verification results
    validation_errors: List[str]
    verification_warnings: List[str]

    # common status and messages
    status: str
    message: str

    # repair agent state
    repair_route: str
    repair_history: List[Dict[str, Any]]

    # resampling control
    resample_count: int
    max_resamples: int
    seed: int

    # postprocess control
    postprocess_count: int
    max_postprocesses: int

    # optional MCP actions
    enable_cad_import: bool
    target_cad: str
    mcp_requested_action: str
    cad_import_status: str
    cad_import_result: Dict[str, Any]

    # QCAD generation
    qcad_output_dir: str
    qcad_dxf_path: str
    qcad_repair_error: str

    # generation mode
    generation_mode: Literal["sampling", "qcad"]