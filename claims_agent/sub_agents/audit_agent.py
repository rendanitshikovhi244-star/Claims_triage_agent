"""
audit_agent.py
--------------
AuditSummaryAgent — final agent in the pipeline.

Reads all prior agent outputs from session state, compiles the complete
triage decision, writes a summary AuditEntry to Redis, and produces the
FinalDecision that is returned to the caller.

Stores output under 'final_decision'.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..config import DEFAULT_MODEL
from ..schemas import FinalDecision
from ..tools.redis_tools import write_audit_log

audit_agent = LlmAgent(
    name="AuditSummaryAgent",
    model=DEFAULT_MODEL,
    description=(
        "Compiles the complete triage outcome into a FinalDecision and writes "
        "the audit summary entry to Redis."
    ),
    instruction="""You are an insurance claims audit coordinator.

You have access to the complete triage pipeline results in session state:
- Normalised claim:  {normalized_claim}
- Classification:    {classification}
- Document check:    {doc_check}
- Policy check:      {policy_check}
- Fraud assessment:  {fraud_assessment}

Your tasks:
1. Determine the overall_status of the claim using this priority order:
   a. If fraud_assessment.recommendation == "reject"         → "rejected"
   b. If fraud_assessment.is_suspicious == true              → "fraud_review"
   c. If policy_check.passed == false                        → "policy_violation"
   d. If doc_check.all_docs_present == false                 → "pending_documents"
   e. Otherwise                                              → "approved_for_processing"

2. Compile all missing_docs from doc_check.missing_docs.

3. Compile all policy_violations from policy_check.violations.

4. Write a clear, professional summary (2–4 sentences) explaining the triage outcome
   for a human reviewer.

5. Set audit_key to the string "audit:" followed by the claim_id (e.g. "audit:CLM-001").

6. Call write_audit_log with:
   - claim_id from the normalised claim
   - agent_name: "AuditSummaryAgent"
   - decision: the string "final:" followed by the overall_status value
     (e.g. "final:approved_for_processing" or "final:fraud_review")
   - details: your full JSON final decision as a string

7. Respond ONLY with a valid JSON object matching the FinalDecision schema.
   Raw JSON only — no markdown, no explanation.
""",
    tools=[write_audit_log],
    output_schema=FinalDecision,
    output_key="final_decision",
)
