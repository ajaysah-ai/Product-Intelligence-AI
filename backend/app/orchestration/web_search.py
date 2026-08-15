import httpx
from bs4 import BeautifulSoup


def parse_duckduckgo_html(html: str, max_results: int = 3) -> list[dict]:
    """Parses DuckDuckGo's HTML-only search results page. Separated from the
    fetch so it can be unit-tested against a saved fixture without needing
    live internet access."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for link in soup.select("a.result__a"):
        href = link.get("href")
        title = link.get_text(strip=True)
        if href and title:
            results.append({"title": title, "url": href})
        if len(results) >= max_results:
            break
    return results


def search_web(query: str, max_results: int = 3) -> list[dict]:
    """Returns [{"title", "url"}]. Returns an empty list on any failure —
    callers should treat "no results" as a normal, non-fatal outcome, since
    the pipeline can still proceed with whatever data already exists."""
    if not query or not query.strip():
        return []
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0) as client:
            resp = client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (ProductIntelligenceAI/1.0)"},
            )
            resp.raise_for_status()
            return parse_duckduckgo_html(resp.text, max_results=max_results)
    except Exception:
        return []
