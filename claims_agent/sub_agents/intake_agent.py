"""
intake_agent.py
---------------
IntakeAgent — first agent in the pipeline.

Accepts raw claim input (either a JSON dict string or free-text narrative)
and normalises it into a structured ClaimIntake object that downstream agents
can rely on.

The agent writes its normalised output to session state under the key
'normalized_claim' (as a JSON string) via output_key.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from ..schemas import ClaimIntake

intake_agent = LlmAgent(
    name="IntakeAgent",
    model="gemini-2.0-flash",
    description=(
        "Normalises raw insurance claim input (JSON or free-text) into a "
        "structured ClaimIntake record."
    ),
    instruction="""You are an insurance claim intake specialist.

Your task is to read the raw claim data provided in the conversation and extract
or infer all fields needed for a structured ClaimIntake record.

Rules:
- If the input is a JSON object, map its fields directly.
- If the input is free-text (e.g. an email or description), extract all available
  information from the text and use reasonable defaults for any missing fields.
- For claim_id: if not provided, generate one in the format CLM-YYYYMMDD-XXX using
  today's date and a 3-digit sequence (e.g. CLM-20260417-001).
- For incident_date: if not provided, use today's date in YYYY-MM-DD format.
- For amount_claimed: if not explicitly stated, set to 0.0 and note it in the description.
- claim_type must be one of: auto, health, property, life, liability.
- documents_provided should list any documents mentioned as attached or submitted.

Respond ONLY with a valid JSON object matching the ClaimIntake schema.
Do not include any explanation or markdown fences — raw JSON only.
""",
    output_schema=ClaimIntake,
    output_key="normalized_claim",
    generate_content_config=types.GenerateContentConfig(temperature=0.1),
)
