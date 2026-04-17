"""
policy_agent.py
---------------
PolicyAgent — runs in parallel with DocumentAgent.

Validates the claim against the policy rules:
  1. Policy must be active
  2. Claim type must be covered
  3. Amount claimed must not exceed coverage limit

Writes audit log and stores output under 'policy_check'.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..config import DEFAULT_MODEL
from ..tools.policy_tools import lookup_policy, validate_claim_against_policy
from ..tools.redis_tools import write_audit_log

policy_agent = LlmAgent(
    name="PolicyAgent",
    model=DEFAULT_MODEL,
    description="Validates the claim against policy rules and identifies any violations.",
    instruction="""You are an insurance policy compliance analyst.

The normalised claim is available in session state as {normalized_claim}.

Your tasks:
1. Call lookup_policy with the policy_number from the normalised claim to verify
   the policy exists and retrieve its details.

2. Call validate_claim_against_policy with:
   - policy_number from the normalised claim
   - claim_type from the normalised claim
   - amount_claimed from the normalised claim

3. Based on the tool results, build the PolicyCheckResult:
   - policy_number: from the normalised claim
   - is_policy_active: from lookup_policy result
   - coverage_limit: from the validation result
   - deductible: from the validation result
   - amount_within_limit: true if amount_claimed <= coverage_limit
   - violations: list of violation strings from the validation result
   - passed: true if violations list is empty

4. Call write_audit_log with:
   - claim_id from the normalised claim
   - agent_name: "PolicyAgent"
   - decision: "policy:passed" if no violations, else the string "policy:violations:" followed by
     the number of violations as an integer (e.g. "policy:violations:2")
   - details: your full JSON policy check result as a string

5. Respond ONLY with a valid JSON object matching the PolicyCheckResult schema.
   Raw JSON only — no markdown, no explanation.
""",
    tools=[lookup_policy, validate_claim_against_policy, write_audit_log],
    output_key="policy_check",
)
