"""
Portfolio Health Monitor
Output Safety & Guardrails Validation
Enforces non-advisory constraints, evidence provenance requirements, validates severity/confidence bounds,
detects unsupported financial predictions, and classifies statement epistemic certainty.
"""

from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from app.guardrails.input_validation import validate_url_safety

logger = logging.getLogger("agentx.guardrails.output")


# ------------------------------------------------------------------------------
# Output Safety Exceptions
# ------------------------------------------------------------------------------
class OutputSafetyError(ValueError):
    """Base exception for generated report or alert safety violations."""
    pass


class InvestmentAdviceViolationError(OutputSafetyError):
    """Raised when an alert, report, or LLM summary contains prohibited investment advice (buy/sell/hold)."""
    pass


class UnsupportedPredictionError(OutputSafetyError):
    """Raised when output contains speculative forward-looking guarantees or certainty claims."""
    pass


class MissingEvidenceError(OutputSafetyError):
    """Raised when an alert or verified claim lacks verifiable primary evidence citations."""
    pass


# ------------------------------------------------------------------------------
# 1. Non-Advisory Mandate (Prohibited Buy / Sell / Hold Recommendations)
# ------------------------------------------------------------------------------
# Regex patterns that signify actionable investment recommendations
PROHIBITED_ADVICE_PATTERNS = [
    re.compile(r"\b(recommend(ation)?|advis(e|ing|ory)?|suggest(ion)?)\s*(is\s+to|to|you\s+to|that\s+you|you)?\s*(buy|sell|hold|accumulate|dump|short)\b", re.IGNORECASE),
    re.compile(r"\b(strong\s+buy|strong\s+sell|must\s+buy|must\s+sell)\b", re.IGNORECASE),
    re.compile(r"\b(buy|sell|hold|accumulate|liquidate|trim)\s+(your\s+)?(shares|position|stock|holdings?)\b", re.IGNORECASE),
    re.compile(r"\b(take\s+profits?|exit\s+(your\s+)?position|enter\s+(a\s+)?position)\b", re.IGNORECASE),
    re.compile(r"\b(price\s+target\s+(is\s+)?guaranteed|surefire\s+(buy|investment))\b", re.IGNORECASE),
    re.compile(r"\b(you\s+should\s+(buy|sell|hold|invest))\b", re.IGNORECASE),
    re.compile(r"\b(safe\s+bet|can't\s+lose|guaranteed\s+return)\b", re.IGNORECASE),
]

MANDATORY_NON_ADVISORY_DISCLAIMER = (
    "Notice: This report provides objective risk and event monitoring only. "
    "It does NOT contain investment recommendations to buy, sell, or hold any financial security."
)


def verify_non_advisory_compliance(text: str) -> None:
    """
    Scans generated output for prohibited investment advice (buy, sell, hold).
    Raises InvestmentAdviceViolationError if detected.
    """
    if not text:
        return
    for pattern in PROHIBITED_ADVICE_PATTERNS:
        match = pattern.search(text)
        if match:
            violation_phrase = match.group(0)
            logger.error("Prohibited investment recommendation detected: '%s'", violation_phrase)
            raise InvestmentAdviceViolationError(
                f"Non-advisory policy violation: Generated content contains actionable financial recommendation ('{violation_phrase}'). "
                "AgentX is strictly an evidence-based monitor and must not provide investment advice."
            )


# ------------------------------------------------------------------------------
# 2. Unsupported Predictions Guard
# ------------------------------------------------------------------------------
UNSUPPORTED_PREDICTION_PATTERNS = [
    re.compile(r"\b(will\s+definitely|guaranteed\s+to|certain\s+to)\s+(skyrocket|crash|double|triple|reach)\b", re.IGNORECASE),
    re.compile(r"\b(100%\s+guaranteed|risk-?free\s+profit)\b", re.IGNORECASE),
    re.compile(r"\b(stock\s+will\s+reach\s+\$\d+)\b", re.IGNORECASE),
    re.compile(r"\b(foolproof\s+strategy|guaranteed\s+growth)\b", re.IGNORECASE),
]


def verify_no_unsupported_predictions(text: str) -> None:
    """
    Verifies that generated reports do not make speculative guarantees or unverified price targets.
    Raises UnsupportedPredictionError if detected.
    """
    if not text:
        return
    for pattern in UNSUPPORTED_PREDICTION_PATTERNS:
        match = pattern.search(text)
        if match:
            prediction_phrase = match.group(0)
            logger.warning("Unsupported predictive claim detected: '%s'", prediction_phrase)
            raise UnsupportedPredictionError(
                f"Output safety violation: Found unsupported speculative prediction ('{prediction_phrase}'). "
                "All financial assessments must be grounded in observable facts and historical disclosures."
            )


# ------------------------------------------------------------------------------
# 3. Epistemic Statement Categorization
# ------------------------------------------------------------------------------
class EpistemicCategory(str, Enum):
    """Classification of statements based on evidentiary rigor."""
    CONFIRMED_FACT = "CONFIRMED_FACT"      # Directly corroborated by official filing or primary release
    REPORTED_CLAIM = "REPORTED_CLAIM"      # Third-party news reporting or executive commentary
    INTERPRETATION = "INTERPRETATION"      # Calculated analytical metrics (HHI, allocation weight, exposure)
    UNCERTAINTY = "UNCERTAINTY"            # Pending litigation, forward-looking statements, speculation


class ClassifiedStatement(BaseModel):
    """Statement with explicit evidentiary classification and confidence."""
    statement: str
    category: EpistemicCategory
    confidence: float = Field(ge=0.0, le=1.0)
    source_url: Optional[str] = None
    attribution: Optional[str] = None


