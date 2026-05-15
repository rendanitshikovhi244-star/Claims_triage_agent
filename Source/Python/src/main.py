"""
main.py
-------
CLI entrypoint for the Claims Triage Multi-Agent System.

Usage:
    # Run a claim from a JSON file
    python main.py sample_claims/claim_auto_001.json

    # Run a claim from a JSON string
    python main.py '{"claim_id": "CLM-001", "description": "My car was hit..."}'

    # Run free-text intake
    python main.py "My roof was destroyed in a storm last night. Policy POL-1001."

The pipeline runs synchronously and prints a structured final decision to stdout.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure Unicode output works correctly on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "claims_agent" / ".env")

from claims_agent.configs.logging_config import configure as _configure_logging
_configure_logging()

from claims_agent.agent import claims_triage_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_claim_input(arg: str) -> str:
    """
    Accept a file path, a JSON string, or a plain-text description.
    Returns the raw string that will be sent as the user message to the pipeline.
    """
    path = Path(arg)
    if path.exists() and path.suffix == ".json":
        return path.read_text(encoding="utf-8")
    # Treat argument as a literal string (JSON or free-text)
    return arg


def _pretty_print_result(state: dict) -> None:
    """Print a concise summary of the pipeline result."""
    final = state.get("final_decision")
    if final:
        try:
            data = json.loads(final) if isinstance(final, str) else final
            print("\n" + "=" * 60)
            print("CLAIMS TRIAGE RESULT")
            print("=" * 60)
            print(f"Claim ID      : {data.get('claim_id', 'N/A')}")
            print(f"Status        : {data.get('overall_status', 'N/A').upper()}")
            print(f"Urgency       : {data.get('urgency', 'N/A')}")
            print(f"Claim Type    : {data.get('claim_type', 'N/A')}")
            print(f"Fraud Score   : {data.get('fraud_risk_score', 'N/A')}")
            print(f"Fraud Action  : {data.get('fraud_recommendation', 'N/A')}")
            missing = data.get("missing_docs", [])
            if missing:
                print(f"Missing Docs  : {', '.join(missing)}")
            violations = data.get("policy_violations", [])
            if violations:
                print("Policy Issues :")
                for v in violations:
                    print(f"  - {v}")
            print(f"\nSummary: {data.get('summary', '')}")
            print(f"\nAudit Log Key : {data.get('audit_key', 'N/A')}")
            print("=" * 60 + "\n")
        except Exception:
            print("\nFinal decision (raw):")
            print(final)
    else:
        print("\n[WARNING] No final_decision found in session state.")
        print("Session state keys:", list(state.keys()))


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------


async def run_pipeline(claim_input: str) -> dict:
    """
    Execute the full claims triage pipeline for a single claim.

    Args:
        claim_input: Raw claim data — JSON string, file path, or free-text.

    Returns:
        The final session state dict after the pipeline completes.
    """
    session_id = "session_" + str(hash(claim_input) % 10**9)

    print(f"\nRunning Claims Triage Pipeline...")
    print(f"Session ID: {session_id}\n")

    return await claims_triage_agent.process_claim(
        claim_input=claim_input,
        session_id=session_id,
        user_id="claims_processor",
    )


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python main.py <path/to/claim.json>\n"
            "  python main.py '<json string>'\n"
            "  python main.py 'Free-text claim description...'\n"
        )
        sys.exit(1)

    raw_input = _load_claim_input(sys.argv[1])
    final_state = asyncio.run(run_pipeline(raw_input))
    _pretty_print_result(final_state)


if __name__ == "__main__":
    main()
