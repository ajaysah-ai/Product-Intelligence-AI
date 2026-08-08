"""
Run standalone for local testing:
    python -m uvicorn app.mcp_server.server:app --host 0.0.0.0 --port 8100

In docker-compose this runs as its own service (see docker-compose.yml),
built from the same image as the backend so it reuses the extraction
pipeline (Phase 3) and its heavy dependencies (torch/easyocr) without a
second slow install.
"""
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.mcp_server.fetchers import fetch_and_extract

server = MCPServer("product-intelligence-mcp")


@server.tool()
def website_agent(url: str) -> dict:
    """Fetches a product's official website page and extracts its text content."""
    return fetch_and_extract(url, "website")


@server.tool()
def catalog_agent(url: str) -> dict:
    """Fetches a product catalog page or catalog PDF and extracts its text content."""
    return fetch_and_extract(url, "catalog")


@server.tool()
def tech_doc_agent(url: str) -> dict:
    """Fetches a technical document (spec sheet, manual, datasheet) and extracts its text content."""
    return fetch_and_extract(url, "tech_doc")


@server.tool()
def digital_asset_agent(url: str) -> dict:
    """Fetches a digital asset (product photo, diagram) and extracts any embedded text via OCR."""
    return fetch_and_extract(url, "digital_asset")


app = server.streamable_http_app(
    # This server is only reachable on the private Docker Compose network, not
    # exposed directly to browsers, so DNS-rebinding protection (which by
    # default only trusts the Host header "127.0.0.1") isn't needed here —
    # and its default would reject the Compose service name "mcp_server".
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)
