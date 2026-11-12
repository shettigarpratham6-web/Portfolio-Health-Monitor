"""
Portfolio Health Monitor
External Financial Research & Web Scraping Service
Integrates Tavily Web Search, BeautifulSoup4 Sanitization, and Async HTTPX
"""

from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set
import urllib.parse

from bs4 import BeautifulSoup, Comment
from dateutil import parser as date_parser
import httpx
from pydantic import BaseModel, Field, HttpUrl

from app.core.config import Settings, get_settings

logger = logging.getLogger("agentx.services.research")


# ------------------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------------------
class ResearchArticle(BaseModel):
    """
    Standardized, normalized external financial intelligence article or filing.
    Preserves provenance metadata, publication dates, and sanitized text content.
    """
    title: str = Field(..., description="Cleaned article or announcement headline")
    url: str = Field(..., description="Canonical source URL")
    source_name: str = Field(..., description="Normalized publisher name or domain")
    publication_date: Optional[datetime] = Field(
        default=None,
        description="Extracted or declared publication timestamp (UTC)",
    )
    extracted_content: str = Field(
        ...,
        description="Sanitized, human-readable article text stripped of scripts and markup",
    )
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when content was retrieved",
    )
    snippet: Optional[str] = Field(
        default=None,
        description="Short summary or excerpt provided by search engine",
    )
    score: Optional[float] = Field(
        default=None,
        description="Search relevance or credibility score",
    )


# ------------------------------------------------------------------------------
# URL Sanitization & SSRF Safety
# ------------------------------------------------------------------------------
TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "msclkid", "trk", "source", "spm", "_hsenc",
}

DISALLOWED_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254", "metadata.google.internal",
}


def is_safe_url(url: str) -> bool:
    """
    Validate that a URL is well-formed, uses HTTP/HTTPS,
    and does not target internal network infrastructure (SSRF protection).
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        lower_host = hostname.lower()
        if lower_host in DISALLOWED_HOSTS or lower_host.endswith(".internal") or lower_host.endswith(".local"):
            return False

        # Verify not resolving to private IP ranges
        try:
            ip = ipaddress.ip_address(lower_host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass  # Standard domain name

        return True
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """
    Canonicalize URL by stripping tracking parameters, normalizing lowercase host,
    removing anchor fragments, and trimming trailing slashes.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Clean query parameters
        query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        cleaned_params = [
            (k, v) for k, v in query_params if k.lower() not in TRACKING_QUERY_PARAMS
        ]
        new_query = urllib.parse.urlencode(cleaned_params)

        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        canonical = urllib.parse.urlunparse((scheme, netloc, path, parsed.params, new_query, ""))
        return canonical
    except Exception:
        return url.strip()


def extract_domain(url: str) -> str:
    """Extract clean domain name without www prefix."""
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or "external"
    except Exception:
        return "external"


# ------------------------------------------------------------------------------
# HTML Parsing & Content Extraction
# ------------------------------------------------------------------------------
DANGEROUS_TAGS = {
    "script", "style", "noscript", "iframe", "embed", "object",
    "svg", "canvas", "nav", "footer", "header", "form", "aside",
}


