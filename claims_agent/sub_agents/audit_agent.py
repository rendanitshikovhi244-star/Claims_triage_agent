"""
audit_agent.py
--------------
AuditSummaryAgent — final agent in the pipeline.
Model, description, and instruction are sourced from agent_configs.py.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.redis_tools import write_audit_log

_cfg = AGENT_CONFIGS["AuditSummaryAgent"]

audit_agent = LlmAgent(
    name="AuditSummaryAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[write_audit_log],
    output_key="final_decision",
    before_agent_callback=agent_start_callback,
)
