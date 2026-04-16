import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# Pages to prioritize (crawled first)
PRIORITY_PATTERNS = re.compile(
    r"(career|job|hiring|team|about|staff|service|contact)", re.IGNORECASE
)

MAX_PAGES = 10
TIMEOUT = 10


async def crawl_website(url: str) -> str:
    """Crawl a website starting from the given URL. Returns combined text from up to 10 pages."""
    if not url:
        return ""

    visited: set[str] = set()
    texts: list[str] = []
    base_domain = urlparse(url).netloc

    # Discover links from homepage first, then prioritize career/about pages
    to_visit = [url]
    discovered: list[str] = []

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": "HVSalesIntel/1.0"}
    ) as client:
        while (to_visit or discovered) and len(visited) < MAX_PAGES:
            # Pick next URL: prioritize to_visit queue, then discovered
            if to_visit:
                current = to_visit.pop(0)
            else:
                current = discovered.pop(0)

            normalized = _normalize_url(current)
            if normalized in visited:
                continue
            visited.add(normalized)

            try:
                resp = await client.get(current)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue
            except (httpx.HTTPError, Exception):
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract text
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            if text:
                # Limit per-page text to avoid blowing up context
                texts.append(text[:5000])

            # Discover internal links (only from first few pages)
            if len(visited) <= 3:
                for a in soup.find_all("a", href=True):
                    href = urljoin(current, a["href"])
                    parsed = urlparse(href)
                    if parsed.netloc != base_domain:
                        continue
                    if parsed.scheme not in ("http", "https"):
                        continue
                    norm = _normalize_url(href)
                    if norm in visited:
                        continue
                    # Priority pages go to the front
                    if PRIORITY_PATTERNS.search(href):
                        to_visit.append(href)
                    else:
                        discovered.append(href)

    return "\n\n---\n\n".join(texts)


def _normalize_url(url: str) -> str:
    """Strip fragments and trailing slashes for dedup."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"
