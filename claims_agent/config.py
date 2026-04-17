"""
config.py
---------
Shared model configuration for all agents.
Loads .env from the claims_agent/ directory and exposes DEFAULT_MODEL.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

load_dotenv(Path(__file__).parent / ".env")

DEFAULT_MODEL = LiteLlm(
    model=os.environ["HF_MODEL"],
)
