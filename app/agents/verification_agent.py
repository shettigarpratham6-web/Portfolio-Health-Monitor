"""
Portfolio Health Monitor
Research & Verification Agent
Verifies credibility, dates, separates factual evidence from market rumors, and filters duplicates.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from app.agents.discovery_agent import DiscoveredEvent
from app.core.terminal_logger import TerminalLogger
from app.mcp.clients import get_mcp_client
from app.services.llm import get_llm_service

logger = logging.getLogger("agentx.agents.verification")


# ------------------------------------------------------------------------------
# Input & Output Schemas
# ------------------------------------------------------------------------------
class VerificationAgentInput(BaseModel):
    """Input payload for Verification Agent."""
    discovered_events: List[DiscoveredEvent]
    min_credibility_threshold: float = Field(default=0.4, ge=0.0, le=1.0)


class VerifiedFact(BaseModel):
    """Specific verifiable statement extracted from evidence."""
    statement: str
    is_corroborated: bool = True
    confidence: float = Field(ge=0.0, le=1.0)


class LLMVerificationSchema(BaseModel):
    """Internal Pydantic schema for OpenRouter structured analysis."""
    canonical_title: str
    verified_summary: str
    event_type: str = Field(description="EARNINGS, REGULATORY, LEADERSHIP, PRODUCT, MACRO, LITIGATION, or OTHER")
    sentiment: str = Field(description="BULLISH, BEARISH, NEUTRAL, or UNKNOWN")
    verification_status: str = Field(description="VERIFIED, CONTRADICTED, INCONCLUSIVE, or UNVERIFIED")
    credibility_score: float = Field(ge=0.0, le=1.0)
    facts: List[str] = Field(default_factory=list)
    speculative_claims: List[str] = Field(default_factory=list)


class VerifiedEvent(BaseModel):
    """Verified, classified market event with concrete factual evidence."""
    company_name: str
    ticker: str
    company_id: Optional[str] = None
    canonical_title: str
    verified_summary: str
    event_type: str
    sentiment: str
    verification_status: str
    credibility_score: float
    primary_source_url: str
    source_name: str
    published_date: Optional[str] = None
    event_hash: str
    facts: List[VerifiedFact] = Field(default_factory=list)
    speculative_claims: List[str] = Field(default_factory=list)
    is_duplicate: bool = False


class VerificationOutput(BaseModel):
    """Aggregated output from Verification Agent."""
    total_reviewed: int
    total_verified: int
    duplicates_filtered: int
    verified_events: List[VerifiedEvent]
    verification_summary: str


# ------------------------------------------------------------------------------
# Verification Agent
# ------------------------------------------------------------------------------
class VerificationAgent:
    """
    Research & Verification Agent.
    Validates external news items and corporate disclosures.
    Filters duplicates using Analysis MCP and verifies claims using OpenRouter LLM.
    """

    def __init__(self, mcp_client=None, llm_service=None) -> None:
        self.mcp = mcp_client or get_mcp_client()
        self.llm = llm_service or get_llm_service()

    @staticmethod
    def _calibrate_credibility(
        reported_score: float,
        url: str,
        source_name: str,
        facts_count: int,
        speculative_count: int,
    ) -> float:
        """Calibrate raw credibility score based on primary domain authority and facts ratio."""
        low_url = (url or "").lower()
        low_src = (source_name or "").lower()

        base = max(0.0, min(1.0, reported_score))

        # Regulatory & official filings get high credibility baseline
        if "sec.gov" in low_url or "justice.gov" in low_url or ".gov" in low_url:
            base = max(base, 0.95)
        # Established tier-1 financial wires
        elif any(wire in low_url or wire in low_src for wire in ("reuters", "bloomberg", "wsj", "ft.com", "cnbc", "apnews")):
            base = max(base, 0.85)

        # Corroborated facts bonus / speculative claims penalty
        if facts_count >= 2 and speculative_count == 0:
            base = min(1.0, base + 0.05)
        elif speculative_count > facts_count:
            base = max(0.3, base - 0.15)

        return round(base, 2)

    @staticmethod
    def _deterministic_classify(
        title: str, snippet: str, url: str, source_name: str
    ) -> tuple[str, str, str, float]:
        """Classify event type, sentiment, and credibility deterministically using financial keywords."""
        text = f"{title} {snippet}".lower()
        low_url = (url or "").lower()
        low_src = (source_name or "").lower()

        # Domain credibility
        if "sec.gov" in low_url or "justice.gov" in low_url or ".gov" in low_url:
            credibility = 0.95
            status = "VERIFIED"
        elif any(w in low_url or w in low_src for w in ("reuters", "bloomberg", "wsj", "ft.com", "cnbc", "apnews")):
            credibility = 0.85
            status = "VERIFIED"
        elif any(w in low_url or w in low_src for w in ("forbes", "businessinsider", "marketwatch", "barrons", "yahoo")):
            credibility = 0.75
            status = "VERIFIED"
        else:
            credibility = 0.55
            status = "UNVERIFIED"

        # Event type
        if any(k in text for k in ("lawsuit", "sues", "sued", "court", "settlement", "plaintiff", "verdict", "injunction", "subpoena", "allegation")):
            event_type = "LITIGATION"
        elif any(k in text for k in ("antitrust", "sec", "ftc", "doj", "investigation", "probe", "fine", "penalty", "sanction", "compliance", "regulatory", "filing", "10-k", "10-q")):
            event_type = "REGULATORY"
        elif any(k in text for k in ("earnings", "revenue", "eps", "profit", "guidance", "quarterly", "fiscal", "results", "margin", "dividend")):
            event_type = "EARNINGS"
        elif any(k in text for k in ("inflation", "interest rate", "fed", "tariff", "recession", "gdp", "central bank", "currency", "treasury")):
            event_type = "MACRO"
        elif any(k in text for k in ("ceo", "cfo", "resigns", "resignation", "appointed", "executive", "board of directors", "departure", "management")):
            event_type = "LEADERSHIP"
        elif any(k in text for k in ("launch", "chip", "recall", "delay", "patent", "unveils", "discontinuation", "release", "product")):
            event_type = "PRODUCT"
        else:
            event_type = "OTHER"

        # Sentiment
        bearish_keywords = ("plunge", "drop", "drops", "miss", "misses", "investigation", "sued", "lawsuit", "fine", "loss", "losses", "decline", "warns", "slump", "fall", "falls", "downgrade", "probe", "violation", "antitrust")
        bullish_keywords = ("beat", "beats", "surge", "surges", "growth", "record", "jump", "rallies", "rally", "upgrade", "outperform", "soars", "gain", "gains", "profit surge", "exceeds", "expansion")

        bear_count = sum(1 for k in bearish_keywords if k in text)
        bull_count = sum(1 for k in bullish_keywords if k in text)

        if bear_count > bull_count:
            sentiment = "BEARISH"
        elif bull_count > bear_count:
            sentiment = "BULLISH"
        else:
            sentiment = "NEUTRAL"

        return event_type, sentiment, status, credibility

    @traceable(name="Research & Verification Agent", run_type="chain")
    async def run(self, input_data: VerificationAgentInput) -> VerificationOutput:
        """
        Execute verification workflow across discovered events.
        1. Checks duplicates via Analysis MCP tool.
        2. Applies LLM fact vs. speculation separation and credibility scoring.
        3. Generates deterministic event hashes.
        """
        events = input_data.discovered_events
        logger.info("Executing Verification Agent on %d discovered events", len(events))

        verified_events: List[VerifiedEvent] = []
        duplicates_count = 0
        seen_hashes: set[str] = set()

        for ev in events:
            # 1. Duplicate check via Analysis MCP tool
            dup_res = await self.mcp.call_tool(
                tool_name="detect_duplicate_events",
                arguments={
                    "candidate_title": ev.title,
                    "candidate_summary": ev.snippet,
                    "company_id": ev.company_id,
                    "candidate_event_type": ev.event_category,
                },
                server_name="analysis",
            )
            canonical_hash = dup_res.get("canonical_hash") or hashlib.sha256(
                f"{ev.ticker}:{ev.title.lower()}".encode("utf-8")
            ).hexdigest()

            if dup_res.get("is_duplicate") or canonical_hash in seen_hashes:
                logger.info("Filtered duplicate event: '%s' (%s)", ev.title, ev.ticker)
                TerminalLogger.log_agent_step(f"↳ [{ev.ticker}] Filtered duplicate event: \"{ev.title[:55]}\"")
                duplicates_count += 1
                continue

            seen_hashes.add(canonical_hash)

            # 2. OpenRouter Structured Verification
            system_prompt = (
                "You are an evidence verification analyst in financial intelligence. "
                "Your objective is to separate verifiable facts from speculation, rumors, and unsubstantiated claims. "
                "Assess source credibility (0.0 to 1.0). High credibility: official filings, audited statements. "
                "Medium credibility: established news agencies (Reuters, Bloomberg, WSJ). "
                "Low credibility: anonymous blogs, social media commentary. "
                "Do NOT provide investment advice or recommendations."
            )
            user_prompt = (
                f"Analyze this candidate document for {ev.company_name} ({ev.ticker}):\n"
                f"Title: {ev.title}\n"
                f"Source: {ev.source_name} ({ev.url})\n"
                f"Published Date: {ev.publication_date}\n"
                f"Content Snippet: {ev.snippet}\n\n"
                f"Extract facts, isolate speculation, and classify verification status."
            )

            TerminalLogger.log_api_call("OpenRouter LLM", f"Verification for [{ev.ticker}] \"{ev.title[:50]}\"", endpoint_or_model="generate_structured")

            try:
                analysis: LLMVerificationSchema = await self.llm.generate_structured(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_model=LLMVerificationSchema,
                    temperature=0.1,
                )

                # Cross-calibrate credibility score against domain authority
                norm_credibility = self._calibrate_credibility(
                    reported_score=analysis.credibility_score,
                    url=ev.url,
                    source_name=ev.source_name,
                    facts_count=len(analysis.facts),
                    speculative_count=len(analysis.speculative_claims),
                )

                if norm_credibility < input_data.min_credibility_threshold:
                    logger.info("Skipping low-credibility event (score=%.2f): '%s'", norm_credibility, ev.title)
                    TerminalLogger.log_agent_step(f"↳ [{ev.ticker}] Skipped low credibility ({norm_credibility:.2f} < {input_data.min_credibility_threshold}): \"{ev.title[:50]}\"", level="warn")
                    continue

                facts_list = [
                    VerifiedFact(statement=f_str, is_corroborated=True, confidence=norm_credibility)
                    for f_str in analysis.facts
                ]

                TerminalLogger.log_agent_step(
                    f"↳ [{ev.ticker}] Verified: Sentiment={analysis.sentiment} | "
                    f"Credibility={norm_credibility*100:.0f}% | "
                    f"Status={analysis.verification_status} | "
                    f"Facts={len(facts_list)} | Speculative={len(analysis.speculative_claims)}"
                )

                verified_event = VerifiedEvent(
                    company_name=ev.company_name,
                    ticker=ev.ticker,
                    company_id=ev.company_id,
                    canonical_title=analysis.canonical_title or ev.title,
                    verified_summary=analysis.verified_summary or ev.snippet,
                    event_type=analysis.event_type.upper(),
                    sentiment=analysis.sentiment.upper(),
                    verification_status=analysis.verification_status.upper(),
                    credibility_score=norm_credibility,
                    primary_source_url=ev.url,
                    source_name=ev.source_name,
                    published_date=ev.publication_date,
                    event_hash=canonical_hash,
                    facts=facts_list,
                    speculative_claims=analysis.speculative_claims,
                    is_duplicate=False,
                )
                verified_events.append(verified_event)

            except Exception as exc:
                logger.warning("LLM verification failed for '%s'; using deterministic fallback: %s", ev.title, exc)
                # Robust data-driven fallback based on domain authority and financial lexicon
                fb_event_type, fb_sentiment, fb_status, fb_credibility = self._deterministic_classify(
                    title=ev.title,
                    snippet=ev.snippet or "",
                    url=ev.url or "",
                    source_name=ev.source_name or "",
                )

                if fb_credibility < input_data.min_credibility_threshold:
                    continue

                snippet_clean = (ev.snippet or ev.title)[:200]
                verified_event = VerifiedEvent(
                    company_name=ev.company_name,
                    ticker=ev.ticker,
                    company_id=ev.company_id,
                    canonical_title=ev.title,
                    verified_summary=ev.snippet or ev.title,
                    event_type=fb_event_type,
                    sentiment=fb_sentiment,
                    verification_status=fb_status,
                    credibility_score=fb_credibility,
                    primary_source_url=ev.url,
                    source_name=ev.source_name,
                    published_date=ev.publication_date,
                    event_hash=canonical_hash,
                    facts=[VerifiedFact(statement=snippet_clean, is_corroborated=(fb_status == "VERIFIED"), confidence=fb_credibility)],
                    speculative_claims=[],
                    is_duplicate=False,
                )
                verified_events.append(verified_event)

        summary = (
            f"Verification complete: {len(verified_events)} events verified, "
            f"{duplicates_count} duplicates removed from {len(events)} candidate documents."
        )

        return VerificationOutput(
            total_reviewed=len(events),
            total_verified=len(verified_events),
            duplicates_filtered=duplicates_count,
            verified_events=verified_events,
            verification_summary=summary,
        )

