# Claims Triage Multi-Agent System

An insurance claims triage pipeline built with **Google ADK** (Agent Development Kit), **Gemini / HuggingFace** LLMs, and **Redis** for audit logging.

---

## Architecture

```
ClaimsTriagePipeline (SequentialAgent)
 ├── IntakeAgent          — normalises raw input (JSON or free-text) → ClaimIntake
 ├── ClassificationAgent  — urgency (critical/high/medium/low) + claim type
 ├── ComplianceCheck (ParallelAgent)
 │    ├── DocumentAgent   — identifies missing required docs, drafts request message
 │    └── PolicyAgent     — validates coverage, active policy, deductible, limits
 ├── FraudAgent           — risk score (0–1), routes suspicious claims to Redis queue
 └── AuditSummaryAgent    — compiles FinalDecision, writes summary audit entry
```

### Redis Keys
| Key | Type | Purpose |
|---|---|---|
| `audit:{claim_id}` | List | Per-agent audit entries (append-only, chronological) |
| `fraud_review_queue` | List | Suspicious claims awaiting human fraud review |

### ADK Session State (SQLite)
Inter-agent handoff via shared keys: `normalized_claim` → `classification` → `doc_check` + `policy_check` → `fraud_assessment` → `final_decision`

---

## Project Structure

```
Claims_triage_agent/
├── claims_agent/
│   ├── __init__.py
│   ├── agent.py                 ← root_agent (conversational) + pipeline_agent (CLI)
│   ├── .env                     ← secrets (never committed — see setup below)
│   ├── configs/
│   │   ├── agent_configs.py     ← central registry: prompts, model assignments per agent
│   │   ├── logging_config.py    ← structured logging setup
│   │   └── model_config.py      ← three-tier LiteLLM model instances
│   ├── schemas/
│   │   └── models.py            ← Pydantic models for all agent I/O
│   ├── tools/
│   │   ├── redis_tools.py       ← write_audit_log, push_fraud_queue, get_audit_log
│   │   ├── document_tools.py    ← get_required_documents, check_present_documents
│   │   ├── pipeline_runner_tool.py ← ADK tool that invokes the triage pipeline
│   │   └── policy_tools.py      ← lookup_policy, validate_claim_against_policy
│   └── sub_agents/
│       ├── conversational_agent.py ← ClaimsAssistant (adk web / adk run entry point)
│       ├── intake_agent.py
│       ├── classification_agent.py
│       ├── document_agent.py
│       ├── policy_agent.py
│       ├── fraud_agent.py
│       └── audit_agent.py
├── sample_claims/
│   ├── claim_auto_001.json      ← standard auto claim (2 missing docs)
│   ├── claim_health_002.json    ← health claim (1 missing doc)
│   └── claim_suspicious_003.json ← high fraud risk (day-1 claim, pressure language)
├── tests/
│   └── test_pipeline.py         ← unit tests (no API key or Redis required)
├── main.py                      ← CLI entrypoint
├── requirements.txt
├── pytest.ini
└── .env.example                 ← template — copy to claims_agent/.env and fill in
```

---

## Setup

### 1. Clone and create virtual environment
```bash
python -m venv .venv
# Windows
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
Copy the example template and fill in your credentials:
```bash
copy .env.example claims_agent\.env      # Windows
cp .env.example claims_agent/.env        # macOS/Linux
```

Edit `claims_agent/.env`:

```env
# HuggingFace API key (https://huggingface.co/settings/tokens)
HUGGINGFACE_API_KEY=hf_your_key_here

# Three-tier model assignments — swap any line to use a different HF model
HF_MODEL_FAST=huggingface/Qwen/Qwen2.5-14B-Instruct     # IntakeAgent, PolicyAgent
HF_MODEL_MID=huggingface/meta-llama/Llama-3.3-70B-Instruct  # ClassificationAgent, DocumentAgent, AuditSummaryAgent
HF_MODEL_MAIN=huggingface/MiniMaxAI/MiniMax-M2.7            # FraudAgent, ClaimsAssistant

REDIS_URL=redis://localhost:6379/0
SESSION_DB_URL=sqlite+aiosqlite:///./claims_sessions.db
```

Model assignments are managed in `claims_agent/configs/agent_configs.py`. To reroute an individual agent to a different tier, edit the `_MODELS` dictionary in that file.

### 4. Start Redis
```bash
docker run -d -p 6379:6379 --name redis-claims redis:alpine
```

---

## Running

### CLI — single claim
```bash
# From a JSON file
python main.py sample_claims/claim_auto_001.json

# From a JSON string
python main.py '{"claim_id": "CLM-001", "policy_number": "POL-1001", ...}'

# Free-text intake
python main.py "My car was rear-ended on the highway. Policy POL-1001."
```

### Browser UI (ADK dev interface)
```bash
adk web
# Opens at http://localhost:8000
```

### Tests (no API key or Redis needed)
```bash
pytest tests/ -v
```

---

## Inspecting Results

### Audit log for a claim
```bash
docker exec -it redis-claims redis-cli LRANGE audit:CLM-20260417-001 0 -1
```

### Fraud review queue
```bash
docker exec -it redis-claims redis-cli LRANGE fraud_review_queue 0 -1
```

### Session state (SQLite)
```bash
# After running main.py, a claims_sessions.db file is created in the project root
```

---

## Model Tiers

Agents are assigned to one of three cost-vs-capability tiers in `claims_agent/configs/agent_configs.py`:

| Tier | Env var | Default model | Agents |
|---|---|---|---|
| FAST | `HF_MODEL_FAST` | Qwen2.5-14B-Instruct | IntakeAgent, PolicyAgent |
| MID | `HF_MODEL_MID` | Llama-3.3-70B-Instruct | ClassificationAgent, DocumentAgent, AuditSummaryAgent |
| MAIN | `HF_MODEL_MAIN` | MiniMax-M2.7 | FraudAgent, ClaimsAssistant |

To swap a single agent to a different tier, change its entry in the `_MODELS` dict inside `agent_configs.py`.

---

## Claim Status Logic

Final status is determined by `AuditSummaryAgent` using this priority order:

| Priority | Condition | Status |
|---|---|---|
| 1 | `fraud_assessment.recommendation == "reject"` | `rejected` |
| 2 | `fraud_assessment.is_suspicious == true` (score ≥ 0.7) | `fraud_review` |
| 3 | `policy_check.passed == false` | `policy_violation` |
| 4 | `doc_check.all_docs_present == false` | `pending_documents` |
| 5 | All checks pass | `approved_for_processing` |

---

## Policy Stub Registry

The system ships with hardcoded test policies:

| Policy | Active | Coverage Limit | Deductible | Covers |
|---|---|---|---|---|
| POL-1001 | ✅ | $50,000 | $500 | auto, liability |
| POL-1002 | ✅ | $200,000 | $1,000 | health |
| POL-1003 | ❌ lapsed | $100,000 | $750 | property, liability |
| POL-1004 | ✅ | $500,000 | $2,500 | life |
| POL-9999 | ✅ | $10,000 | $250 | all types |
