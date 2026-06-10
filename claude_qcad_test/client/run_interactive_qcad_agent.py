from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from anthropic import AsyncAnthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT_DIR = Path(__file__).resolve().parents[1]

DEFAULT_INPUT_DXF = ROOT_DIR / "samples" / "sample_house.dxf"
DEFAULT_ROOM_LABEL_JSON = ROOT_DIR / "samples" / "sample_rooms.json"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs"


SYSTEM_PROMPT = """
You are a Claude-QCAD refinement agent.

The user will type natural-language drafting/refinement requests.
You must use the available MCP tools to inspect, modify, validate, and render the DXF.

Important rules:
- Do not pretend that you modified the drawing unless you actually called an MCP tool.
- Use inspect_dxf before making major changes if the current DXF state is unclear.
- Use validate_geometry after applying a refinement plan.
- Use render_preview when the user asks to see or preview the result.
- Preserve the existing room topology.
- Do not invent new rooms unless the user explicitly asks.
- Use room_label_json as the semantic source of truth.
- Use DXF as the geometric source of truth.
- Prefer small safe corrections:
  - normalize layers
  - align nearly horizontal/vertical walls
  - add room labels
  - snap endpoints
  - render preview
  - validate geometry

When calling apply_refinement_plan, create a JSON plan like:
{
  "actions": [
    {
      "tool": "normalize_layers",
      "params": {
        "wall_layer": "WALL",
        "text_layer": "ROOM_TEXT"
      }
    }
  ]
}

Use backend according to the user's selected backend.
Use output paths inside the outputs directory.
After each tool result, briefly explain what changed and what file was created.
"""


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def _extract_text_from_mcp_result(result: Any) -> str:
    """
    Convert MCP CallToolResult into plain text for Claude tool_result.
    """
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
    """
    Convert MCP tool definitions to Anthropic tool definitions.
    """
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


async def run_interactive_agent(args: argparse.Namespace) -> None:
    load_dotenv()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY가 없습니다. .env에 넣거나 export ANTHROPIC_API_KEY='...'로 설정해 주세요."
        )

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    input_dxf = Path(args.input_dxf).resolve()
    room_label_json = Path(args.room_label_json).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    server_path = ROOT_DIR / "qcad_mcp" / "server.py"

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        env={
            **os.environ,
            "QCAD_BIN": os.getenv("QCAD_BIN", ""),
        },
    )

    anthropic_client = AsyncAnthropic(api_key=api_key)

    print("\n=== Claude QCAD MCP Interactive Agent ===")
    print(f"input_dxf        : {input_dxf}")
    print(f"room_label_json  : {room_label_json}")
    print(f"output_dir       : {output_dir}")
    print(f"backend          : {args.backend}")
    print("\n명령 예시:")
    print("- 벽을 수평/수직으로 정렬하고 레이어를 WALL로 정리해줘")
    print("- 방 이름 라벨을 추가해줘")
    print("- 현재 도면을 검증해줘")
    print("- svg로 미리보기 렌더링해줘")
    print("- 최종 dxf로 저장해줘")
    print("\n종료하려면 /exit 입력\n")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            anthropic_tools = _convert_mcp_tools_to_anthropic_tools(mcp_tools)

            messages: List[Dict[str, Any]] = [
                {
                    "role": "user",
                    "content": f"""
We are starting an interactive QCAD refinement session.

Current files:
- input_dxf: {input_dxf}
- room_label_json: {room_label_json}
- output_dir: {output_dir}
- backend: {args.backend}

Use these paths unless the user provides different paths.
For intermediate DXF files, save into output_dir.
For preview SVG files, save into output_dir.
""",
                }
            ]

            while True:
                user_input = input("You > ").strip()

                if not user_input:
                    continue

                if user_input.lower() in {"/exit", "exit", "quit", "/quit"}:
                    print("종료합니다.")
                    break

                messages.append(
                    {
                        "role": "user",
                        "content": user_input,
                    }
                )

                # Claude may call tools multiple times before returning a normal answer.
                for _ in range(args.max_tool_turns):
                    response = await anthropic_client.messages.create(
                        model=model,
                        max_tokens=2048,
                        system=SYSTEM_PROMPT,
                        messages=messages,
                        tools=anthropic_tools,
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

                    # No tool call: print Claude's final text response.
                    if not tool_uses:
                        texts = [
                            getattr(block, "text", "")
                            for block in assistant_content
                            if getattr(block, "type", None) == "text"
                        ]
                        print("\nClaude > " + "\n".join(texts).strip() + "\n")
                        break

                    tool_results_content = []

                    for tool_use in tool_uses:
                        tool_name = tool_use.name
                        tool_args = tool_use.input or {}

                        print(f"\n[MCP CALL] {tool_name}")
                        print(json.dumps(tool_args, ensure_ascii=False, indent=2))

                        try:
                            result = await session.call_tool(tool_name, tool_args)
                            result_text = _extract_text_from_mcp_result(result)

                            print(f"\n[MCP RESULT] {tool_name}")
                            print(result_text)

                            tool_results_content.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_use.id,
                                    "content": result_text,
                                }
                            )

                        except Exception as e:
                            error_text = f"Tool call failed: {type(e).__name__}: {e}"
                            print(f"\n[MCP ERROR] {tool_name}")
                            print(error_text)

                            tool_results_content.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_use.id,
                                    "content": error_text,
                                    "is_error": True,
                                }
                            )

                    messages.append(
                        {
                            "role": "user",
                            "content": tool_results_content,
                        }
                    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--backend",
        choices=["python", "qcad"],
        default="python",
        help="python은 fallback 테스트, qcad는 실제 QCAD 실행",
    )

    parser.add_argument(
        "--input-dxf",
        default=str(DEFAULT_INPUT_DXF),
    )

    parser.add_argument(
        "--room-label-json",
        default=str(DEFAULT_ROOM_LABEL_JSON),
    )

    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
    )

    parser.add_argument(
        "--max-tool-turns",
        type=int,
        default=8,
        help="한 번의 사용자 입력에 대해 Claude가 MCP tool을 연속 호출할 수 있는 최대 횟수",
    )

    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await run_interactive_agent(args)


if __name__ == "__main__":
    asyncio.run(main())