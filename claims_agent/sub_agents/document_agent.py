"""
document_agent.py
-----------------
DocumentAgent — runs in parallel with PolicyAgent.

Checks which required documents are missing from the claim submission and
generates a polite request message for the claimant.

Writes audit log and stores output under 'doc_check'.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from ..config import DEFAULT_MODEL
from ..schemas import DocCheckResult
from ..tools.document_tools import check_present_documents, get_required_documents
from ..tools.redis_tools import write_audit_log

document_agent = LlmAgent(
    name="DocumentAgent",
    model=DEFAULT_MODEL,
    description=(
        "Identifies missing required documents for the claim and generates a "
        "document request message for the claimant."
    ),
    instruction="""You are an insurance document compliance officer.

The normalised claim is available in session state as {normalized_claim}.

Your tasks:
1. Call get_required_documents with the claim_type from the normalised claim to
   retrieve the full list of required documents.

2. Call check_present_documents with the claim_type and the documents_provided
   list from the normalised claim (pass documents_provided as a JSON array string).

3. Based on the tool results:
   - Build the list of required_docs (from get_required_documents)
   - Build the list of missing_docs (from check_present_documents)
   - Set all_docs_present to true if missing_docs is empty
   - If documents are missing, write a professional, empathetic request_message
     addressed to the claimant asking them to submit the missing items.
     Be specific — list each missing document by name.
   - If all documents are present, set request_message to null.

4. Call write_audit_log with:
   - claim_id from the normalised claim
   - agent_name: "DocumentAgent"
   - decision: "docs:complete" if all present, else "docs:missing:{{count}}" 
     where {{count}} is the number of missing documents
   - details: your full JSON doc check result as a string

5. Respond ONLY with a valid JSON object matching the DocCheckResult schema.
   Raw JSON only — no markdown, no explanation.
""",
    tools=[get_required_documents, check_present_documents, write_audit_log],
    output_schema=DocCheckResult,
    output_key="doc_check",
)
