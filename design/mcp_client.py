from __future__ import annotations

import asyncio
import sys
from typing import Any, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _call_cad_import_tool_async(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                tool_name,
                arguments=arguments,
            )

            # MCP result는 content 형태로 올 수 있어서 여기서 일반 dict로 정리
            return {
                "ok": True,
                "tool": tool_name,
                "raw_result": result,
            }


def call_cad_import_tool(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        return asyncio.run(
            _call_cad_import_tool_async(
                tool_name=tool_name,
                arguments=arguments,
            )
        )

    except Exception as e:
        return {
            "ok": False,
            "tool": tool_name,
            "message": f"MCP tool call failed: {e}",
        }