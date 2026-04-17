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
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

load_dotenv(Path(__file__).parent / "claims_agent" / ".env")

# Import the root agent (SequentialAgent pipeline)
from claims_agent.agent import root_agent


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
    db_url = os.getenv("SESSION_DB_URL", "sqlite+aiosqlite:///./claims_sessions.db")
    session_service = DatabaseSessionService(db_url)

    runner = Runner(
        agent=root_agent,
        app_name="claims_triage",
        session_service=session_service,
    )

    # Use the claim_id from JSON if available, otherwise generate one
    session_id = "session_" + str(hash(claim_input) % 10**9)
    user_id = "claims_processor"

    session = await session_service.create_session(
        app_name="claims_triage",
        user_id=user_id,
        session_id=session_id,
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=claim_input)],
    )

    print(f"\nRunning Claims Triage Pipeline...")
    print(f"Session ID: {session_id}\n")

    final_state: dict = {}

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        # Print agent activity as the pipeline progresses
        if event.author and not event.author.startswith("_"):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        args_preview = str(fc.args)[:200].replace("\n", " ")
                        print(f"  [{event.author}] → TOOL CALL: {fc.name}({args_preview})")
                    elif hasattr(part, "function_response") and part.function_response:
                        fr = part.function_response
                        resp_preview = str(fr.response)[:300].replace("\n", " ")
                        print(f"  [{event.author}] ← TOOL RESULT: {fr.name} → {resp_preview}")
                    elif hasattr(part, "text") and part.text and part.text.strip():
                        print(f"  [{event.author}] OUTPUT:\n{part.text}")

    # Retrieve final session state
    updated_session = await session_service.get_session(
        app_name="claims_triage",
        user_id=user_id,
        session_id=session_id,
    )
    if updated_session:
        final_state = dict(updated_session.state)

    return final_state


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
