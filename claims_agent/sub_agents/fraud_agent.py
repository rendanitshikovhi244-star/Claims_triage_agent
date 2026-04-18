"""
fraud_agent.py
--------------
FraudAgent — fourth sequential stage after the parallel doc+policy check.
Model, description, and instruction are sourced from agent_configs.py.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..configs import AGENT_CONFIGS
from ..tools.redis_tools import push_fraud_queue, write_audit_log

_cfg = AGENT_CONFIGS["FraudAgent"]

fraud_agent = LlmAgent(
    name="FraudAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[push_fraud_queue, write_audit_log],
    output_key="fraud_assessment",
)
