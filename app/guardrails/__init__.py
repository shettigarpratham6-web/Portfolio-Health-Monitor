"""
Portfolio Health Monitor
Guardrails Module
Exports input and output safety validation, prompt injection defense, SSRF filtering,
and non-advisory compliance enforcers.
"""

from app.guardrails.input_validation import (
    MaliciousInputError,
    PromptInjectionDetectedError,
    SanitizedResearchContent,
    SecurityValidationError,
    SSRFAttemptError,
    ThreatLevel,
    ValidatedMonitoringRequest,
    detect_prompt_injection,
    detect_sql_injection,
    sanitize_external_research_content,
    validate_mcp_arguments,
    validate_monitoring_request,
    validate_url_safety,
)
from app.guardrails.output_validation import (
    ClassifiedStatement,
    EpistemicCategory,
    InvestmentAdviceViolationError,
    MANDATORY_NON_ADVISORY_DISCLAIMER,
    MissingEvidenceError,
    OutputSafetyError,
    UnsupportedPredictionError,
    ValidatedAlertPayload,
    classify_statement,
    sanitize_and_validate_report,
    validate_alert_output,
    verify_no_unsupported_predictions,
    verify_non_advisory_compliance,
)

__all__ = [
    # Input Guardrails
    "SecurityValidationError",
    "PromptInjectionDetectedError",
    "MaliciousInputError",
    "SSRFAttemptError",
    "ThreatLevel",
    "ValidatedMonitoringRequest",
    "SanitizedResearchContent",
    "validate_monitoring_request",
    "validate_mcp_arguments",
    "validate_url_safety",
    "detect_prompt_injection",
    "detect_sql_injection",
    "sanitize_external_research_content",
    # Output Guardrails
    "OutputSafetyError",
    "InvestmentAdviceViolationError",
    "UnsupportedPredictionError",
    "MissingEvidenceError",
    "MANDATORY_NON_ADVISORY_DISCLAIMER",
    "EpistemicCategory",
    "ClassifiedStatement",
    "ValidatedAlertPayload",
    "verify_non_advisory_compliance",
    "verify_no_unsupported_predictions",
    "classify_statement",
    "validate_alert_output",
    "sanitize_and_validate_report",
]

