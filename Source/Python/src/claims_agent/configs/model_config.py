"""
model_config.py
---------------
Model instances for all agents.
Three tiers — each mapped to a HuggingFace model chosen for its role:

  MODEL_FAST  (Qwen2.5-14B-Instruct)           — IntakeAgent, PolicyAgent
  MODEL_MID   (Llama-3.3-70B-Instruct)         — ClassificationAgent, DocumentAgent, AuditSummaryAgent
  MODEL_MAIN  (MiniMaxAI/MiniMax-M2.7)         — FraudAgent, ClaimsAssistant (agent harness + tool calling)

Models are resolved from AWS Secrets Manager first, falling back to .env for local dev.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

from claims_agent.utils.aws.credentials_loader import load_secrets_if_available

logger = logging.getLogger(__name__)

# .env lives one level up: claims_agent/.env (fallback for local dev)
load_dotenv(Path(__file__).parent.parent / ".env")


_secrets = load_secrets_if_available()

MODEL_FAST = LiteLlm(model=_secrets.get("HF_MODEL_FAST", os.environ.get("HF_MODEL_FAST", "")))
MODEL_MID  = LiteLlm(model=_secrets.get("HF_MODEL_MID", os.environ.get("HF_MODEL_MID", "")))
MODEL_MAIN = LiteLlm(model=_secrets.get("HF_MODEL_MAIN", os.environ.get("HF_MODEL_MAIN", "")))

# Convenience alias — used by any code that still expects DEFAULT_MODEL
DEFAULT_MODEL = MODEL_MAIN
