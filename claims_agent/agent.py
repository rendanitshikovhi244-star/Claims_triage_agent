"""
agent.py
--------
Defines `root_agent` — the entry point required by `adk run` and `adk web`.

Pipeline (SequentialAgent):
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

# Run document and policy checks concurrently — they are independent of each other
compliance_check = ParallelAgent(
    name="ComplianceCheck",
    description="Runs document validation and policy rule checks in parallel.",
    sub_agents=[document_agent, policy_agent],
)

# The full triage pipeline
root_agent = SequentialAgent(
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
