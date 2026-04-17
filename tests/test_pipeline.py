"""
test_pipeline.py
----------------
Unit and integration tests for the Claims Triage multi-agent system.

Tests cover:
  - Pydantic schema validation
  - Tool function logic (document_tools, policy_tools)
  - Redis tools with mocked Redis (no live Redis required)
  - End-to-end pipeline with mocked LLM responses
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from claims_agent.schemas.models import (
    AuditEntry,
    ClaimIntake,
    Classification,
    DocCheckResult,
    FinalDecision,
    FraudAssessment,
    PolicyCheckResult,
)
from claims_agent.tools.document_tools import (
    check_present_documents,
    get_required_documents,
)
from claims_agent.tools.policy_tools import (
    lookup_policy,
    validate_claim_against_policy,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_claim_intake_valid(self):
        claim = ClaimIntake(
            claim_id="CLM-001",
            policy_number="POL-1001",
            claimant_name="John Doe",
            claim_type="auto",
            incident_date="2026-04-15",
            amount_claimed=5000.0,
            description="Car accident on highway.",
            documents_provided=["police_report", "photos_of_damage"],
        )
        assert claim.claim_id == "CLM-001"
        assert claim.amount_claimed == 5000.0

    def test_claim_intake_invalid_type(self):
        with pytest.raises(Exception):
            ClaimIntake(
                claim_id="CLM-001",
                policy_number="POL-1001",
                claimant_name="John Doe",
                claim_type="spaceship",  # invalid
                incident_date="2026-04-15",
                amount_claimed=5000.0,
                description="description",
            )

    def test_fraud_assessment_score_bounds(self):
        with pytest.raises(Exception):
            FraudAssessment(
                claim_id="CLM-001",
                risk_score=1.5,  # > 1.0 — invalid
                fraud_flags=[],
                is_suspicious=True,
                recommendation="reject",
            )

    def test_final_decision_valid(self):
        fd = FinalDecision(
            claim_id="CLM-001",
            overall_status="approved_for_processing",
            urgency="medium",
            claim_type="auto",
            missing_docs=[],
            policy_violations=[],
            fraud_risk_score=0.1,
            fraud_recommendation="proceed",
            summary="Claim is clean and ready for processing.",
            audit_key="audit:CLM-001",
        )
        assert fd.overall_status == "approved_for_processing"


# ---------------------------------------------------------------------------
# Document tool tests
# ---------------------------------------------------------------------------


class TestDocumentTools:
    def test_get_required_documents_auto(self):
        result = get_required_documents("auto")
        assert result["status"] == "success"
        assert "police_report" in result["required_documents"]
        assert "repair_estimate" in result["required_documents"]

    def test_get_required_documents_unknown_type(self):
        result = get_required_documents("spaceship")
        assert result["status"] == "error"

    def test_check_present_documents_all_present(self):
        auto_docs = [
            "police_report",
            "photos_of_damage",
            "repair_estimate",
            "drivers_license",
            "vehicle_registration",
            "insurance_card",
        ]
        result = check_present_documents("auto", json.dumps(auto_docs))
        assert result["status"] == "success"
        assert result["all_present"] is True
        assert len(result["missing_documents"]) == 0

    def test_check_present_documents_missing(self):
        partial_docs = ["police_report", "photos_of_damage"]
        result = check_present_documents("auto", json.dumps(partial_docs))
        assert result["status"] == "success"
        assert result["all_present"] is False
        assert "repair_estimate" in result["missing_documents"]
        assert "drivers_license" in result["missing_documents"]

    def test_check_present_documents_comma_separated(self):
        result = check_present_documents(
            "health", "medical_records, doctor_note, itemised_bill"
        )
        assert result["status"] == "success"
        assert "prescription_receipts" in result["missing_documents"]

    def test_check_present_documents_case_insensitive(self):
        """Document names should match regardless of case."""
        result = check_present_documents("auto", json.dumps(["Police_Report", "PHOTOS_OF_DAMAGE", "Repair_Estimate", "Drivers_License", "Vehicle_Registration", "Insurance_Card"]))
        assert result["all_present"] is True


# ---------------------------------------------------------------------------
# Policy tool tests
# ---------------------------------------------------------------------------


class TestPolicyTools:
    def test_lookup_existing_policy(self):
        result = lookup_policy("POL-1001")
        assert result["status"] == "success"
        assert result["is_active"] is True
        assert result["coverage_limit"] == 50_000.0

    def test_lookup_nonexistent_policy(self):
        result = lookup_policy("POL-FAKE")
        assert result["status"] == "error"

    def test_validate_active_policy_within_limit(self):
        result = validate_claim_against_policy("POL-1001", "auto", 10_000.0)
        assert result["status"] == "success"
        assert result["passed"] is True
        assert len(result["violations"]) == 0

    def test_validate_inactive_policy(self):
        result = validate_claim_against_policy("POL-1003", "property", 5_000.0)
        assert result["status"] == "success"
        assert result["passed"] is False
        assert any("inactive" in v.lower() for v in result["violations"])

    def test_validate_wrong_claim_type(self):
        # POL-1001 covers auto and liability only, not health
        result = validate_claim_against_policy("POL-1001", "health", 1_000.0)
        assert result["passed"] is False
        assert any("not covered" in v.lower() for v in result["violations"])

    def test_validate_amount_exceeds_limit(self):
        result = validate_claim_against_policy("POL-1001", "auto", 100_000.0)
        assert result["passed"] is False
        assert any("exceeds" in v.lower() for v in result["violations"])

    def test_validate_policy_case_insensitive(self):
        result = validate_claim_against_policy("pol-1001", "auto", 5_000.0)
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Redis tool tests (mocked)
# ---------------------------------------------------------------------------


class TestRedisTools:
    @pytest.mark.asyncio
    async def test_write_audit_log_success(self):
        mock_redis = AsyncMock()
        mock_redis.rpush = AsyncMock(return_value=1)
        mock_redis.aclose = AsyncMock()

        with patch(
            "claims_agent.tools.redis_tools._get_redis", return_value=mock_redis
        ):
            from claims_agent.tools.redis_tools import write_audit_log

            result = await write_audit_log(
                claim_id="CLM-001",
                agent_name="TestAgent",
                decision="test:decision",
                details='{"test": "data"}',
            )

        assert result["status"] == "success"
        assert result["redis_key"] == "audit:CLM-001"
        mock_redis.rpush.assert_called_once()
        # Verify the key used
        call_args = mock_redis.rpush.call_args[0]
        assert call_args[0] == "audit:CLM-001"

    @pytest.mark.asyncio
    async def test_push_fraud_queue_success(self):
        mock_redis = AsyncMock()
        mock_redis.rpush = AsyncMock(return_value=1)
        mock_redis.aclose = AsyncMock()

        with patch(
            "claims_agent.tools.redis_tools._get_redis", return_value=mock_redis
        ):
            from claims_agent.tools.redis_tools import push_fraud_queue

            result = await push_fraud_queue(
                claim_id="CLM-003",
                risk_score=0.85,
                fraud_flags='["suspicious_timing", "pressure_language"]',
            )

        assert result["status"] == "success"
        assert result["queue"] == "fraud_review_queue"
        mock_redis.rpush.assert_called_once_with("fraud_review_queue", pytest.approx)

    @pytest.mark.asyncio
    async def test_write_audit_log_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.rpush = AsyncMock(side_effect=Exception("Connection refused"))
        mock_redis.aclose = AsyncMock()

        with patch(
            "claims_agent.tools.redis_tools._get_redis", return_value=mock_redis
        ):
            from claims_agent.tools.redis_tools import write_audit_log

            result = await write_audit_log(
                claim_id="CLM-001",
                agent_name="TestAgent",
                decision="test",
                details="{}",
            )

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_get_audit_log(self):
        mock_redis = AsyncMock()
        sample_entry = json.dumps(
            {
                "claim_id": "CLM-001",
                "agent_name": "ClassificationAgent",
                "timestamp": "2026-04-17T10:00:00Z",
                "decision": "classified:high",
                "details": "{}",
            }
        )
        mock_redis.lrange = AsyncMock(return_value=[sample_entry])
        mock_redis.aclose = AsyncMock()

        with patch(
            "claims_agent.tools.redis_tools._get_redis", return_value=mock_redis
        ):
            from claims_agent.tools.redis_tools import get_audit_log

            result = await get_audit_log("CLM-001")

        assert result["status"] == "success"
        assert len(result["entries"]) == 1
        assert result["entries"][0]["agent_name"] == "ClassificationAgent"