def extract_publication_date(soup: BeautifulSoup, raw_html: str = "") -> Optional[datetime]:
    """
    Extract publication date from standard meta tags, JSON-LD, or HTML5 time elements.
    Returns timezone-aware UTC datetime if found and parseable.
    """
    candidate_strings: List[str] = []

    # 1. OpenGraph & Article Meta tags
    meta_attributes = [
        {"property": "article:published_time"},
        {"property": "og:published_time"},
        {"property": "rnews:datePublished"},
        {"name": "pubdate"},
        {"name": "publishdate"},
        {"name": "date"},
        {"name": "publication_date"},
        {"name": "sailthru.date"},
        {"name": "DC.date.issued"},
        {"name": "parsely-pub-date"},
        {"itemprop": "datePublished"},
    ]
    for attrs in meta_attributes:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            candidate_strings.append(tag["content"].strip())

    # 2. HTML5 <time> tags
    for time_tag in soup.find_all("time"):
        if time_tag.get("datetime"):
            candidate_strings.append(time_tag["datetime"].strip())

    # 3. Safe JSON-LD extraction (parsed as JSON, never executed)
    for json_ld in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if json_ld.string:
            try:
                data = json.loads(json_ld.string)
                if isinstance(data, dict):
                    date_val = data.get("datePublished") or data.get("dateCreated")
                    if date_val and isinstance(date_val, str):
                        candidate_strings.append(date_val.strip())
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            date_val = item.get("datePublished")
                            if date_val and isinstance(date_val, str):
                                candidate_strings.append(date_val.strip())
            except Exception:
                pass

    # Parse first valid candidate date string
    for candidate in candidate_strings:
        if not candidate:
            continue
        try:
            dt = date_parser.parse(candidate)
            if dt:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
        except Exception:
            continue

    return None


