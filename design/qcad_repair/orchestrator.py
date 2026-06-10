from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, List

from dotenv import load_dotenv
from anthropic import AsyncAnthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from design.qcad_repair.prompts import AUTONOMOUS_QCAD_REPAIR_PROMPT
from design.mcp_client import call_refinement_tool

def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)

def _extract_text_from_mcp_result(result: Any) -> str:
    try:
        content = getattr(result, "content", [])
        parts = []

        for item in content:
            item_type = getattr(item, "type", None)

            if item_type == "text":
                parts.append(getattr(item, "text", ""))
            else:
                parts.append(json.dumps(item, default=_json_default, ensure_ascii=False, indent=2))

        if parts:
            return "\n".join(parts)

        return json.dumps(result, default=_json_default, ensure_ascii=False, indent=2)

    except Exception:
        return str(result)

def _convert_mcp_tools_to_anthropic_tools(mcp_tools: Any) -> List[Dict[str, Any]]:
    anthropic_tools = []

    for tool in mcp_tools.tools:
        input_schema = getattr(tool, "inputSchema", None)
        if input_schema is None:
            input_schema = getattr(tool, "input_schema", None)

        if input_schema is None:
            input_schema = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }

        anthropic_tools.append(
            {
                "name": tool.name,
                "description": tool.description or f"MCP tool: {tool.name}",
                "input_schema": input_schema,
            }
        )

    return anthropic_tools

def _load_skillset() -> str:
    path = Path(__file__).resolve().parent / "skillset.md "
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

async def run_qcad_repair(
    *,
    input_dxf: str,
    room_label_json: Optional[str],
    output_dir: str,
    backend: str = "python",
    max_tool_turns: int = 8,
) -> Dict[str, Any]:
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "status": "qcad_repair_failed",
            "message": "ANTHROPIC_API_KEY is missing.",
        }
    
    model = "claude-sonnet-4-5-20250929"
    input_path = Path(input_dxf).resolve()
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        return {
            "status": "qcad_repair_failed",
            "message": f"input_dxf not found: {input_path}",
        }
    
    room_label_path = Path(room_label_json).resolve() if room_label_json else None

    refined_dxf = output_path / f"{input_path.stem}_qcad_refined.dxf"
    refined_svg = output_path / f"{input_path.stem}_qcad_refined.svg"

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.refinement_server"],
        env={
            **os.environ,
            "QCAD_BIN": os.environ.get("QCAD_BIN", ""),
        }
    )

    anthropic_client = AsyncAnthropic(api_key=api_key)

    repair_history: List[Dict[str, Any]] = []

    initial_user_goal = f"""
Run an autonomous QCAD refinement process.

Input DXF:
{input_path}

This input DXF has already been processed by a rule-based CAD style enhancer.
It may contain added wall outlines, simple doors, windows, dimensions, title block, and other CAD-style drafting elements.

Your role is not to redesign the floorplan.
Your role is to inspect, validate, and safely repair the enhanced DXF if necessary.

Files:
- input_dxf: {input_path}
- room_label_json: {room_label_path if room_label_path else ""}
- output_dxf: {refined_dxf}
- output_svg: {refined_svg}
- backend: {backend}

Required process:
1. Call inspect_dxf on input_dxf.
2. Call validate_geometry on input_dxf.
3. Decide whether a small repair is necessary.
4. If repair is necessary, call apply_refinement_plan.
   - Use output_dxf as the output path.
   - Use backend: {backend}.
   - Prefer small safe actions such as align_walls or normalize_layers.
   - Avoid duplicate labels.
   - Avoid destructive layer normalization if room layers are meaningful.
5. If no repair is necessary, call apply_refinement_plan with an empty actions list to create output_dxf.
6. Call validate_geometry on output_dxf.
7. Call render_preview using output_dxf and output_svg.
8. Return a concise final summary.

Important:
- Do not run enhance_cad_style again unless the enhanced DXF is still clearly under-detailed.
- Do not add duplicate doors, windows, dimensions, or title blocks.
- Preserve the existing room topology.
- Do not invent new rooms.
"""

    
    messages: List[Dict[str, Any]] = [
        {
            "role": "user",
            "content": initial_user_goal,
        },
    ]

    final_text = ""

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            anthropic_tools = _convert_mcp_tools_to_anthropic_tools(mcp_tools)
            skillset = _load_skillset()

            for turn in range(max_tool_turns):
                response = await anthropic_client.messages.create(
                    model=model,
                    messages=messages,
                    tools=anthropic_tools,
                    max_tokens=2048,
                    system=AUTONOMOUS_QCAD_REPAIR_PROMPT + "/n/n" + skillset,
                )

                assistant_content = response.content

                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_content,
                    }
                )

                tool_uses = [
                    block for block in assistant_content
                    if getattr(block, "type", None) == "tool_use"
                ]

                if not tool_uses:
                    texts = [
                        getattr(block, "text", "") for block in response.content
                        if getattr(block, "type", None) == "text"
                    ]
                    break

                tool_results_content = []

                for tool_use in tool_uses:
                    tool_name = tool_use.name
                    tool_args = tool_use.input or {}
                    
                    try:
                        result = await session.call_tool(tool_name, tool_args)
                        result_text = _extract_text_from_mcp_result(result)
                    
                        repair_history.append({
                            "turn": turn + 1,
                            "tool": tool_name,
                            "arguments": tool_args,
                            "result": result_text,
                        })

                        tool_results_content.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": result_text,
                            
                        })
                    
                    except Exception as e:
                        error_text = f"Tool call failed: {type(e).__name__}: {str(e)}"
                        repair_history.append({
                            "turn": turn + 1,
                            "tool": tool_name,
                            "arguments": tool_args,
                            "error": error_text,
                        })

                        tool_results_content.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": error_text,
                            "is_error": True,
                        })

                messages.append(
                    {
                        "role": "user",
                        "content": tool_results_content,
                    }
                )
        
    return {
        "status": "qcad_refined",
        "input_dxf": str(input_path),
        "refined_dxf_path": str(refined_dxf),
        "refined_svg_path": str(refined_svg),
        "qcad_repair_report": {
            "backend": backend,
            "model": model,
            "final_text": final_text,
            "repair_history": repair_history,
        },
    }

