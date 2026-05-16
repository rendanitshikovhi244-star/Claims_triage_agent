"""
streamlit_app.py
----------------
Streamlit UI for the Claims Triage Multi-Agent System.

Run with:
    cd Source/Python/src
    streamlit run streamlit_app.py
"""

import json

import requests
import streamlit as st

API_BASE = "http://localhost:8080"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Claims Triage",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Claims Triage Agent")
st.caption("Submit an insurance claim and receive an AI-powered triage decision.")

# ---------------------------------------------------------------------------
# Sidebar — health check + fraud queue
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("System Status")
    if st.button("Check Health"):
        try:
            resp = requests.get(f"{API_BASE}/health", timeout=5)
            data = resp.json()
            if data["status"] == "ok":
                st.success(f"API: OK | Redis: {data['redis']}")
            else:
                st.warning(f"API: {data['status']} | Redis: {data['redis']}")
        except requests.ConnectionError:
            st.error("Cannot reach API. Is `uvicorn api:app` running on port 8080?")

    st.divider()
    st.header("Fraud Queue")
    if st.button("Refresh Fraud Queue"):
        try:
            resp = requests.get(f"{API_BASE}/fraud-queue", timeout=5)
            data = resp.json()
            st.metric("Queue Length", data["queue_length"])
            if data["claim_ids"]:
                for cid in data["claim_ids"]:
                    st.code(cid)
            else:
                st.info("No claims in fraud queue.")
        except requests.ConnectionError:
            st.error("Cannot reach API.")

# ---------------------------------------------------------------------------
# Result display helper
# ---------------------------------------------------------------------------


def _display_result(result: dict):
    """Render the triage response in a structured layout."""
    # Status banner
    status = result.get("overall_status", "unknown")
    status_colors = {
        "approved_for_processing": "🟢",
        "pending_documents": "🟡",
        "policy_violation": "🟠",
        "fraud_review": "🔴",
        "rejected": "⛔",
    }
    icon = status_colors.get(status, "⚪")
    st.subheader(f"{icon} {status.replace('_', ' ').title()}")

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Claim ID", result.get("claim_id", "N/A"))
    col2.metric("Urgency", (result.get("urgency") or "N/A").upper())
    col3.metric("Fraud Score", result.get("fraud_risk_score", "N/A"))
    col4.metric("Recommendation", result.get("fraud_recommendation", "N/A"))

    # Details
    if result.get("missing_docs"):
        st.warning("**Missing Documents:** " + ", ".join(result["missing_docs"]))
    if result.get("policy_violations"):
        st.error("**Policy Violations:**")
        for v in result["policy_violations"]:
            st.markdown(f"- {v}")
    if result.get("summary"):
        st.info(f"**Summary:** {result['summary']}")

    # Raw JSON expander
    with st.expander("Raw API Response"):
        st.json(result)


# ---------------------------------------------------------------------------
# Main — Claim submission
# ---------------------------------------------------------------------------

tab_form, tab_json, tab_audit = st.tabs(["📋 Submit Claim", "📝 Raw JSON/Text", "🔍 Audit Lookup"])

# --- Tab 1: Structured form ---
with tab_form:
    with st.form("claim_form"):
        col1, col2 = st.columns(2)
        with col1:
            policy_number = st.text_input("Policy Number", placeholder="POL-1001")
            claimant_name = st.text_input("Claimant Name", placeholder="Jane Smith")
            claim_type = st.selectbox(
                "Claim Type", ["auto", "health", "property", "life", "liability"]
            )
        with col2:
            incident_date = st.date_input("Incident Date")
            amount_claimed = st.number_input("Amount Claimed ($)", min_value=0.0, step=100.0)
            documents_provided = st.multiselect(
                "Documents Provided",
                [
                    "police_report",
                    "fire_or_police_report",
                    "photos_of_damage",
                    "medical_records",
                    "purchase_receipts",
                    "proof_of_ownership",
                    "repair_estimate",
                    "property_deed",
                    "death_certificate",
                    "witness_statements",
                ],
            )

        description = st.text_area(
            "Incident Description",
            placeholder="Describe what happened...",
            height=120,
        )

        submitted = st.form_submit_button("Submit Claim", type="primary", use_container_width=True)

    if submitted:
        payload = {
            "policy_number": policy_number,
            "claimant_name": claimant_name,
            "claim_type": claim_type,
            "incident_date": str(incident_date),
            "amount_claimed": amount_claimed,
            "description": description,
            "documents_provided": documents_provided,
        }

        with st.spinner("Running triage pipeline (this may take 30-60s)..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/claims", json=payload, timeout=120
                )
                if resp.status_code in (200, 202):
                    result = resp.json()
                    st.success("Triage complete!")
                    _display_result(result)
                else:
                    st.error(f"Error {resp.status_code}: {resp.json().get('detail', resp.text)}")
            except requests.ConnectionError:
                st.error("Cannot reach API. Make sure the server is running.")
            except requests.Timeout:
                st.warning("Request timed out. The pipeline may still be processing.")


# --- Tab 2: Raw JSON/Text input ---
with tab_json:
    raw_input = st.text_area(
        "Paste a claim JSON or free-text description",
        height=200,
        placeholder='{"claim_id": "CLM-001", "policy_number": "POL-1001", ...}',
    )
    if st.button("Submit Raw Input", type="primary", use_container_width=True):
        if not raw_input.strip():
            st.warning("Please enter some text.")
        else:
            payload = {"raw_input": raw_input}
            with st.spinner("Running triage pipeline..."):
                try:
                    resp = requests.post(
                        f"{API_BASE}/claims", json=payload, timeout=120
                    )
                    if resp.status_code in (200, 202):
                        result = resp.json()
                        st.success("Triage complete!")
                        _display_result(result)
                    else:
                        st.error(f"Error {resp.status_code}: {resp.json().get('detail', resp.text)}")
                except requests.ConnectionError:
                    st.error("Cannot reach API.")
                except requests.Timeout:
                    st.warning("Request timed out.")


# --- Tab 3: Audit log lookup ---
with tab_audit:
    claim_id_lookup = st.text_input("Claim ID", placeholder="CLM-20260417-003")
    if st.button("Fetch Audit Log", use_container_width=True):
        if not claim_id_lookup.strip():
            st.warning("Please enter a claim ID.")
        else:
            try:
                resp = requests.get(
                    f"{API_BASE}/claims/{claim_id_lookup}/audit", timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.info(f"Found {data['entry_count']} audit entries")
                    for entry in data["entries"]:
                        with st.expander(
                            f"**{entry['agent_name']}** — {entry['decision']}",
                            expanded=False,
                        ):
                            st.caption(entry["timestamp"])
                            st.json(entry["details"])
                elif resp.status_code == 404:
                    st.warning("No audit log found for this claim ID.")
                else:
                    st.error(f"Error: {resp.json().get('detail', resp.text)}")
            except requests.ConnectionError:
                st.error("Cannot reach API.")
