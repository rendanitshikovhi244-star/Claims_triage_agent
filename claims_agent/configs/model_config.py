"""
model_config.py
---------------
Shared model configuration for all agents.
Loads .env from the claims_agent/ directory and exposes DEFAULT_MODEL.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

# .env lives one level up: claims_agent/.env
load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_MODEL = LiteLlm(
    model=os.environ["HF_MODEL"],
)
