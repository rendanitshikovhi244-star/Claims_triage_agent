"""
policy_tools.py
---------------
ADK tool functions for validating insurance policy rules against a submitted claim.

In a real system these functions would query a policy database or API.
Here they use a small hardcoded stub registry so the system runs end-to-end
without external dependencies.
"""

from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# Stub policy registry — keyed by policy_number
# ---------------------------------------------------------------------------

_POLICY_DB: dict[str, dict] = {
    "POL-1001": {
        "is_active": True,
        "coverage_limit": 50_000.0,
        "deductible": 500.0,
        "covered_claim_types": ["auto", "liability"],
    },
    "POL-1002": {
        "is_active": True,
        "coverage_limit": 200_000.0,
        "deductible": 1_000.0,
        "covered_claim_types": ["health"],
    },
    "POL-1003": {
        "is_active": False,  # expired / lapsed policy
        "coverage_limit": 100_000.0,
        "deductible": 750.0,
        "covered_claim_types": ["property", "liability"],
    },
    "POL-1004": {
        "is_active": True,
        "coverage_limit": 500_000.0,
        "deductible": 2_500.0,
        "covered_claim_types": ["life"],
    },
    "POL-9999": {
        "is_active": True,
        "coverage_limit": 10_000.0,
        "deductible": 250.0,
        "covered_claim_types": ["auto", "health", "property", "life", "liability"],
    },
}


# ---------------------------------------------------------------------------
# Tool: lookup_policy
# ---------------------------------------------------------------------------


def lookup_policy(policy_number: str) -> dict:
    """
    Retrieve policy details from the policy registry.

    Args:
        policy_number (str): The policyholder's policy number (e.g. 'POL-1001').

    Returns:
        dict: status and policy details (is_active, coverage_limit, deductible,
              covered_claim_types) or an error if policy not found.
    """
    policy = _POLICY_DB.get(policy_number.strip().upper())
    if policy is None:
        return {
            "status": "error",
            "error": f"Policy '{policy_number}' not found in registry.",
        }
    return {"status": "success", "policy_number": policy_number, **policy}


# ---------------------------------------------------------------------------
# Tool: validate_claim_against_policy
# ---------------------------------------------------------------------------


def validate_claim_against_policy(
    policy_number: str,
    claim_type: str,
    amount_claimed: float,
) -> dict:
    """
    Run all policy rules against the claim and return a list of violations.

    Rules checked:
      1. Policy must be active (not lapsed/expired).
      2. Claim type must be covered under the policy.
      3. Amount claimed must not exceed the coverage limit minus the deductible.

    Args:
        policy_number (str): Policyholder's policy number.
        claim_type (str): Type of claim (e.g. 'auto', 'health').
        amount_claimed (float): Total amount being claimed in USD.

    Returns:
        dict: status, violations list, passed flag, coverage_limit, and deductible.
    """
    lookup = lookup_policy(policy_number)
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
