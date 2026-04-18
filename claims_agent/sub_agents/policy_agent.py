"""
policy_agent.py
---------------
PolicyAgent — runs in parallel with DocumentAgent.
Model, description, and instruction are sourced from agent_configs.py.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.policy_tools import lookup_policy, validate_claim_against_policy
from ..tools.redis_tools import write_audit_log

_cfg = AGENT_CONFIGS["PolicyAgent"]

policy_agent = LlmAgent(
    name="PolicyAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[lookup_policy, validate_claim_against_policy, write_audit_log],
    output_key="policy_check",
    before_agent_callback=agent_start_callback,
)
