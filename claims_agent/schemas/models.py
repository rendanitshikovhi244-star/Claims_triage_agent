from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class ClaimIntake(BaseModel):
    """Normalised claim object produced by IntakeAgent."""

    claim_id: str = Field(description="Unique claim identifier, e.g. CLM-001")
    policy_number: str = Field(description="Policyholder's policy number")
    claimant_name: str = Field(description="Full name of the claimant")
    claim_type: Literal["auto", "health", "property", "life", "liability"] = Field(
        description="Category of the insurance claim"
    )
    incident_date: str = Field(
        description="Date of the incident in ISO-8601 format (YYYY-MM-DD)"
    )
    amount_claimed: float = Field(
        description="Total amount claimed in USD", ge=0
    )
    description: str = Field(
        description="Free-text narrative of the incident"
    )
    documents_provided: List[str] = Field(
        default_factory=list,
        description="List of document names already submitted with the claim",
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class Classification(BaseModel):
    """Urgency and type classification produced by ClassificationAgent."""

    claim_id: str
    urgency: Literal["critical", "high", "medium", "low"] = Field(
        description=(
            "critical = life-threatening or catastrophic loss; "
            "high = significant financial impact or time-sensitive; "
            "medium = standard processing; "
            "low = minor claim, no time pressure"
        )
    )
    claim_type: Literal["auto", "health", "property", "life", "liability"]
    reasoning: str = Field(description="Brief rationale for the urgency rating")


# ---------------------------------------------------------------------------
# Document check
# ---------------------------------------------------------------------------


class DocCheckResult(BaseModel):
    """Missing-document assessment produced by DocumentAgent."""

    claim_id: str
    required_docs: List[str] = Field(
        description="All documents required for this claim type"
    )
    missing_docs: List[str] = Field(
        description="Documents that have NOT been submitted yet"
    )
    all_docs_present: bool = Field(
        description="True when no documents are missing"
    )
    request_message: Optional[str] = Field(
        default=None,
        description="Polite message to send the claimant requesting missing docs",
    )


# ---------------------------------------------------------------------------
# Policy check
# ---------------------------------------------------------------------------


class PolicyCheckResult(BaseModel):
    """Policy rule validation produced by PolicyAgent."""

    claim_id: str
    policy_number: str
    is_policy_active: bool
    coverage_limit: float = Field(description="Maximum coverage in USD")
    deductible: float = Field(description="Applicable deductible in USD")
    amount_within_limit: bool
    violations: List[str] = Field(
        default_factory=list,
        description="List of policy rule violations found",
    )
    passed: bool = Field(description="True when no violations are detected")


# ---------------------------------------------------------------------------
# Fraud assessment
# ---------------------------------------------------------------------------


class FraudAssessment(BaseModel):
    """Fraud-risk assessment produced by FraudAgent."""

    claim_id: str
    risk_score: float = Field(
        description="Fraud risk score from 0.0 (clean) to 1.0 (certain fraud)",
        ge=0.0,
        le=1.0,
    )
    fraud_flags: List[str] = Field(
        default_factory=list,
        description="Specific indicators that raised the risk score",
    )
    is_suspicious: bool = Field(
        description="True when risk_score >= 0.7 — triggers fraud review queue"
    )
    recommendation: Literal["proceed", "flag_for_review", "reject"] = Field(
        description=(
            "proceed = continue normal processing; "
            "flag_for_review = route to fraud team; "
            "reject = strong fraud evidence, deny immediately"
        )
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditEntry(BaseModel):
    """Immutable audit record written to Redis for every agent decision."""

    claim_id: str
    agent_name: str
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )
    decision: str = Field(description="Short decision label, e.g. 'classified:high'")
    details: dict = Field(
        default_factory=dict,
        description="Full structured output of the agent as a dict",
    )


class FinalDecision(BaseModel):
    """Complete summary produced by AuditSummaryAgent."""

    claim_id: str
    overall_status: Literal["approved_for_processing", "pending_documents", "policy_violation", "fraud_review", "rejected"]
    urgency: str
    claim_type: str
    missing_docs: List[str] = Field(default_factory=list)
    policy_violations: List[str] = Field(default_factory=list)
    fraud_risk_score: float
    fraud_recommendation: str
    summary: str = Field(description="Human-readable summary of the triage outcome")
    audit_key: str = Field(description="Redis key where the full audit log is stored")