UNCERTAINTY_INDICATORS = [
    re.compile(r"\b(speculat(e|ion|ed)|rumor|alleg(ed|edly)|potential(ly)?|may|might|could)\b", re.IGNORECASE),
    re.compile(r"\b(pending|under\s+investigation|preliminary|unconfirmed)\b", re.IGNORECASE),
    re.compile(r"\b(forward-looking|guidance|projected|forecast)\b", re.IGNORECASE),
]

FACT_INDICATORS = [
    re.compile(r"\b(reported|filed|form\s+10-[kq]|form\s+8-k|sec\s+filing|announced|disclosed)\b", re.IGNORECASE),
    re.compile(r"\b(revenue\s+was|net\s+income|decreased\s+by|increased\s+by|\$\d+(\.\d+)?[mbk]?)\b", re.IGNORECASE),
]

INTERPRETATION_INDICATORS = [
    re.compile(r"\b(concentration|weight|allocation|exposure|calculated|metric|hhi|score)\b", re.IGNORECASE),
]


def classify_statement(
    statement: str,
    source_url: Optional[str] = None,
    source_credibility: float = 0.5,
) -> ClassifiedStatement:
    """
    Categorizes a statement into Confirmed Fact, Reported Claim, Interpretation, or Uncertainty.
    """
    text = statement.strip()
    if not text:
        return ClassifiedStatement(
            statement="",
            category=EpistemicCategory.UNCERTAINTY,
            confidence=0.0,
        )

    # 1. Check uncertainty / speculation indicators first
    for pattern in UNCERTAINTY_INDICATORS:
        if pattern.search(text):
            return ClassifiedStatement(
                statement=text,
                category=EpistemicCategory.UNCERTAINTY,
                confidence=min(0.6, source_credibility),
                source_url=source_url,
                attribution="Identified forward-looking or speculative language.",
            )

    # 2. Check analytical interpretation
    for pattern in INTERPRETATION_INDICATORS:
        if pattern.search(text):
            return ClassifiedStatement(
                statement=text,
                category=EpistemicCategory.INTERPRETATION,
                confidence=0.9,
                source_url=source_url,
                attribution="Derived portfolio calculation.",
            )

    # 3. Check official filing / verified corporate fact
    is_official_source = source_url and ("sec.gov" in source_url or "edgar" in source_url)
    has_fact_marker = any(p.search(text) for p in FACT_INDICATORS)

    if is_official_source or (has_fact_marker and source_credibility >= 0.8):
        return ClassifiedStatement(
            statement=text,
            category=EpistemicCategory.CONFIRMED_FACT,
            confidence=max(0.85, source_credibility),
            source_url=source_url,
            attribution="Corroborated by verified disclosure.",
        )

    # 4. Default to reported claim
    return ClassifiedStatement(
        statement=text,
        category=EpistemicCategory.REPORTED_CLAIM,
        confidence=source_credibility,
        source_url=source_url,
        attribution="Reported by third-party media.",
    )


# ------------------------------------------------------------------------------
# 4. Alert & Report Output Validators
# ------------------------------------------------------------------------------
class ValidatedAlertPayload(BaseModel):
    """Strictly validated alert record ensuring evidence provenance and non-advisory compliance."""
    portfolio_id: str
    ticker: Optional[str] = None
    title: str
    alert_type: str
    severity: str
    message: str
    evidence_sources: List[str]
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        s = v.upper().strip()
        if s not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            raise OutputSafetyError(f"Invalid alert severity '{v}'. Must be LOW, MEDIUM, HIGH, or CRITICAL.")
        return s

    @field_validator("title", "message")
    @classmethod
    def validate_non_advisory(cls, text: str) -> str:
        verify_non_advisory_compliance(text)
        verify_no_unsupported_predictions(text)
        return text.strip()

    @field_validator("evidence_sources")
    @classmethod
    def validate_evidence(cls, sources: List[str]) -> List[str]:
        if not sources:
            raise MissingEvidenceError("Alert safety violation: Every alert must include at least one evidence source URL.")
        validated: List[str] = []
        for src in sources:
            url = validate_url_safety(src)
            if url not in validated:
                validated.append(url)
        return validated


def validate_alert_output(alert: Dict[str, Any]) -> ValidatedAlertPayload:
    """Validate structured alert before persisting or presenting to user."""
    try:
        return ValidatedAlertPayload(**alert)
    except Exception as val_err:
        if hasattr(val_err, "errors"):
            for err in val_err.errors():
                ctx = err.get("ctx", {})
                exc = ctx.get("error") if isinstance(ctx, dict) else None
                if isinstance(exc, OutputSafetyError):
                    raise exc
        if isinstance(val_err, OutputSafetyError):
            raise val_err
        raise OutputSafetyError(str(val_err)) from val_err


def sanitize_and_validate_report(report_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Performs comprehensive safety audit on generated monitoring report:
    1. Checks executive summary for prohibited advice and unsupported predictions.
    2. Validates each contained alert's evidence and bounds.
    3. Guarantees presence of mandatory non-advisory disclaimer.
    """
    exec_summary = report_dict.get("executive_summary", "")
    verify_non_advisory_compliance(exec_summary)
    verify_no_unsupported_predictions(exec_summary)

    # Validate all alerts
    raw_alerts = report_dict.get("alerts", [])
    validated_alerts = []
    for raw_a in raw_alerts:
        a_dict = raw_a if isinstance(raw_a, dict) else raw_a.model_dump()
        val_alert = validate_alert_output(a_dict)
        validated_alerts.append(val_alert.model_dump())

    # Guarantee non-advisory notice
    report_dict["alerts"] = validated_alerts
    report_dict["non_advisory_notice"] = MANDATORY_NON_ADVISORY_DISCLAIMER
    return report_dict
