"""
agent.py
--------
ClaimsTriageAgent — orchestrates the full triage pipeline without relying on
ADK's SequentialAgent or ParallelAgent wrappers.

Each stage is driven by a dedicated Runner for the sub-agent, sharing the same
session state so outputs written via output_key are visible downstream.

Pipeline order:
  1. IntakeAgent
  2. ClassificationAgent
  3. DocumentAgent ‖ PolicyAgent  (concurrent via asyncio.gather)
  4. FraudAgent
  5. AuditSummaryAgent

root_agent is still exposed for adk web / adk run entry point.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

from .sessions import RedisSessionService

from .sub_agents import (
    audit_agent,
    classification_agent,
    document_agent,
    fraud_agent,
    intake_agent,
    policy_agent,
)
from .sub_agents.conversational_agent import conversational_agent

logger = logging.getLogger("claims_agent.triage")


class ClaimsTriageAgent:
    """
    Orchestrates the insurance claims triage pipeline through direct async
    calls to each sub-agent, without using ADK's SequentialAgent or
    ParallelAgent.

    Each sub-agent shares the same session_service and session_id, so outputs
    written via output_key are visible to every downstream agent.
    """

    APP_NAME = "claims_triage"

    def __init__(self, session_service: BaseSessionService | None = None) -> None:
        if session_service is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            session_service = RedisSessionService(redis_url=redis_url)
        self.session_service = session_service

        # Pipeline sub-agents
        self.intake_agent = intake_agent
        self.classification_agent = classification_agent
        self.document_agent = document_agent
        self.policy_agent = policy_agent
        self.fraud_agent = fraud_agent
        self.audit_agent = audit_agent

        # Front-door conversational agent (adk web / adk run entry point)
        self._root_agent = conversational_agent

    # -----------------------------------------------------------------------
    # Internal runner helper
    # -----------------------------------------------------------------------

    async def _run_agent(
        self,
        agent: LlmAgent,
        session_id: str,
        user_id: str,
        message: str,
    ) -> str | None:
        """
        Create a Runner for *agent* and drive it with *message*.
        Returns the text of the final response event, or None.
        """
        runner = Runner(
            agent=agent,
            app_name=self.APP_NAME,
            session_service=self.session_service,
        )
        content = types.Content(role="user", parts=[types.Part(text=message)])
        final_text: str | None = None

        logger.info("[Pipeline] %-26s → running", agent.name)
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        logger.info(
                            "[Pipeline] %-26s → TOOL CALL  : %s(%s)",
                            event.author,
                            part.function_call.name,
                            str(part.function_call.args)[:120].replace("\n", " "),
                        )
                    elif hasattr(part, "function_response") and part.function_response:
                        logger.info(
                            "[Pipeline] %-26s ← TOOL RESULT: %s → %s",
                            event.author,
                            part.function_response.name,
                            str(part.function_response.response)[:120].replace("\n", " "),
                        )
                    elif hasattr(part, "text") and part.text and part.text.strip():
                        logger.info(
                            "[Pipeline] %-26s   OUTPUT     : %s",
                            event.author,
                            part.text[:200].replace("\n", " "),
                        )
            if event.is_final_response() and event.content:
                final_text = event.content.parts[0].text.strip()

        logger.info("[Pipeline] %-26s   complete", agent.name)
        return final_text

    # -----------------------------------------------------------------------
    # Pipeline entry point
    # -----------------------------------------------------------------------

    async def process_claim(
        self,
        claim_input: str,
        *,
        session_id: str | None = None,
        user_id: str = "system",
    ) -> dict[str, Any]:
        """
        Run the full triage pipeline and return the final session state dict.

        Stages:
          1. IntakeAgent        — normalise raw input into ClaimIntake
          2. ClassificationAgent — urgency + type classification
          3. DocumentAgent ‖ PolicyAgent — independent checks, run concurrently
          4. FraudAgent          — fraud risk assessment
          5. AuditSummaryAgent   — compile final_decision
        """
        session_id = session_id or f"triage_{uuid.uuid4().hex[:12]}"
        await self.session_service.create_session(
            app_name=self.APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

        logger.info("[Triage] Starting pipeline  session=%s", session_id)
        logger.info("Running Agent %s", self.intake_agent.name)

        # Stage 1 — Intake
        await self._run_agent(self.intake_agent, session_id, user_id, claim_input)

        # Stage 2 — Classification
        logger.info("Running Agent %s", self.classification_agent.name)
        await self._run_agent(
            self.classification_agent,
            session_id,
            user_id,
            "Classify the normalised claim.",
        )

        logger.info("Running Agent %s", self.document_agent.name)
        # Stage 3 — Document check + Policy check (independent, run concurrently)
        await asyncio.gather(
            self._run_agent(
                self.document_agent,
                session_id,
                user_id,
                "Check required documents for the claim.",
            ),
            self._run_agent(
                self.policy_agent,
                session_id,
                user_id,
                "Validate the claim against the policy.",
            ),
        )

        # Stage 4 — Fraud assessment
        logger.info("Running Agent %s", self.fraud_agent.name)
        await self._run_agent(
            self.fraud_agent,
            session_id,
            user_id,
            "Assess the fraud risk of the claim.",
        )

        # Stage 5 — Audit summary
        logger.info("Running Agent %s", self.audit_agent.name)
        await self._run_agent(
            self.audit_agent,
            session_id,
            user_id,
            "Produce the final audit decision.",
        )

        logger.info("[Triage] Pipeline complete  session=%s", session_id)

        session = await self.session_service.get_session(
            app_name=self.APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        return dict(session.state) if session else {}


# ---------------------------------------------------------------------------
# Module-level instances
# ---------------------------------------------------------------------------

# Shared instance used by pipeline_runner_tool and main.py CLI
claims_triage_agent = ClaimsTriageAgent()

# root_agent is the adk web / adk run entry point — the conversational front-door
root_agent = claims_triage_agent._root_agent
