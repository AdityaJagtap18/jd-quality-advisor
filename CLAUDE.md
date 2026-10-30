# CLAUDE.md — Agent Orchestration (JDQI Demo)

## What This Is
A Streamlit app with two tools built on the **Claude Advisor Strategy**:
- **🔍 Analyse JD** — pastes an existing JD, scores it across 6 JDQI dimensions via a 9-agent pipeline
- **📝 Build JD** — chat interface guides the user to build a JDQI-compliant JD, downloads as branded `.docx`

Both pipelines are gated by **AWS Bedrock Guardrails** on input and output. Guardrails are a hard gate — any failure (including AWS errors) blocks the pipeline.

Core insight: AI amplifies whatever signal the JD carries. Garbage JD → garbage hiring at scale.

## Repo
`jd-quality-advisor` · branch: `main`  
Remote: `https://github.com/AdityaJagtap18/jd-quality-advisor`   

## Design & Plans
| Doc | Path |
|-----|------|
| Analyse JD spec | `docs/superpowers/specs/2026-04-10-jdqi-advisor-strategy-design.md` |
| Analyse JD plan | `docs/superpowers/plans/2026-04-10-jdqi-advisor-strategy.md` |
| Build JD spec | `docs/superpowers/specs/2026-04-14-jd-builder-design.md` |
| Build JD plan | `docs/superpowers/plans/2026-04-14-jd-builder.md` |
| Guardrail highlighter spec | `docs/superpowers/specs/2026-04-29-guardrail-jd-highlighter-design.md` |
| Guardrail highlighter plan | `docs/superpowers/plans/2026-04-29-guardrail-jd-highlighter.md` |

## Architecture

### Tab 1: Analyse JD — Advisor Strategy (9 agents)

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
    ├── passed → JDQI Report UI
    └── blocked → scan_jd_for_violations (Haiku, ~2s)
                  → highlight problematic phrases in JD text
```

All agents share a plain Python dict (`JDQIContext`) as shared context.

### Tab 2: Build JD — Two-Phase Chat Pipeline

```
User Chat Message
    │
    ▼  🛡️ Bedrock Guardrail (INPUT) — fires on EVERY message
    │
    ▼
Phase 1: Gather Agent (Sonnet)        [agents/jd_builder_gather.py]
    Adaptive conversation, one question at a time
    Covers all 6 JDQI dimensions; warns on skip impact
    Calls signal_ready tool when JDQIBrief is complete
    │
    ▼  User confirms → "Generate JD now"
    │
    ▼
Phase 2: Draft Agent (Sonnet)         [agents/jd_builder_draft.py]
    Receives clean JDQIBrief (not raw chat history)    ┐
    Writes full JD prose → JDDocument dict              │ up to 3 attempts
    │                                                   │
    ▼  🛡️ Bedrock Guardrail (OUTPUT)                  │
    ├── passed ─────────────────────────────────────────┘
    └── blocked → extract block reasons (topics/words/PII)
                  pass feedback to draft_jd(guardrail_feedback=...)
                  redraft avoiding all flagged content
                  re-check guardrail (loop, max 3 attempts)
    │
    ▼
Branded .docx download               [agents/jd_docx.py]
    python-docx, configurable color + optional logo
```

## File Map
| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI — two tabs, session state, pipeline orchestration |
| `agents/parser.py` | Agent 1 — extract structured fields from raw JD |
| `agents/specialists.py` | Agents 2–7 — 6 dimension analyzers, run in parallel |
| `agents/synthesizer.py` | Agent 8 — Sonnet tool loop, calls `consult_advisor` |
| `agents/advisor.py` | Agent 9 — Opus benchmark comparison + JDQI scoring |
| `agents/jd_builder_gather.py` | Phase 1 gather agent — adaptive chat, `signal_ready` tool |
| `agents/jd_builder_draft.py` | Phase 2 draft agent — JDQIBrief → JDDocument prose |
| `agents/jd_docx.py` | python-docx builder — branded `.docx` with color + logo |
| `agents/guardrails.py` | AWS Bedrock `apply_guardrail` — input + output gate; `scan_jd_for_violations()` — Haiku call to identify problematic JD phrases |
| `models/context.py` | TypedDict schemas — JDQIContext, JDQIBrief, JDDocument, etc. |
| `tests/test_jd_docx.py` | Unit tests for the docx builder (7 tests) |
| `tests/test_guardrail_highlighter.py` | Unit tests for `scan_jd_for_violations` and `_build_highlighted_html` (14 tests) |

## Local Dev
```bash
cd ./jd-quality-advisor
source .venv/bin/activate
streamlit run app.py --server.port 8501
# → http://localhost:8501
```

`.env` must contain:
```
ANTHROPIC_API_KEY=sk-ant-...

# AWS Bedrock (explicit keys — preferred)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1

