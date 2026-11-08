"""
AgentX – Portfolio Health Monitor
Research & Verification Agent
Verifies credibility, dates, separates factual evidence from market rumors, and filters duplicates.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from app.agents.discovery_agent import DiscoveredEvent
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

            try:
                analysis: LLMVerificationSchema = await self.llm.generate_structured(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_model=LLMVerificationSchema,
                    temperature=0.1,
                )

                if analysis.credibility_score < input_data.min_credibility_threshold:
                    logger.info("Skipping low-credibility event (score=%.2f): '%s'", analysis.credibility_score, ev.title)
                    continue

                facts_list = [
                    VerifiedFact(statement=f_str, is_corroborated=True, confidence=analysis.credibility_score)
                    for f_str in analysis.facts
                ]

                verified_event = VerifiedEvent(
                    company_name=ev.company_name,
                    ticker=ev.ticker,
                    company_id=ev.company_id,
                    canonical_title=analysis.canonical_title or ev.title,
                    verified_summary=analysis.verified_summary or ev.snippet,
                    event_type=analysis.event_type.upper(),
                    sentiment=analysis.sentiment.upper(),
                    verification_status=analysis.verification_status.upper(),
                    credibility_score=analysis.credibility_score,
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
                # Fallback to deterministic verification when LLM generation is unavailable
                verified_event = VerifiedEvent(
                    company_name=ev.company_name,
                    ticker=ev.ticker,
                    company_id=ev.company_id,
                    canonical_title=ev.title,
                    verified_summary=ev.snippet or ev.title,
                    event_type="OTHER",
                    sentiment="NEUTRAL",
                    verification_status="UNVERIFIED",
                    credibility_score=0.6 if "sec.gov" in ev.url else 0.5,
                    primary_source_url=ev.url,
                    source_name=ev.source_name,
                    published_date=ev.publication_date,
                    event_hash=canonical_hash,
                    facts=[VerifiedFact(statement=ev.snippet[:150], is_corroborated=False, confidence=0.5)],
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

