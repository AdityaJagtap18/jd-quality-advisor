# JD Quality Intelligence (JDQI)

A Streamlit demo of the **Claude Advisor Strategy** applied to hiring — two tools in one app:

| Tab | What it does |
|-----|-------------|
| 🔍 **Analyse JD** | Paste an existing JD, get a scored quality report across 6 dimensions |
| 📝 **Build JD** | Chat with an AI consultant to build a JDQI-compliant JD, download as branded `.docx` |

Both pipelines are gated by **AWS Bedrock Guardrails** on input and output.

---

## Why This Exists

AI amplifies whatever signal the JD carries. A vague or biased JD fed into an AI hiring pipeline produces vague, biased shortlists — at scale. This tool acts as a quality gate before the JD becomes the source of truth.

---

## Architecture

### Analyse JD — 9-Agent Pipeline (Advisor Strategy)

```
JD Text + Industry
    │
    ▼  🛡️ Bedrock Guardrail (INPUT)
    │
    ▼
Agent 1: JD Parser (Sonnet)           → parsed_jd
    │
    ▼
Agents 2–7: Specialist Analyzers      → dimension_results  (parallel, ThreadPoolExecutor)
    Completeness · Skill Specificity · Cognitive Load
    Inclusion Signals · Compensation · Role Coherence
    │
    ▼
Agent 8: Synthesis Executor (Sonnet)  → calls consult_advisor tool
    │  tool call
    ▼
Agent 9: Advisor (Opus, on-demand)    → advisor_report
    │
    ▼  🛡️ Bedrock Guardrail (OUTPUT)
    ├── passed → JDQI Report + Suggested Additions
    └── blocked → Haiku scans JD → highlights problematic phrases
```

### Build JD — Two-Phase Chat Pipeline

```
User Chat Message
    │
    ▼  🛡️ Bedrock Guardrail (INPUT)
    │
    ▼
Phase 1: Gather Agent (Sonnet)
    Adaptive conversation — covers all 6 JDQI dimensions
    Warns user on JDQI score impact before skipping any dimension
    Calls signal_ready tool when brief is complete
    │
    ▼  User confirms → "Generate JD now"
    │
    ▼
Phase 2: Draft Agent (Sonnet)          ┐
    Receives clean JDQIBrief            │  up to 3 attempts
    Writes full JD prose                │
    │                                   │
    ▼  🛡️ Bedrock Guardrail (OUTPUT)   │
    │                                   │
    ├── passed ─────────────────────────┘
    │
    └── blocked → extract block reasons (topics, words, PII)
                  feed back to Draft Agent as explicit corrections
                  redraft avoiding all flagged content
                  re-check guardrail  (loop, max 3 attempts)
    │
    ▼
Branded .docx download
    (configurable color, optional logo, header/footer)
```

---

## JDQI Dimensions

| Dimension | What's checked | Weight |
|-----------|---------------|--------|
| Completeness | required/preferred skills, success criteria, reporting structure, growth path | 25% |
| Skill Specificity | tools/versions/proficiency levels explicit vs vague | 20% |
| Role Coherence | seniority vs experience/responsibility alignment | 20% |
| Cognitive Load | word count, Flesch-Kincaid grade, jargon density | 15% |
| Inclusion Signals | exclusionary language flags | 10% |
| Compensation | salary band present/absent | 10% |

---

## File Map

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI — two tabs, session state, pipeline orchestration |
| `agents/parser.py` | Agent 1 — extract structured fields from raw JD text |
| `agents/specialists.py` | Agents 2–7 — 6 dimension analyzers, ThreadPoolExecutor |
| `agents/synthesizer.py` | Agent 8 — Sonnet tool loop, calls `consult_advisor` |
| `agents/advisor.py` | Agent 9 — Opus benchmark comparison + JDQI scoring |
| `agents/jd_builder_gather.py` | Phase 1 gather agent — adaptive chat, `signal_ready` tool |
| `agents/jd_builder_draft.py` | Phase 2 draft agent — JDQIBrief → JDDocument prose |
| `agents/jd_docx.py` | python-docx builder — branded `.docx` with color + logo |
| `agents/guardrails.py` | AWS Bedrock `apply_guardrail` — input + output gate; `scan_jd_for_violations()` Haiku phrase scan |
| `models/context.py` | TypedDict schemas — JDQIContext, JDQIBrief, JDDocument, etc. |
| `tests/test_jd_docx.py` | Unit tests for the docx builder |
| `tests/test_guardrail_highlighter.py` | Unit tests for guardrail scan + HTML highlighter |

---

## Quick Start

```bash
# 1. Clone and enter the project
cd ./jd-quality-advisor

# 2. Create venv with Python 3.11
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Set environment variables
cp .env.example .env   # then fill in values (see below)

# 4. Run
streamlit run app.py --server.port 8501
# → http://localhost:8501
```

### `.env` variables

```
ANTHROPIC_API_KEY=sk-ant-...

# AWS Bedrock Guardrails (bedrock_user IAM credentials)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1

# Or use a named profile instead of explicit keys:
# AWS_PROFILE=your-profile-name
```

> **Guardrail behaviour:** If AWS credentials are missing or invalid, both INPUT and OUTPUT guardrail checks will block the pipeline and show a red error. Credentials must be valid with `bedrock:ApplyGuardrail` permission.

---

## Bedrock Guardrail Config

| Setting | Value |
|---------|-------|
| Guardrail ID | `ovpwtkmupag5` |
| Version | `2` |
| Region | `ap-south-1` |

| Path | Behaviour on block |
|------|--------------------|
| INPUT (both tabs) | Pipeline halts, red error, no LLM call |
| OUTPUT (Build JD) | Course-correction loop — redraft up to 3× with block reasons as feedback |
| OUTPUT (Analyse JD) | Red error + Haiku scans the JD and highlights the offending phrases in amber |

---

## Tech Stack

| Layer | Tech |
|-------|------|
| UI | Streamlit 1.43+ |
| LLM | Anthropic SDK 0.49+ (Sonnet 4.6 + Opus 4.6) |
| Guardrails | AWS Bedrock `apply_guardrail` via boto3 1.34+ |
| Docx generation | python-docx 1.1+ |
| Parallelism | ThreadPoolExecutor (6 specialist agents) |
| Config | python-dotenv |
| Runtime | Python 3.11 |

---

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
# 21 passed
```
