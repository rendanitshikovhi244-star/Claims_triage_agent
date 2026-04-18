"""
classification_agent.py
-----------------------
ClassificationAgent — second agent in the pipeline.
Model, description, and instruction are sourced from agent_configs.py.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.redis_tools import write_audit_log

_cfg = AGENT_CONFIGS["ClassificationAgent"]

classification_agent = LlmAgent(
    name="ClassificationAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[write_audit_log],
    output_key="classification",
    before_agent_callback=agent_start_callback,
)
