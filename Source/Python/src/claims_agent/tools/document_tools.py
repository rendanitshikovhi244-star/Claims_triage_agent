"""
document_tools.py
-----------------
ADK tool functions for determining which documents are required for each claim
type and identifying which documents are missing from a submission.

These are deterministic rule-based functions — no LLM calls inside.
"""

from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# Required documents by claim type
# ---------------------------------------------------------------------------

_REQUIRED_DOCS: dict[str, List[str]] = {
    "auto": [
        "police_report",
        "photos_of_damage",
        "repair_estimate",
        "drivers_license",
        "vehicle_registration",
        "insurance_card",
    ],
    "health": [
        "medical_records",
        "doctor_note",
        "itemised_bill",
        "prescription_receipts",
        "proof_of_insurance",
    ],
    "property": [
        "photos_of_damage",
        "repair_estimate",
        "purchase_receipts",
        "property_deed",
        "fire_or_police_report",
        "proof_of_ownership",
    ],
    "life": [
        "death_certificate",
        "beneficiary_id",
        "original_policy_document",
        "medical_examiner_report",
    ],
    "liability": [
        "incident_report",
        "witness_statements",
        "photos_of_scene",
        "legal_correspondence",
        "proof_of_insurance",
    ],
}


# ---------------------------------------------------------------------------
# Tool: get_required_documents
# ---------------------------------------------------------------------------


def get_required_documents(claim_type: str) -> dict:
    """
    Return the list of documents required for a given insurance claim type.

    Args:
        claim_type (str): One of 'auto', 'health', 'property', 'life', 'liability'.

    Returns:
        dict: status and a list of required document names.
    """
    claim_type = claim_type.lower().strip()
    required = _REQUIRED_DOCS.get(claim_type)
    if required is None:
        return {
            "status": "error",
            "error": f"Unknown claim type '{claim_type}'. Valid types: {list(_REQUIRED_DOCS.keys())}",
        }
    return {"status": "success", "claim_type": claim_type, "required_documents": required}


# ---------------------------------------------------------------------------
# Tool: check_present_documents
# ---------------------------------------------------------------------------


def check_present_documents(
    claim_type: str,
    documents_provided: str,
) -> dict:
    """
    Compare submitted documents against the required list and identify gaps.

    Args:
        claim_type (str): One of 'auto', 'health', 'property', 'life', 'liability'.
        documents_provided (str): JSON array string (or comma-separated list) of
            document names already submitted by the claimant.

    Returns:
        dict: status, required_documents, missing_documents, and all_present flag.
    """
    import json

    claim_type = claim_type.lower().strip()
    required = _REQUIRED_DOCS.get(claim_type)
    if required is None:
        return {
            "status": "error",
            "error": f"Unknown claim type '{claim_type}'.",
        }

    # Parse provided documents — accept JSON array or comma-separated string
    try:
        provided: List[str] = json.loads(documents_provided)
    except (json.JSONDecodeError, TypeError):
        provided = [d.strip() for d in str(documents_provided).split(",") if d.strip()]

    # Normalise to lowercase for comparison
    provided_lower = {d.lower().replace(" ", "_") for d in provided}
    required_lower = {d.lower().replace(" ", "_") for d in required}

    missing = [d for d in required if d.lower().replace(" ", "_") not in provided_lower]

    return {
        "status": "success",
        "claim_type": claim_type,
        "required_documents": required,
        "provided_documents": list(provided),
        "missing_documents": missing,
        "all_present": len(missing) == 0,
    }
