"""
redis_tools.py
--------------
ADK tool functions for writing to the audit log and fraud review queue in Redis.

The functions are plain Python callables with typed signatures and docstrings so
that Google ADK auto-generates correct tool schemas for the LLM.

Redis keys used:
  audit:{claim_id}   — LIST of JSON-serialised AuditEntry objects (append-only)
  fraud_review_queue — LIST of claim IDs pending human fraud review
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

_REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _get_redis() -> aioredis.Redis:
    """Return a lazily-created Redis client (connection pool shared per process)."""
    return aioredis.from_url(_REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# Tool: write_audit_log
# ---------------------------------------------------------------------------


async def write_audit_log(
    claim_id: str,
    agent_name: str,
    decision: str,
    details: str,
) -> dict:
    """
    Append an audit entry to the Redis audit log for a claim.

    Each call pushes a JSON record to the Redis list key ``audit:{claim_id}``.
    This creates an immutable, ordered audit trail of every agent decision.

    Args:
        claim_id (str): The unique claim identifier (e.g. 'CLM-001').
        agent_name (str): Name of the agent recording this entry.
        decision (str): Short decision label (e.g. 'classified:high', 'docs:missing').
        details (str): JSON string with the full structured output of the agent.

    Returns:
        dict: status ('success' or 'error') and the Redis key where the log lives.
    """
    redis_client = _get_redis()
    try:
        entry = {
            "claim_id": claim_id,
            "agent_name": agent_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "decision": decision,
            "details": details,
        }
        redis_key = f"audit:{claim_id}"
        await redis_client.rpush(redis_key, json.dumps(entry))
        return {"status": "success", "redis_key": redis_key}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    finally:
        await redis_client.aclose()


# ---------------------------------------------------------------------------
# Tool: push_fraud_queue
# ---------------------------------------------------------------------------


async def push_fraud_queue(
    claim_id: str,
    risk_score: float,
    fraud_flags: str,
) -> dict:
    """
    Push a suspicious claim onto the fraud review queue in Redis.

    Adds the claim ID to the Redis list ``fraud_review_queue`` so that the
    fraud investigation team can consume items from the queue.

    Args:
        claim_id (str): The unique claim identifier that should be reviewed.
        risk_score (float): Fraud risk score (0.0–1.0) that triggered escalation.
        fraud_flags (str): JSON array string listing the fraud indicators found.

    Returns:
        dict: status and queue length after the push.
    """
    redis_client = _get_redis()
    try:
        payload = json.dumps(
            {
                "claim_id": claim_id,
                "risk_score": risk_score,
                "fraud_flags": fraud_flags,
                "queued_at": datetime.utcnow().isoformat() + "Z",
            }
        )
        queue_len = await redis_client.rpush("fraud_review_queue", payload)
        return {
            "status": "success",
            "queue": "fraud_review_queue",
            "queue_length": queue_len,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    finally:
        await redis_client.aclose()


# ---------------------------------------------------------------------------
# Tool: get_audit_log
# ---------------------------------------------------------------------------


async def get_audit_log(claim_id: str) -> dict:
    """
    Retrieve all audit entries for a specific claim from Redis.

    Args:
        claim_id (str): The claim whose audit trail you want to inspect.

    Returns:
        dict: status, claim_id, and a list of audit entry dicts.
    """
    redis_client = _get_redis()
    try:
        redis_key = f"audit:{claim_id}"
        raw_entries = await redis_client.lrange(redis_key, 0, -1)
        entries = [json.loads(e) for e in raw_entries]
        return {"status": "success", "claim_id": claim_id, "entries": entries}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    finally:
        await redis_client.aclose()