# OR use a named profile instead:
# AWS_PROFILE=your-profile-name
```

**Credential resolution in `agents/guardrails.py`:** explicit `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` always take priority over `AWS_PROFILE`, even if the profile is set in the shell environment. This prevents a shell-level assumed-role from overriding `.env` credentials.

## Tech Stack
| Layer | Tech |
|-------|------|
| UI | Streamlit 1.43+ |
| LLM SDK | anthropic 0.49+ (Sonnet 4.6 + Opus 4.6) |
| Guardrails | AWS Bedrock `apply_guardrail` via boto3 1.34+ |
| Docx generation | python-docx 1.1+ |
| Parallelism | ThreadPoolExecutor (6 specialists) |
| Config | python-dotenv (with `override=True`) |
| Runtime | Python 3.11 (venv at `.venv/`) |

## Bedrock Guardrail Config
| Setting | Value |
|---------|-------|
| Guardrail ID | `ovpwtkmupag5` |
| Version | `2` |
| Region | `ap-south-1` |
| Input source | `"INPUT"` — JD text / chat message before any LLM call |
| Output source | `"OUTPUT"` — advisor report / drafted JD text |

**Behavior on blocked INPUT**: pipeline halts, red error shown, no LLM call made.
**Behavior on blocked OUTPUT (Build JD)**: course-correction loop — block reasons fed back to `draft_jd(guardrail_feedback=...)`, redraft up to 3 times before showing a persistent error.
**Behavior on blocked OUTPUT (Analyse JD)**: red error shown → Haiku call scans original JD → problematic phrases highlighted in amber in the JD text panel.
**Behavior on AWS error**: pipeline halts, red error shown — guardrail is a hard gate.

## JDQI Dimensions
| Dimension | What's checked | Weight |
|-----------|---------------|--------|
| Completeness | required/preferred skills, success criteria, reporting structure, growth path | 25% |
| Skill Specificity | tools/versions/proficiency levels explicit vs vague | 20% |
| Role Coherence | seniority vs experience/responsibility alignment | 20% |
| Cognitive Load | word count, Flesch-Kincaid grade, jargon density | 15% |
| Inclusion Signals | exclusionary language flags | 10% |
| Compensation | salary band present/absent | 10% |

## Key Design Decisions
- **Advisor invoked via tool call** — synthesis executor (Sonnet) has one tool `consult_advisor`. It calls the tool with a brief summary; the tool handler invokes `run_advisor()` (Opus) with the full shared context.
- **Two-phase JD Builder** — gather agent fills a structured `JDQIBrief`; draft agent receives the clean brief (not raw chat history). Higher quality output; mirrors the advisor pattern.
- **`signal_ready` tool** — gather agent calls this tool when it has enough info; the tool call is the handoff signal to Phase 2.
- **History trimming in Build JD** — Anthropic API requires history to start with a user message. The greeting is seeded as an assistant message for display only; leading assistant messages are stripped before passing history to `gather_turn`.
- **ThreadPoolExecutor not asyncio** — Streamlit runs its own event loop; threading avoids conflicts. `anthropic.Anthropic` client is thread-safe.
- **`load_dotenv(override=True)`** — ensures `.env` values override any shell environment variables (e.g. a shell-level `AWS_PROFILE` won't shadow `.env` credentials).
- **`_extract_json()` in advisor + draft agent** — walks brace depth to extract the first `{...}` block, tolerating any text Opus/Sonnet appends after the JSON.
- **Guardrail output course-correction loop** — when the OUTPUT guardrail blocks a drafted JD, the block reasons (topic policies, blocked words/phrases, PII) are extracted from `assessments` and passed back to `draft_jd(guardrail_feedback=...)` as explicit rewrite instructions. The loop retries up to `_MAX_DRAFT_RETRIES = 3` times. Each redraft is told exactly which words to remove and which patterns triggered topic blocks (e.g. `Discriminatory_Hiring_Criteria`, `Sensitive_Demographic_Questions`). This avoids surfacing a guardrail error to the user in the common case where the first draft uses protected-characteristic language in the EEO statement.
- **`tool_choice="any"` forced follow-up in gather_turn** — if the gather agent previously declared readiness in text without calling `signal_ready`, the next `gather_turn` call uses `tool_choice={"type": "any"}` to force the tool call. A secondary safety net fires a follow-up call with `tool_choice="any"` if the current reply also contains ready phrases but no tool call. Follow-up messages use the plain text `reply` string (not raw `response.content` Pydantic objects) to avoid `tool_use`-without-`tool_result` 400 errors.
- **No database** — all state is in-memory per Streamlit session.
- **Guardrail OUTPUT block → JD highlighter** — when the OUTPUT guardrail blocks the advisor report in Analyse JD, `scan_jd_for_violations()` (Haiku, `claude-haiku-4-5-20251001`, max_tokens=512) scans the original JD text and returns verbatim phrases that match the block reason. `_build_highlighted_html()` renders the JD with those phrases in amber `<mark>` spans using case-insensitive matching and substring deduplication (longer phrases absorb substrings to prevent nested tags). Falls back to a plain caption if Haiku returns nothing. Only fires on OUTPUT block; INPUT block has no highlighting (JD is still visible in the form).
- **`_build_highlighted_html()` phrase matching** — phrases are sorted longest-first before replacement, then deduplicated (drop any phrase that is a substring of a longer phrase in the list). Replacement uses `re.sub` with `re.IGNORECASE` and `lambda m: m.group(0)` to preserve the original JD casing inside the highlight span. The full JD text is HTML-escaped before any substitution to prevent XSS.

## Running Tests
```bash
source .venv/bin/activate
python -m pytest tests/ -v
# 21 passed
```

## Target Segments
- **High-tech Manufacturing** — under-specified JDs (missing Cadence/Altium, SPICE, tool chains)
- **IT/SaaS/AI** — skill inflation ("5 years React + K8s + ML" for mid role)
- **GCCs** — JDs copied from US/EU parent without India market calibration
