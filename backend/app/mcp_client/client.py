import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp_server:8100/mcp")

SOURCE_TO_TOOL = {
    "website": "website_agent",
    "catalog": "catalog_agent",
    "tech_doc": "tech_doc_agent",
    "digital_asset": "digital_asset_agent",
}


async def _call_tool_async(tool_name: str, url: str) -> dict:
    async with streamable_http_client(MCP_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, {"url": url})
            if result.content and hasattr(result.content[0], "text"):
                return json.loads(result.content[0].text)
            return {"url": url, "text": None, "error": "Empty response from MCP server"}


def call_source_agent(source_type: str, url: str) -> dict:
    """Synchronous wrapper for use from FastAPI's sync route handlers.
    Returns {url, source_type, text, error} — error is None on success."""
    tool_name = SOURCE_TO_TOOL.get(source_type)
    if tool_name is None:
        return {
            "url": url,
            "source_type": source_type,
            "text": None,
            "error": f"Unknown source_type '{source_type}', expected one of {list(SOURCE_TO_TOOL)}",
        }
    try:
        return asyncio.run(_call_tool_async(tool_name, url))
    except Exception as e:
        return {"url": url, "source_type": source_type, "text": None, "error": f"MCP call failed: {e}"}
