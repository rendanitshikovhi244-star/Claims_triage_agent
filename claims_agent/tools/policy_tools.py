"""
policy_tools.py
---------------
ADK tool functions for validating insurance policy rules against a submitted claim.

Queries the shared PostgreSQL policies table (managed by policy_management_agent).
Connection string is read from DATABASE_URL in claims_agent/.env.

Expected table schema (created by policy_management_agent):
  CREATE TABLE policies (
      policy_number   TEXT PRIMARY KEY,
      holder_name     TEXT,
      is_active       BOOLEAN,
      coverage_limit  NUMERIC,
      deductible      NUMERIC,
      covered_types   TEXT[],
      start_date      DATE,
      end_date        DATE
  );
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/policies")


async def _get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(_DATABASE_URL)


# ---------------------------------------------------------------------------
# Tool: lookup_policy
# ---------------------------------------------------------------------------


async def lookup_policy(policy_number: str) -> dict:
    """
    Retrieve policy details from the PostgreSQL policy database.

    Args:
        policy_number (str): The policyholder's policy number (e.g. 'POL-1001').

    Returns:
        dict: status and policy details (is_active, coverage_limit, deductible,
              covered_claim_types) or an error if policy not found.
    """
    conn = await _get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT is_active, coverage_limit, deductible, covered_types "
            "FROM policies WHERE policy_number = $1",
            policy_number.strip().upper(),
        )
    finally:
        await conn.close()

    if row is None:
        return {
            "status": "error",
            "error": f"Policy '{policy_number}' not found in registry.",
        }

    return {
        "status": "success",
        "policy_number": policy_number,
        "is_active": row["is_active"],
        "coverage_limit": float(row["coverage_limit"]),
        "deductible": float(row["deductible"]),
        "covered_claim_types": list(row["covered_types"]),
    }


# ---------------------------------------------------------------------------
# Tool: validate_claim_against_policy
# ---------------------------------------------------------------------------


async def validate_claim_against_policy(
    policy_number: str,
    claim_type: str,
    amount_claimed: float,
) -> dict:
    """
    Run all policy rules against the claim and return a list of violations.

    Rules checked:
      1. Policy must be active (not lapsed/expired).
      2. Claim type must be covered under the policy.
      3. Amount claimed must not exceed the coverage limit.

    Args:
        policy_number (str): Policyholder's policy number.
        claim_type (str): Type of claim (e.g. 'auto', 'health').
        amount_claimed (float): Total amount being claimed in USD.

    Returns:
        dict: status, violations list, passed flag, coverage_limit, and deductible.
    """
    lookup = await lookup_policy(policy_number)
    if lookup["status"] == "error":
        return lookup

    violations: List[str] = []

    if not lookup["is_active"]:
        violations.append(
            f"Policy {policy_number} is inactive or lapsed — cannot process claim."
        )

    if claim_type.lower() not in [t.lower() for t in lookup["covered_claim_types"]]:
        violations.append(
            f"Claim type '{claim_type}' is not covered under policy {policy_number}. "
            f"Covered types: {lookup['covered_claim_types']}."
        )

    max_payable = lookup["coverage_limit"] - lookup["deductible"]
    if amount_claimed > lookup["coverage_limit"]:
        violations.append(
            f"Amount claimed (${amount_claimed:,.2f}) exceeds coverage limit "
            f"(${lookup['coverage_limit']:,.2f})."
        )

    return {
        "status": "success",
        "policy_number": policy_number,
        "is_policy_active": lookup["is_active"],
        "coverage_limit": lookup["coverage_limit"],
        "deductible": lookup["deductible"],
        "max_payable": max_payable,
        "violations": violations,
        "passed": len(violations) == 0,
    }
