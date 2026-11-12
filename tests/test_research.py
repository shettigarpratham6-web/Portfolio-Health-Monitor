"""
Portfolio Health Monitor – Portfolio Health Monitor
Unit Tests for External Financial Research Service
Uses Mocked HTTP and Tavily Responses
"""

from datetime import datetime, timezone
import json
import unittest.mock as mock

import httpx
import pytest

from app.core.config import Settings
from app.services.research import (
    ResearchArticle,
    ResearchService,
    deduplicate_articles,
    extract_domain,
    extract_publication_date,
    extract_readable_content,
    is_safe_url,
    normalize_url,
)
from bs4 import BeautifulSoup


@pytest.fixture
def mock_settings():
    return Settings(
        secret_key="test-secret-key-32chars-minimum-length-ok",
        tavily_api_key="tvly-mock-test-key-never-exposed",
        tavily_search_depth="advanced",
        tavily_max_results=5,
    )


# ------------------------------------------------------------------------------
# Test 1: URL Normalization & SSRF Protection
# ------------------------------------------------------------------------------
def test_url_normalization():
    raw_url = "https://WWW.Reuters.COM/technology/article-123/?utm_source=twitter&utm_medium=social&ref=partner#comments"
    normalized = normalize_url(raw_url)
    assert normalized == "https://www.reuters.com/technology/article-123"

    domain = extract_domain(normalized)
    assert domain == "reuters.com"


def test_ssrf_safety_filtering():
    # Dangerous internal or local addresses must be rejected
    assert not is_safe_url("http://localhost:8000/api")
    assert not is_safe_url("http://127.0.0.1/admin")
    assert not is_safe_url("http://169.254.169.254/latest/meta-data")
    assert not is_safe_url("http://10.0.0.5/internal")
    assert not is_safe_url("http://192.168.1.1/router")
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("ftp://ftp.example.com")

    # Public valid web URLs must be accepted
    assert is_safe_url("https://www.sec.gov/edgar/searchedgar/companysearch")
    assert is_safe_url("https://reuters.com/business/finance")
    assert is_safe_url("http://bloomberg.com/news")


# ------------------------------------------------------------------------------
# Test 2: HTML Content Sanitization & Script Stripping
# ------------------------------------------------------------------------------
def test_extract_readable_content_sanitization():
    raw_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Apple Reports Record Q4 Revenue</title>
        <script>alert('Malicious Script Execution Attempt');</script>
        <style>.ad { display: block; }</style>
    </head>
    <body>
        <header><nav><a href="/">Home</a></nav></header>
        <article>
            <h1>Apple Reports Record Q4 Revenue</h1>
            <p>Apple Inc. announced financial results for its fiscal 2026 fourth quarter ended September 26.</p>
            <script>document.cookie = "stolen";</script>
            <iframe src="https://ads.tracker.com"></iframe>
            <p>The Company posted quarterly revenue of $94.9 billion, an increase of 6 percent year over year.</p>
            <aside>Related stories and advertisements</aside>
        </article>
        <footer>Copyright 2026 Apple Inc.</footer>
    </body>
    </html>
    """

    content = extract_readable_content(raw_html)

    # Confirm critical article text is extracted
    assert "Apple Reports Record Q4 Revenue" in content
    assert "fiscal 2026 fourth quarter" in content
    assert "$94.9 billion" in content

    # Confirm dangerous script and ads are completely removed
    assert "alert" not in content
    assert "Malicious Script" not in content
    assert "document.cookie" not in content
    assert "iframe" not in content


# ------------------------------------------------------------------------------
# Test 3: Publication Date Extraction
# ------------------------------------------------------------------------------
def test_extract_publication_date_from_meta_and_time():
    # 1. OpenGraph meta tag
    html_og = '<html><head><meta property="article:published_time" content="2026-10-31T14:30:00Z"></head></html>'
    soup_og = BeautifulSoup(html_og, "html.parser")
    dt_og = extract_publication_date(soup_og, html_og)
    assert dt_og is not None
    assert dt_og.year == 2026
    assert dt_og.month == 10
    assert dt_og.day == 31
    assert dt_og.hour == 14

    # 2. HTML5 time tag
    html_time = '<html><body><time datetime="2026-11-05T09:00:00+00:00">Nov 5, 2026</time></body></html>'
    soup_time = BeautifulSoup(html_time, "html.parser")
    dt_time = extract_publication_date(soup_time, html_time)
    assert dt_time is not None
    assert dt_time.day == 5

    # 3. JSON-LD structured metadata
    html_jsonld = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "Earnings Report",
            "datePublished": "2026-08-15T18:00:00Z"
        }
        </script>
    </head>
    </html>
    """
    soup_jsonld = BeautifulSoup(html_jsonld, "html.parser")
    dt_jsonld = extract_publication_date(soup_jsonld, html_jsonld)
    assert dt_jsonld is not None
    assert dt_jsonld.month == 8
    assert dt_jsonld.day == 15


# ------------------------------------------------------------------------------
# Test 4: Malformed and Broken HTML Handling
# ------------------------------------------------------------------------------
def test_malformed_html_handling():
    # Incomplete / corrupt tags
    broken_html = "<<<html <p>Broken text without closing tags <script>unclosed script"
    content = extract_readable_content(broken_html)
    assert isinstance(content, str)

    # Empty string
    assert extract_readable_content("") == ""
    assert extract_readable_content(None) == ""


