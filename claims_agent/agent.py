"""
agent.py
--------
Defines two agents:

  pipeline_agent  — the SequentialAgent triage pipeline (used by main.py CLI
                    and called internally by the conversational agent's tools).

  root_agent      — ClaimsAssistant, the conversational front-door agent that
                    is the entry point for `adk run` and `adk web`.

Pipeline order (SequentialAgent):
  IntakeAgent
  → ClassificationAgent
  → ParallelAgent [DocumentAgent ‖ PolicyAgent]
  → FraudAgent
  → AuditSummaryAgent
"""

from __future__ import annotations

from google.adk.agents import ParallelAgent, SequentialAgent

from .sub_agents import (
    audit_agent,
    classification_agent,
    document_agent,
    fraud_agent,
    intake_agent,
    policy_agent,
)
from .sub_agents.conversational_agent import conversational_agent

# Run document and policy checks concurrently — they are independent of each other
compliance_check = ParallelAgent(
    name="ComplianceCheck",
    description="Runs document validation and policy rule checks in parallel.",
    sub_agents=[document_agent, policy_agent],
)

# The full triage pipeline — used by main.py CLI and by pipeline_runner_tool
pipeline_agent = SequentialAgent(
    name="ClaimsTriagePipeline",
    description=(
        "End-to-end insurance claims triage pipeline: intake → classification → "
        "document & policy check → fraud assessment → audit summary."
    ),
    sub_agents=[
        intake_agent,
        classification_agent,
        compliance_check,
        fraud_agent,
        audit_agent,
    ],
)

# root_agent is the adk web / adk run entry point — the conversational agent
root_agent = conversational_agent
