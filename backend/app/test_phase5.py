"""
Run after `docker compose up` (needs the mcp_server service running):
    docker compose exec backend python -m app.test_phase5

Spins up a throwaway HTTP server inside THIS container on port 8199, serving
a test HTML page. The mcp_server container fetches it via the Docker network
using the service name "backend" (http://backend:8199/...) — a real HTTP
fetch end-to-end, no internet access or mocking required.

Exits non-zero if any check fails.
"""
import asyncio
import functools
import http.server
import socketserver
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.main import app
from app.mcp_client.client import MCP_SERVER_URL

client = TestClient(app)
results = []

TEST_HTTP_PORT = 8199
TEST_PAGE_CONTENT = (
    "<html><body><h1>Wireless Keyboard XJ-500</h1>"
    "<p>Hot-swappable mechanical switches with RGB backlighting.</p></body></html>"
)


def check(description, passed):
    results.append((description, passed))
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {description}")


def start_test_http_server(directory: Path, port: int):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


async def _list_tools_async():
    async with streamable_http_client(MCP_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [t.name for t in result.tools]


async def _call_tool_async(tool_name: str, url: str):
    async with streamable_http_client(MCP_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, {"url": url})
            return result


def main():
    tmp_dir = Path(tempfile.mkdtemp())
    (tmp_dir / "website.html").write_text(TEST_PAGE_CONTENT, encoding="utf-8")
    start_test_http_server(tmp_dir, TEST_HTTP_PORT)
    time.sleep(0.5)

    website_url = f"http://backend:{TEST_HTTP_PORT}/website.html"

    # -----------------------------------------------------------------
    # 1) MCP server starts standalone, tools list correctly
    # -----------------------------------------------------------------
    try:
        tool_names = asyncio.run(_list_tools_async())
        expected = {"website_agent", "catalog_agent", "tech_doc_agent", "digital_asset_agent"}
        check(f"MCP server lists all 4 expected tools (got {tool_names})", expected.issubset(set(tool_names)))
    except Exception:
        print("---- full traceback for MCP list_tools failure ----")
        traceback.print_exc()
        print("----------------------------------------------------")
        check("MCP server reachable and lists tools", False)

    # -----------------------------------------------------------------
    # 2) Calling website_agent on a real URL returns text, not an error
    # -----------------------------------------------------------------
    import json

    try:
        result = asyncio.run(_call_tool_async("website_agent", website_url))
        payload = json.loads(result.content[0].text)
        check("website_agent: no error", payload.get("error") is None)
        check(
            "website_agent: extracted text contains expected content",
            payload.get("text") is not None and "Wireless Keyboard XJ-500" in payload["text"],
        )
    except Exception:
        print("---- full traceback for website_agent call failure ----")
        traceback.print_exc()
        print("---------------------------------------------------------")
        check("website_agent call succeeded", False)

    # -----------------------------------------------------------------
    # 3) Retrieved content lands in temp_documents (same table as uploads)
    # -----------------------------------------------------------------
    r = client.post("/submit", data={"text": "external retrieval test", "sources_selected": '["website"]'})
    check("submit with sources_selected=[website] -> 200", r.status_code == 200)
    request_id = r.json().get("request_id") if r.status_code == 200 else None

    if request_id:
        r2 = client.post(f"/fetch-external/{request_id}", json={"sources": {"website": website_url}})
        check("fetch-external -> 200", r2.status_code == 200)
        if r2.status_code == 200:
            website_result = next((x for x in r2.json()["results"] if x["source_type"] == "website"), None)
            check("fetch-external: website source not skipped", website_result is not None and website_result["skipped"] is False)
            check(
                "fetch-external: website document stored with success status",
                website_result is not None and website_result.get("status") == "success",
            )
    else:
        check("fetch-external -> 200 (skipped, no request_id)", False)

    # -----------------------------------------------------------------
    # 4) Toggling a source OFF -> skipped entirely, even with a URL provided
    # -----------------------------------------------------------------
    r3 = client.post("/submit", data={"text": "toggle-off test", "sources_selected": '["website"]'})  # catalog NOT selected
    request_id_2 = r3.json().get("request_id") if r3.status_code == 200 else None

    if request_id_2:
        r4 = client.post(
            f"/fetch-external/{request_id_2}",
            json={"sources": {"website": website_url, "catalog": "http://backend:9999/never-fetched.html"}},
        )
        check("toggle-off: fetch-external -> 200", r4.status_code == 200)
        if r4.status_code == 200:
            catalog_result = next((x for x in r4.json()["results"] if x["source_type"] == "catalog"), None)
            check(
                "toggle-off: catalog source (not in sources_selected) was skipped",
                catalog_result is not None and catalog_result["skipped"] is True,
            )
    else:
        check("toggle-off test setup failed", False)

    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{total} checks passed")
    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
