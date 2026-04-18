"""
model_config.py
---------------
Model instances for all agents.
Three tiers — each mapped to a HuggingFace model chosen for its role:

  MODEL_FAST  (Qwen2.5-14B-Instruct)           — IntakeAgent, PolicyAgent
  MODEL_MID   (Llama-3.3-70B-Instruct)         — ClassificationAgent, DocumentAgent, AuditSummaryAgent
  MODEL_MAIN  (MiniMaxAI/MiniMax-M2.7)         — FraudAgent, ClaimsAssistant (agent harness + tool calling)

To swap a tier, change the corresponding HF_MODEL_* variable in claims_agent/.env.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

# .env lives one level up: claims_agent/.env
load_dotenv(Path(__file__).parent.parent / ".env")

MODEL_FAST = LiteLlm(model=os.environ["HF_MODEL_FAST"])
MODEL_MID  = LiteLlm(model=os.environ["HF_MODEL_MID"])
MODEL_MAIN = LiteLlm(model=os.environ["HF_MODEL_MAIN"])

# Convenience alias — used by any code that still expects DEFAULT_MODEL
DEFAULT_MODEL = MODEL_MAIN
