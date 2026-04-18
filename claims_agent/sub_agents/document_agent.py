"""
document_agent.py
-----------------
DocumentAgent — runs in parallel with PolicyAgent.
Model, description, and instruction are sourced from agent_configs.py.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..configs import AGENT_CONFIGS
from ..tools.document_tools import check_present_documents, get_required_documents
from ..tools.redis_tools import write_audit_log

_cfg = AGENT_CONFIGS["DocumentAgent"]

document_agent = LlmAgent(
    name="DocumentAgent",
    model=_cfg.model,
    description=_cfg.description,
    instruction=_cfg.instruction,
    tools=[get_required_documents, check_present_documents, write_audit_log],
    output_key="doc_check",
)
