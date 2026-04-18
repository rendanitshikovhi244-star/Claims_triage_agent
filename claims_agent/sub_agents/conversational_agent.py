"""
conversational_agent.py
-----------------------
ClaimsAssistant — the front-door conversational agent.
Model, description, and instruction are sourced from agent_configs.py.

It is the root_agent exposed to adk web and adk run.
The batch CLI (main.py) bypasses this agent and calls pipeline_agent directly.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..configs import AGENT_CONFIGS, agent_start_callback
from ..tools.document_tools import get_required_documents
from ..tools.pipeline_runner_tool import resubmit_with_documents, submit_claim
from ..tools.redis_tools import get_audit_log

_cfg = AGENT_CONFIGS["ClaimsAssistant"]

conversational_agent = LlmAgent(
    name="ClaimsAssistant",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[
        get_required_documents,
        submit_claim,
        resubmit_with_documents,
        get_audit_log,
    ],
    before_agent_callback=agent_start_callback,
)
