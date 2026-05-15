"""
pipeline_runner_tool.py
-----------------------
Tools used by ClaimsAssistant (the conversational agent) to trigger the
internal triage pipeline and to resubmit claims with additional documents.

Two tools are exposed:
  submit_claim              — first submission, runs the full pipeline
  resubmit_with_documents   — resubmit after user provides missing documents

The triage SequentialAgent (pipeline_agent) is imported lazily inside each
function to avoid a circular import:
  agent.py  ←  conversational_agent  ←  this file  ←→ [lazy] agent.py
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date
from pathlib import Path

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

logger = logging.getLogger("claims_agent.pipeline")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(_REDIS_URL, decode_responses=True)


def _format_result(state: dict) -> str:
    """Convert pipeline session state to a human-readable summary string."""
    final = state.get("final_decision")
    if not final:
        return "The triage pipeline did not produce a result. Please try again."
    try:
        data = json.loads(final) if isinstance(final, str) else final
        status = data.get("overall_status", "unknown").upper().replace("_", " ")
        lines = [
            f"Claim ID    : {data.get('claim_id', 'N/A')}",
            f"Status      : {status}",
            f"Urgency     : {data.get('urgency', 'N/A')}",
            f"Claim Type  : {data.get('claim_type', 'N/A')}",
            f"Fraud Score : {data.get('fraud_risk_score', 'N/A')} "
            f"({data.get('fraud_recommendation', 'N/A')})",
        ]
        missing = data.get("missing_docs", [])
        if missing:
            lines.append(f"Missing Docs: {', '.join(missing)}")
        violations = data.get("policy_violations", [])
        if violations:
            lines.append("Policy Issues: " + "; ".join(violations))
        lines.append(f"\nSummary: {data.get('summary', '')}")
        return "\n".join(lines)
    except Exception:
        return f"Pipeline completed. Raw result: {final}"


async def _run_pipeline_internal(claim_json: str) -> dict:
    """Delegate to ClaimsTriageAgent.process_claim and return the final state."""
    # Lazy import — avoids circular dependency at module load time
    from claims_agent.agent import claims_triage_agent  # noqa: PLC0415

    session_id = f"internal_{uuid.uuid4().hex[:12]}"
    logger.info("[Pipeline] Starting triage pipeline (session=%s)", session_id)

    state = await claims_triage_agent.process_claim(
        claim_input=claim_json,
        session_id=session_id,
        user_id="conversational_agent",
    )

    logger.info("[Pipeline] Pipeline complete (session=%s)", session_id)
    return state


# ---------------------------------------------------------------------------
# Tool: submit_claim
# ---------------------------------------------------------------------------


async def submit_claim(
    policy_number: str,
    claimant_name: str,
    claim_type: str,
    incident_date: str,
    amount_claimed: float,
    description: str,
    documents_provided: str = "",
) -> str:
    """
    Submit an insurance claim through the full triage pipeline.

    Runs intake → classification → document check → policy check →
    fraud assessment → audit summary and returns the triage decision.
    The claim data is stored in Redis so it can be retrieved for resubmission
    without asking the user to repeat their information.

    Args:
        policy_number: The claimant's policy number (e.g. POL-1001).
        claimant_name: Full name of the claimant.
        claim_type: One of: auto, health, property, life, liability.
        incident_date: Date of the incident in YYYY-MM-DD format.
        amount_claimed: Estimated claim amount in USD.
        description: Free-text description of the incident.
        documents_provided: Comma-separated list of document names already
            provided (e.g. "police_report,photos_of_damage"). Pass an empty
            string if none are available yet.

    Returns:
        A plain-text string starting with CLAIM_ID:<id> followed by the
        formatted triage result.
    """
    today = date.today().strftime("%Y%m%d")
    claim_id = f"CLM-{today}-{uuid.uuid4().hex[:4].upper()}"

    docs = (
        [d.strip() for d in documents_provided.split(",") if d.strip()]
        if documents_provided
        else []
    )

    claim_data = {
        "claim_id": claim_id,
        "policy_number": policy_number,
        "claimant_name": claimant_name,
        "claim_type": claim_type,
        "incident_date": incident_date,
        "amount_claimed": float(amount_claimed),
        "description": description,
        "documents_provided": docs,
    }

    # Persist claim data in Redis (24 h TTL) so resubmission doesn't re-ask
    r = _get_redis()
    try:
        await r.set(
            f"claim_data:{claim_id}",
            json.dumps(claim_data),
            ex=86400,
        )
    finally:
        await r.aclose()

    state = await _run_pipeline_internal(json.dumps(claim_data))
    return f"CLAIM_ID:{claim_id}\n" + _format_result(state)


# ---------------------------------------------------------------------------
# Tool: resubmit_with_documents
# ---------------------------------------------------------------------------


async def resubmit_with_documents(
    claim_id: str,
    new_documents: str,
) -> str:
    """
    Resubmit a claim with additional documents to clear a pending_documents status.

    Retrieves the original claim from Redis, merges the newly provided
    documents into the list, and re-runs the full triage pipeline.

    Args:
        claim_id: The claim ID returned by the original submit_claim call
            (format: CLM-YYYYMMDD-XXXX).
        new_documents: Comma-separated list of document names now being
            provided (e.g. "vehicle_registration,insurance_card").

    Returns:
        A plain-text string with the updated triage result. If the new
        documents resolve all gaps, the status should change from
        PENDING DOCUMENTS to APPROVED FOR PROCESSING.
    """
    r = _get_redis()
    try:
        raw = await r.get(f"claim_data:{claim_id}")
        if not raw:
            return (
                f"No claim data found for {claim_id}. "
                "The data may have expired (24 h limit) or the ID is incorrect."
            )

        claim_data = json.loads(raw)

        # Merge new documents with existing ones (dedup, sorted)
        existing: set[str] = set(claim_data.get("documents_provided", []))
        new_docs: set[str] = {d.strip() for d in new_documents.split(",") if d.strip()}
        claim_data["documents_provided"] = sorted(existing | new_docs)

        # Update the stored claim data with the merged doc list
        await r.set(
            f"claim_data:{claim_id}",
            json.dumps(claim_data),
            ex=86400,
        )
    finally:
        await r.aclose()

    state = await _run_pipeline_internal(json.dumps(claim_data))
    return f"CLAIM_ID:{claim_id}\n" + _format_result(state)
