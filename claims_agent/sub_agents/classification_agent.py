"""
classification_agent.py
-----------------------
ClassificationAgent — second agent in the pipeline.

Reads the normalised claim from session state (normalized_claim) and classifies:
  - urgency: critical / high / medium / low
  - claim_type: confirmed or corrected type

Writes an audit log entry to Redis and stores its output under 'classification'.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from ..schemas import Classification
from ..tools.redis_tools import write_audit_log

classification_agent = LlmAgent(
    name="ClassificationAgent",
    model="gemini-2.0-flash",
    description="Classifies claim urgency and type, then records the decision in the audit log.",
    instruction="""You are an insurance claims triage specialist.

The normalised claim is available in session state as {normalized_claim}.

Your tasks:
1. Classify the urgency of the claim:
   - critical: life-threatening injuries, total loss, catastrophic event, or claim > $100,000
   - high: significant financial impact, time-sensitive treatment, or claim $25,000–$100,000
   - medium: standard processing, claim $5,000–$25,000
   - low: minor claim, no time pressure, claim < $5,000

2. Confirm or correct the claim_type (auto, health, property, life, liability) based on
   the claim description. The intake agent may have guessed incorrectly.

3. Call write_audit_log with:
   - claim_id from the normalised claim
   - agent_name: "ClassificationAgent"
   - decision: "classified:{urgency}" (e.g. "classified:high")
   - details: your full JSON classification result as a string

4. Respond ONLY with a valid JSON object matching the Classification schema.
   Do not include any explanation or markdown fences — raw JSON only.
""",
    tools=[write_audit_log],
    output_schema=Classification,
    output_key="classification",
    generate_content_config=types.GenerateContentConfig(temperature=0.1),
)