def run_qcad_repair_sync(
        *,
    input_dxf: str,
    room_label_json: Optional[str],
    output_dir: str,
    backend: str = "python",
    max_tool_turns: int = 10,
) -> Dict[str, Any]:
    return asyncio.run(
        run_qcad_repair(
            input_dxf=input_dxf,
            room_label_json=room_label_json,
            output_dir=output_dir,
            backend=backend,
            max_tool_turns=max_tool_turns,
        )
    )

# rule-based fallback용
def run_qcad_repair_rule_based_sync(
    *,
    input_dxf: str,
    room_label_json: Optional[str],
    output_dir: str,
    backend: str = "python",
) -> Dict[str, Any]:
    input_path = Path(input_dxf).resolve()
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    refined_dxf = output_path / f"{input_path.stem}_qcad_refined.dxf"
    refined_svg = output_path / f"{input_path.stem}_qcad_refined.svg"

    if not input_path.exists():
        return {
            "status": "qcad_repair_failed",
            "message": f"input_dxf not found: {input_path}",
        }

    inspect_result = call_refinement_tool(
        tool_name="inspect_dxf",
        arguments={
            "input_dxf": str(input_path),
        },
    )

    validation_before = call_refinement_tool(
        tool_name="validate_geometry",
        arguments={
            "input_dxf": str(input_path),
            "room_label_json": room_label_json,
        },
    )

    plan = {
        "actions": [
            {
                "tool": "normalize_layers",
                "params": {
                    "wall_layer": "WALL",
                    "text_layer": "ROOM_TEXT",
                },
            },
            {
                "tool": "align_walls",
                "params": {
                    "tolerance": 20,
                },
            },
            {
                "tool": "add_room_labels",
                "params": {
                    "text_height": 250,
                    "text_layer": "ROOM_TEXT",
                },
            },
        ]
    }

    apply_result = call_refinement_tool(
        tool_name="apply_refinement_plan",
        arguments={
            "input_dxf": str(input_path),
            "output_dxf": str(refined_dxf),
            "room_label_json": str(room_label_json) if room_label_json else "",
            "plan_json": json.dumps(plan, ensure_ascii=False),
            "backend": backend,
        },
    )

    validation_after = call_refinement_tool(
        tool_name="validate_geometry",
        arguments={
            "input_dxf": str(refined_dxf),
            "room_label_json": room_label_json,
        },
    )

    preview_result = call_refinement_tool(
        tool_name="render_preview",
        arguments={
            "input_dxf": str(refined_dxf),
            "output_svg": str(refined_svg),
        },
    )

    return {
        "status": "qcad_refined",
        "input_dxf": str(input_path),
        "refined_dxf_path": str(refined_dxf),
        "refined_svg_path": str(refined_svg),
        "qcad_repair_report": {
            "backend": backend,
            "inspect_result": inspect_result,
            "validation_before": validation_before,
            "plan": plan,
            "apply_result": apply_result,
            "validation_after": validation_after,
            "preview_result": preview_result,
        },
    }