# ------------------------------------------------------------------------------
# Test 5: Article Deduplication
# ------------------------------------------------------------------------------
def test_article_deduplication():
    now = datetime.now(timezone.utc)
    art1 = ResearchArticle(
        title="Nvidia Q3 Revenue Surges Past Estimates",
        url="https://reuters.com/tech/nvidia-q3/?utm_source=news",
        source_name="reuters.com",
        extracted_content="Nvidia delivered record quarterly revenue exceeding hyperscaler expectations.",
        retrieval_timestamp=now,
    )
    # Duplicate 1: Same URL with different tracking query param
    art2 = ResearchArticle(
        title="Nvidia Q3 Revenue Surges Past Estimates",
        url="https://reuters.com/tech/nvidia-q3/?utm_source=twitter",
        source_name="reuters.com",
        extracted_content="Nvidia delivered record quarterly revenue exceeding hyperscaler expectations.",
        retrieval_timestamp=now,
    )
    # Duplicate 2: Different syndicated URL but identical title and body content
    art3 = ResearchArticle(
        title="Nvidia Q3 Revenue Surges Past Estimates",
        url="https://finance.yahoo.com/news/nvidia-q3-syndicated",
        source_name="finance.yahoo.com",
        extracted_content="Nvidia delivered record quarterly revenue exceeding hyperscaler expectations.",
        retrieval_timestamp=now,
    )
    # Distinct article
    art4 = ResearchArticle(
        title="AMD Unveils Competing AI Accelerator",
        url="https://bloomberg.com/news/amd-ai-chip",
        source_name="bloomberg.com",
        extracted_content="AMD announced its next-generation MI350 accelerator chip at their datacenter event.",
        retrieval_timestamp=now,
    )

    deduped = deduplicate_articles([art1, art2, art3, art4])
    assert len(deduped) == 2
    assert deduped[0].title == "Nvidia Q3 Revenue Surges Past Estimates"
    assert deduped[1].title == "AMD Unveils Competing AI Accelerator"


# ------------------------------------------------------------------------------
# Test 6: Mocked Tavily News Search
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_search_company_news_mocked(mock_settings):
    mock_tavily = mock.AsyncMock()
    mock_tavily.search.return_value = {
        "results": [
            {
                "title": "Nvidia Announces Blackwell Ultra Architecture",
                "url": "https://www.cnbc.com/2026/11/01/nvidia-blackwell-ultra.html?utm_campaign=feed",
                "content": "Nvidia CEO Jensen Huang unveiled the enhanced Blackwell Ultra GPU platform today.",
                "score": 0.94,
                "published_date": "2026-11-01T15:00:00Z",
            },
            {
                "title": "Semiconductor Sector Gains on Strong Cloud Spending",
                "url": "https://www.reuters.com/markets/semis-rally-2026-11-02",
                "content": "Major chipmakers rallied following upbeat earnings forecasts from cloud providers.",
                "score": 0.88,
                "published_date": "2026-11-02T10:30:00Z",
            },
        ]
    }

    service = ResearchService(settings=mock_settings, tavily_client=mock_tavily)

    results = await service.search_company_news(company_name="Nvidia", ticker="NVDA")

    assert len(results) == 2
    mock_tavily.search.assert_called_once()

    first = results[0]
    assert first.title == "Nvidia Announces Blackwell Ultra Architecture"
    assert first.source_name == "cnbc.com"
    assert first.url == "https://www.cnbc.com/2026/11/01/nvidia-blackwell-ultra.html"
    assert first.publication_date is not None
    assert first.publication_date.year == 2026
    assert first.score == 0.94
    assert "Jensen Huang" in first.extracted_content


# ------------------------------------------------------------------------------
# Test 7: Mocked Tavily Corporate Announcements & Filings
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_search_company_announcements_mocked(mock_settings):
    mock_tavily = mock.AsyncMock()
    mock_tavily.search.return_value = {
        "results": [
            {
                "title": "Apple Inc. Form 8-K Current Report",
                "url": "https://www.sec.gov/ix?doc=/Archives/edgar/data/320193/000032019326000100/aapl-20261105.htm",
                "content": "Item 2.02 Results of Operations and Financial Condition. Apple released financial results.",
                "score": 0.98,
            }
        ]
    }

    service = ResearchService(settings=mock_settings, tavily_client=mock_tavily)

    filings = await service.search_company_announcements(company_name="Apple", ticker="AAPL")

    assert len(filings) == 1
    assert filings[0].source_name == "sec.gov"
    assert "Form 8-K" in filings[0].title


# ------------------------------------------------------------------------------
# Test 8: Webpage Fetching – Paywall and Paywall Status Handling
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_fetch_webpage_aborts_on_paywalls(mock_settings):
    # Simulates HTTP 403 Forbidden or 402 Payment Required paywall
    paywall_resp = httpx.Response(
        status_code=403,
        text="<html><body>Subscription required to view full article</body></html>",
        request=httpx.Request("GET", "https://wsj.com/articles/restricted-article"),
    )

    mock_http = mock.AsyncMock()
    mock_http.get.return_value = paywall_resp

    service = ResearchService(settings=mock_settings, http_client=mock_http)

    content = await service.fetch_webpage("https://wsj.com/articles/restricted-article")
    # Must abort cleanly without attempting bypass
    assert content is None


# ------------------------------------------------------------------------------
# Test 9: Network Failure and Bounded Retries
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_fetch_webpage_retry_and_timeout_recovery(mock_settings):
    # First attempt raises timeout, second attempt returns successful HTML
    success_resp = httpx.Response(
        status_code=200,
        text="<html><body><article><p>Successful content after transient timeout.</p></article></body></html>",
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", "https://reuters.com/article"),
    )

    mock_http = mock.AsyncMock()
    mock_http.get.side_effect = [
        httpx.ConnectTimeout("Connection timed out"),
        success_resp,
    ]

    service = ResearchService(settings=mock_settings, http_client=mock_http)

    html = await service.fetch_webpage("https://reuters.com/article", max_retries=2)
    assert html is not None
    assert "Successful content after transient timeout" in html
    assert mock_http.get.call_count == 2

