"""
api.py
------
FastAPI interface for the Claims Triage Multi-Agent System.

Endpoints:
  GET  /health                   — liveness + Redis connectivity check
  POST /claims                   — submit a claim through the triage pipeline
  GET  /claims/{claim_id}/audit  — fetch the ordered audit trail from Redis
  GET  /fraud-queue              — inspect the fraud review queue

Run with:
    uvicorn api:app --reload
    uvicorn api:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, List, Literal, Optional

import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent / "claims_agent" / ".env")

from claims_agent.configs.logging_config import configure as _configure_logging

_configure_logging()

from claims_agent.agent import claims_triage_agent  # noqa: E402


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connections (Redis, PostgreSQL) are opened lazily per-request.
    yield


app = FastAPI(
    title="Claims Triage API",
    description=(
        "Insurance claims triage pipeline powered by a Google ADK "
        "multi-agent system. Submit a claim and receive an immediate "
        "triage decision covering classification, document checks, "
        "policy validation, and fraud assessment."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

_REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _redis() -> aioredis.Redis:
    return aioredis.from_url(_REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ClaimRequest(BaseModel):
    """
    Structured claim submission.

    Either provide structured fields *or* a `raw_input` string (JSON or
    free-text). When `raw_input` is present all other fields are ignored.
    """

    policy_number: Optional[str] = Field(default=None, examples=["POL-1001"])
    claimant_name: Optional[str] = Field(default=None, examples=["Jane Smith"])
    claim_type: Optional[Literal["auto", "health", "property", "life", "liability"]] = None
    incident_date: Optional[str] = Field(
        default=None,
        description="Date of the incident in YYYY-MM-DD format",
        examples=["2026-04-15"],
    )
    amount_claimed: Optional[float] = Field(default=None, ge=0, examples=[12500.0])
    description: Optional[str] = Field(
        default=None,
        examples=["My car was rear-ended on the highway."],
    )
    documents_provided: List[str] = Field(
        default_factory=list,
        description="Document names already submitted with the claim.",
        examples=[["police_report", "photos_of_damage"]],
    )
    raw_input: Optional[str] = Field(
        default=None,
        description=(
            "Free-text or raw JSON claim input. "
            "When provided, all other fields are ignored."
        ),
    )


class TriageResponse(BaseModel):
    claim_id: str
    session_id: str
    overall_status: str
    urgency: Optional[str] = None
    claim_type: Optional[str] = None
    fraud_risk_score: Optional[float] = None
    fraud_recommendation: Optional[str] = None
    missing_docs: List[str] = []
    policy_violations: List[str] = []
    summary: Optional[str] = None


class AuditEntryOut(BaseModel):
    claim_id: str
    agent_name: str
    timestamp: str
    decision: str
    details: Any


class AuditLogResponse(BaseModel):
    claim_id: str
    entry_count: int
    entries: List[AuditEntryOut]


class FraudQueueResponse(BaseModel):
    queue_length: int
    claim_ids: List[str]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    redis: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _new_claim_id() -> str:
    today = date.today().strftime("%Y%m%d")
    return f"CLM-{today}-{uuid.uuid4().hex[:4].upper()}"


def _build_claim_payload(req: ClaimRequest) -> tuple[str, str]:
    """Return ``(claim_id, claim_json)`` ready to pass to process_claim."""
    if req.raw_input:
        try:
            parsed = json.loads(req.raw_input)
            claim_id = parsed.get("claim_id") or _new_claim_id()
        except (json.JSONDecodeError, AttributeError):
            claim_id = _new_claim_id()
        return claim_id, req.raw_input

    claim_id = _new_claim_id()
    payload = {
        "claim_id": claim_id,
        "policy_number": req.policy_number or "",
        "claimant_name": req.claimant_name or "",
        "claim_type": req.claim_type or "auto",
        "incident_date": req.incident_date or date.today().isoformat(),
        "amount_claimed": req.amount_claimed or 0.0,
        "description": req.description or "",
        "documents_provided": req.documents_provided,
    }
    return claim_id, json.dumps(payload)


def _parse_triage_response(state: dict, session_id: str) -> TriageResponse:
    """Extract the final_decision from the pipeline session state."""
    final = state.get("final_decision")
    if not final:
        raise HTTPException(
            status_code=500,
            detail="Pipeline completed but did not produce a final_decision.",
        )
    try:
        data = json.loads(final) if isinstance(final, str) else final
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not parse pipeline result: {exc}"
        ) from exc

    return TriageResponse(
        claim_id=data.get("claim_id", "unknown"),
        session_id=session_id,
        overall_status=data.get("overall_status", "unknown"),
        urgency=data.get("urgency"),
        claim_type=data.get("claim_type"),
        fraud_risk_score=data.get("fraud_risk_score"),
        fraud_recommendation=data.get("fraud_recommendation"),
        missing_docs=data.get("missing_docs", []),
        policy_violations=data.get("policy_violations", []),
        summary=data.get("summary"),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["Operations"])
async def health_check() -> HealthResponse:
    """Check that the API is up and Redis is reachable."""
    redis_status = "ok"
    try:
        r = _redis()
        await r.ping()
        await r.aclose()
    except Exception as exc:  # noqa: BLE001
        redis_status = f"error: {exc}"

    overall: Literal["ok", "degraded"] = "ok" if redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, redis=redis_status)


@app.post("/claims", response_model=TriageResponse, status_code=202, tags=["Claims"])
async def submit_claim(req: ClaimRequest) -> TriageResponse:
    """
    Submit an insurance claim through the full triage pipeline.

    Accepts structured fields or a `raw_input` string (JSON or free-text).
    Runs the complete 5-stage pipeline (intake → classification →
    document + policy checks → fraud assessment → audit summary) and
    returns the triage decision synchronously.
    """
    claim_id, claim_json = _build_claim_payload(req)
    session_id = f"api_{uuid.uuid4().hex[:12]}"

    try:
        state = await claims_triage_agent.process_claim(
            claim_input=claim_json,
            session_id=session_id,
            user_id="api",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _parse_triage_response(state, session_id)


@app.get(
    "/claims/{claim_id}/audit",
    response_model=AuditLogResponse,
    tags=["Claims"],
)
async def get_audit_log(claim_id: str) -> AuditLogResponse:
    """Fetch the ordered audit trail for a claim from Redis."""
    r = _redis()
    try:
        raw_entries = await r.lrange(f"audit:{claim_id}", 0, -1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Redis error: {exc}") from exc
    finally:
        await r.aclose()

    if not raw_entries:
        raise HTTPException(
            status_code=404,
            detail=f"No audit log found for claim '{claim_id}'.",
        )

    entries: list[AuditEntryOut] = []
    for raw in raw_entries:
        try:
            entry_data = json.loads(raw)
            details = entry_data.get("details", {})
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except (json.JSONDecodeError, TypeError):
                    pass
            entries.append(
                AuditEntryOut(
                    claim_id=entry_data.get("claim_id", claim_id),
                    agent_name=entry_data.get("agent_name", "unknown"),
                    timestamp=entry_data.get("timestamp", ""),
                    decision=entry_data.get("decision", ""),
                    details=details,
                )
            )
        except (json.JSONDecodeError, Exception):  # noqa: BLE001
            continue

    return AuditLogResponse(
        claim_id=claim_id,
        entry_count=len(entries),
        entries=entries,
    )


@app.get("/fraud-queue", response_model=FraudQueueResponse, tags=["Operations"])
async def get_fraud_queue() -> FraudQueueResponse:
    """Inspect all claim IDs currently in the fraud review queue."""
    r = _redis()
    try:
        items = await r.lrange("fraud_review_queue", 0, -1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Redis error: {exc}") from exc
    finally:
        await r.aclose()

    return FraudQueueResponse(queue_length=len(items), claim_ids=items)