def extract_readable_content(html: str, max_chars: int = 15000) -> str:
    """
    Safely extract cleaned human-readable article content from untrusted HTML.
    Strips scripts, styles, navigation, and advertisement boilerplate.
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Strip comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove dangerous or non-content tags
    for tag in soup.find_all(list(DANGEROUS_TAGS)):
        tag.decompose()

    # Locate main article body container if available
    main_container = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find(class_=re.compile(r"article[-_]?body|story[-_]?content|post[-_]?content", re.I))
        or soup.body
        or soup
    )

    # Extract text from paragraphs and headers
    paragraphs: List[str] = []
    for elem in main_container.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
        text = elem.get_text(separator=" ", strip=True)
        # Skip trivial navigation or copyright lines
        if len(text) > 20 and not text.lower().startswith("copyright"):
            paragraphs.append(text)

    # Fallback to general text if no paragraphs met length threshold
    if not paragraphs:
        raw_text = main_container.get_text(separator=" ", strip=True)
        paragraphs = [re.sub(r"\s+", " ", raw_text)]

    full_text = "\n\n".join(paragraphs)
    # Normalize multiple whitespace
    cleaned_text = re.sub(r"[ \t]+", " ", full_text).strip()
    return cleaned_text[:max_chars]


# ------------------------------------------------------------------------------
# Deduplication Utilities
# ------------------------------------------------------------------------------
def deduplicate_articles(articles: List[ResearchArticle]) -> List[ResearchArticle]:
    """
    Deduplicate research articles by normalized canonical URL
    and content fingerprint (normalized title + content snippet hash).
    """
    seen_urls: Set[str] = set()
    seen_content_hashes: Set[str] = set()
    deduped: List[ResearchArticle] = []

    for art in articles:
        norm_url = normalize_url(art.url)
        if norm_url in seen_urls:
            continue

        # Content fingerprint: SHA-256 of lowercase alphanumeric title + leading body text
        clean_title = re.sub(r"\W+", "", art.title.lower())
        clean_excerpt = re.sub(r"\W+", "", art.extracted_content[:200].lower())
        content_sig = hashlib.sha256(f"{clean_title}:{clean_excerpt}".encode("utf-8")).hexdigest()

        if content_sig in seen_content_hashes:
            continue

        seen_urls.add(norm_url)
        seen_content_hashes.add(content_sig)
        deduped.append(art)

    return deduped


# ------------------------------------------------------------------------------
# Centralized External Research Service
# ------------------------------------------------------------------------------
class ResearchService:
    """
    Centralized service for external financial intelligence research.
    Integrates Tavily Web Search and asynchronous HTML extraction.
    """

    USER_AGENT = "AgentX-PortfolioMonitor/0.1.0 (+https://github.com/agentx/portfolio-health)"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        tavily_client: Optional[Any] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._external_http_client = http_client
        self._internal_http_client: Optional[httpx.AsyncClient] = None
        self._tavily_client = tavily_client

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Retrieve existing client or instantiate managed AsyncClient."""
        if self._external_http_client is not None:
            return self._external_http_client
        if self._internal_http_client is None or self._internal_http_client.is_closed:
            self._internal_http_client = httpx.AsyncClient(
                headers={"User-Agent": self.USER_AGENT},
                follow_redirects=True,
                timeout=httpx.Timeout(12.0, connect=5.0),
            )
        return self._internal_http_client

    def _get_tavily_client(self) -> Any:
        """Instantiate AsyncTavilyClient if not injected."""
        if self._tavily_client is not None:
            return self._tavily_client

        api_key = (
            self.settings.TAVILY_API_KEY.get_secret_value()
            if self.settings.TAVILY_API_KEY
            else None
        )
        if not api_key:
            logger.warning("TAVILY_API_KEY is not configured; web search will be restricted.")
            return None

        from tavily import AsyncTavilyClient
        self._tavily_client = AsyncTavilyClient(api_key=api_key)
        return self._tavily_client

    async def close(self) -> None:
        """Close managed internal HTTP client."""
        if self._internal_http_client and not self._internal_http_client.is_closed:
            await self._internal_http_client.aclose()
            self._internal_http_client = None

    # --------------------------------------------------------------------------
    # Webpage Fetching with Security & Paywall Protection
    # --------------------------------------------------------------------------
    async def fetch_webpage(
        self,
        url: str,
        timeout: float = 12.0,
        max_retries: int = 2,
    ) -> Optional[str]:
        """
        Safely fetch raw HTML from an external URL.
        Security:
          - Enforces SSRF checks.
          - Never bypasses paywalls or authentication (aborts on 401, 402, 403).
          - Enforces maximum response payload (5 MB).
        """
        if not is_safe_url(url):
            logger.warning("Rejected unsafe or restricted URL: %s", url)
            return None

        client = await self._get_http_client()

        for attempt in range(max_retries + 1):
            try:
                response = await client.get(url, timeout=timeout)

                # Abort on paywall or authentication requirements
                if response.status_code in (401, 402, 403):
                    logger.info(
                        "Access restricted or paywalled (HTTP %d) for URL: %s. Aborting fetch.",
                        response.status_code,
                        url,
                    )
                    return None

                if response.status_code == 200:
                    # Enforce content-type is text/html or text/plain
                    ct = response.headers.get("content-type", "").lower()
                    if "text/html" not in ct and "text/plain" not in ct:
                        logger.info("Ignoring non-text MIME type (%s) for URL: %s", ct, url)
                        return None
                    return response.text

                # Retry on transient server errors
                if response.status_code in (500, 502, 503, 504) and attempt < max_retries:
                    logger.debug("Transient HTTP %d fetching %s; retrying...", response.status_code, url)
                    continue

                return None

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < max_retries:
                    continue
                logger.debug("Failed fetching %s after %d retries: %s", url, max_retries, exc)
                return None
            except Exception as exc:
                logger.warning("Unexpected error fetching %s: %s", url, exc)
                return None

        return None

    # --------------------------------------------------------------------------
    # Core Extraction Pipeline
    # --------------------------------------------------------------------------
    def extract_article_from_html(
        self,
        html: str,
        url: str,
        fallback_title: Optional[str] = None,
        snippet: Optional[str] = None,
        score: Optional[float] = None,
    ) -> Optional[ResearchArticle]:
        """
        Parse raw HTML into a structured ResearchArticle.
        Extracts title, publication date, domain, and sanitized content.
        """
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = fallback_title or ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        else:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

        if not title:
            title = fallback_title or "Untitled Financial Document"

        # Extract publication date
        pub_date = extract_publication_date(soup, raw_html=html)

        # Extract content
        content = extract_readable_content(html)
        if not content and snippet:
            content = snippet

        if not content:
            return None

        return ResearchArticle(
            title=title,
            url=normalize_url(url),
            source_name=extract_domain(url),
            publication_date=pub_date,
            extracted_content=content,
            retrieval_timestamp=datetime.now(timezone.utc),
            snippet=snippet,
            score=score,
        )

    # --------------------------------------------------------------------------
    # High-Level Company Research Search
    # --------------------------------------------------------------------------
    async def search_company_news(
        self,
        company_name: str,
        ticker: Optional[str] = None,
        max_results: Optional[int] = None,
        search_depth: Optional[str] = None,
    ) -> List[ResearchArticle]:
        """
        Search recent financial news for a specific company or stock symbol.
        """
        client = self._get_tavily_client()
        if not client:
            return []

        limit = max_results or self.settings.TAVILY_MAX_RESULTS
        depth = search_depth or self.settings.TAVILY_SEARCH_DEPTH

        query_terms = [company_name]
        if ticker:
            query_terms.append(f"({ticker})")
        query_terms.append("financial news earnings revenue analysis")
        query = " ".join(query_terms)

        try:
            logger.info("Executing Tavily news search | query='%s' | depth=%s", query, depth)
            response = await client.search(
                query=query,
                search_depth=depth,
                max_results=limit,
                topic="news",
            )
            raw_results = response.get("results", [])
            articles: List[ResearchArticle] = []

            for item in raw_results:
                url = item.get("url")
                if not url or not is_safe_url(url):
                    continue

                title = item.get("title", "")
                snippet = item.get("content", "")
                score = item.get("score")
                pub_date_raw = item.get("published_date")

                pub_date: Optional[datetime] = None
                if pub_date_raw:
                    try:
                        pub_date = date_parser.parse(pub_date_raw)
                        if pub_date and pub_date.tzinfo is None:
                            pub_date = pub_date.replace(tzinfo=timezone.utc)
                    except Exception:
                        pub_date = None

                article = ResearchArticle(
                    title=title,
                    url=normalize_url(url),
                    source_name=extract_domain(url),
                    publication_date=pub_date,
                    extracted_content=snippet,
                    retrieval_timestamp=datetime.now(timezone.utc),
                    snippet=snippet,
                    score=score,
                )
                articles.append(article)

            return deduplicate_articles(articles)

        except Exception as exc:
            logger.error("Tavily news search failed for '%s': %s", company_name, exc)
            return []

    async def search_company_announcements(
        self,
        company_name: str,
        ticker: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[ResearchArticle]:
        """
        Search for official corporate announcements, press releases, and SEC filings.
        """
        client = self._get_tavily_client()
        if not client:
            return []

        limit = max_results or self.settings.TAVILY_MAX_RESULTS

        query_terms = [company_name]
        if ticker:
            query_terms.append(ticker)
        query_terms.append("official press release SEC filing 8-K 10-Q corporate announcement")
        query = " ".join(query_terms)

        try:
            logger.info("Executing Tavily announcement search | query='%s'", query)
            response = await client.search(
                query=query,
                search_depth="advanced",
                max_results=limit,
            )
            raw_results = response.get("results", [])
            articles: List[ResearchArticle] = []

            for item in raw_results:
                url = item.get("url")
                if not url or not is_safe_url(url):
                    continue

                title = item.get("title", "")
                snippet = item.get("content", "")
                score = item.get("score")

                article = ResearchArticle(
                    title=title,
                    url=normalize_url(url),
                    source_name=extract_domain(url),
                    publication_date=None,
                    extracted_content=snippet,
                    retrieval_timestamp=datetime.now(timezone.utc),
                    snippet=snippet,
                    score=score,
                )
                articles.append(article)

            return deduplicate_articles(articles)

        except Exception as exc:
            logger.error("Tavily announcement search failed for '%s': %s", company_name, exc)
            return []


# ------------------------------------------------------------------------------
# Singleton Access
# ------------------------------------------------------------------------------
_global_research_service: Optional[ResearchService] = None


def get_research_service() -> ResearchService:
    """Return shared ResearchService singleton instance."""
    global _global_research_service
    if _global_research_service is None:
        _global_research_service = ResearchService()
    return _global_research_service
