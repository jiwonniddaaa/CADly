from __future__ import annotations

import asyncio
import sys
import json
from typing import Any, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)

def _extract_mcp_result(result: Any) -> Dict[str, Any]:
    """
    MCP CallToolResult를 일반 dict로 최대한 정리.
    tool이 dict를 text JSON으로 반환하는 경우까지 처리.
    """
    try:
        content = getattr(result, "content", [])

        texts = []
        for item in content:
            item_type = getattr(item, "type", None)

            if item_type == "text":
                texts.append(getattr(item, "text", ""))
            else:
                texts.append(json.dumps(item, default=_json_default, ensure_ascii=False))

        joined = "\n".join(texts).strip()

        if joined:
            try:
                return json.loads(joined)
            except Exception:
                return {
                    "text": joined,
                }

        return {
            "raw_result": json.loads(
                json.dumps(result, default=_json_default, ensure_ascii=False)
            )
        }

    except Exception:
        return {
            "raw_result": str(result),
        }

async def _call_mcp_tool_async(
    *,
    server_module: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", server_module],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                tool_name,
                arguments=arguments,
            )

            parsed_result = _extract_mcp_result(result)

            return {
                "ok": True,
                "server_module": server_module,
                "tool": tool_name,
                "result": parsed_result,
                "raw_result": result,
            }

def call_mcp_tool(
    *,
    server_module: str,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        return asyncio.run(
            _call_mcp_tool_async(
                server_module=server_module,
                tool_name=tool_name,
                arguments=arguments,
            )
        )

    except Exception as e:
        return {
            "ok": False,
            "server_module": server_module,
            "tool": tool_name,
            "message": f"MCP tool call failed: {e}",
        }

_CAD_IMPORT_SERVER = "mcp_server.server"


async def call_cad_import_tool_async(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        return await _call_mcp_tool_async(
            server_module=_CAD_IMPORT_SERVER,
            tool_name=tool_name,
            arguments=arguments,
        )
    except Exception as e:
        return {
            "ok": False,
            "server_module": _CAD_IMPORT_SERVER,
            "tool": tool_name,
            "message": f"MCP tool call failed: {e}",
        }


# CAD Import Tool (sync callers: design pipeline nodes)
def call_cad_import_tool(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    return call_mcp_tool(
        server_module=_CAD_IMPORT_SERVER,
        tool_name=tool_name,
        arguments=arguments,
    )
    
# CAD refinement tool
def call_refinement_tool(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    return call_mcp_tool(
        server_module="mcp_server.refinement_server",
        tool_name=tool_name,
        arguments=arguments,
    )