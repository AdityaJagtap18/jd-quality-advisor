# JD Builder — Design Spec
**Date:** 2026-04-14  
**Status:** Approved  
**Module:** JD Builder (tab 2 in `app.py`)

---

## 1. Overview

A two-phase chat interface for building JDQI-compliant job descriptions, delivered as a downloadable branded `.docx`. Built into the existing JDQI Streamlit app as a second tab alongside the Analyse JD tab.

**Core insight:** The chat agent gathers rich, structured information from the user — whether they are a knowledgeable hiring manager or an HR generalist who needs coaching — then hands a clean brief to a dedicated drafting agent. This separation ensures high-quality JD prose without replaying raw chat history through the LLM.

---

## 2. Architecture & Data Flow

```
User message
    │
    ▼
Bedrock Guardrail (INPUT) ── blocked → show error in chat, no LLM call
    │ passed
    ▼
Phase 1: Gather Agent (Sonnet)  [agents/jd_builder_gather.py]
    • Maintains chat history + JDQIBrief dict in session state
    • Asks one question at a time, adapts depth to user expertise
    • Covers all 6 JDQI dimensions; skippable with JDQI score impact warning
    • Calls signal_ready(brief: JDQIBrief) tool when brief is complete
    │ tool call → agent reply: "I have enough. Generate the JD?"
    ▼
User confirms ("yes" / clicks "Generate JD" button)
    │
    ▼
Phase 2: Draft Agent (Sonnet)  [agents/jd_builder_draft.py]
    • Receives clean JDQIBrief (not raw chat history)
    • Writes full JD prose, returns JDDocument dict
    │
    ▼
Bedrock Guardrail (OUTPUT) ── blocked → show error, no download offered
    │ passed
    ▼
docx builder  [agents/jd_docx.py]
    • python-docx, applies brand_color + optional logo
    │
    ▼
st.download_button → .docx file
```

---

## 3. Session State

| Key | Type | Description |
|-----|------|-------------|
| `builder_messages` | `list[dict]` | Chat history `{role, content}` for display |
| `jdqi_brief` | `JDQIBrief \| None` | Structured brief filled during Phase 1 |
| `jd_document` | `JDDocument \| None` | Generated JD sections from Phase 2 |
| `ready_to_generate` | `bool` | Set when Gather agent calls `signal_ready` |
| `brand_color` | `str` | Hex color chosen by user (default `#1D3557`) |
| `logo_bytes` | `bytes \| None` | Uploaded logo image bytes |

---

## 4. Agent Contracts

### 4.1 Gather Agent — `agents/jd_builder_gather.py`

**Model:** `claude-sonnet-4-6`  
**Entry:** `gather_turn(messages, client) -> (reply: str, brief: JDQIBrief | None)`

**System prompt responsibilities:**
- Ask one question at a time; infer expertise from answer depth and skip obvious follow-ups for expert users
- Cover dimensions in this order: role basics (title, industry, seniority, location/remote) → responsibilities → required skills (name + version/proficiency level) → preferred skills → success criteria → reporting structure → growth path → compensation → inclusion signals
- For each skippable dimension, if user wants to skip: warn with estimated JDQI score impact (e.g., "Skipping compensation will likely cost ~10 JDQI points") and record in `skipped_dimensions`
- Call `signal_ready` tool when all required fields are filled or consciously skipped

**Tool: `signal_ready`**

Input schema (`JDQIBrief`):
```json
{
  "role_title": "string",
  "industry": "string",
  "seniority_level": "junior | mid | senior | lead | director",
  "location": "string",
  "remote_policy": "on-site | hybrid | remote | flexible",
  "company_description": "string",
  "responsibilities": ["string"],
  "required_skills": [{"name": "string", "version_or_level": "string"}],
  "preferred_skills": ["string"],
  "success_criteria": ["string"],
  "reporting_structure": "string | null",
  "growth_path": "string | null",
  "compensation": "string | null",
  "inclusion_statement": "string | null",
  "skipped_dimensions": [{"dimension": "string", "jdqi_impact_note": "string"}]
}
```

When the tool is called:
1. Set `st.session_state.jdqi_brief = brief`
2. Set `st.session_state.ready_to_generate = True`
3. Agent reply shown in chat: confirmation that enough info has been gathered + prompt to confirm generation

### 4.2 Draft Agent — `agents/jd_builder_draft.py`

**Model:** `claude-sonnet-4-6`  
**Entry:** `draft_jd(brief: JDQIBrief, client) -> JDDocument`

Receives the clean `JDQIBrief`. Writes a complete, JDQI-optimised JD. Returns `JDDocument`:

```json
{
  "role_title": "string",
  "about_company": "string (2-3 sentences)",
  "about_role": "string (2-3 sentences)",
  "responsibilities": ["string (action-verb led)"],
  "required_skills": ["string (with version/level)"],
  "preferred_skills": ["string"],
  "success_criteria": ["string"],
  "reporting_structure": "string | null",
  "growth_path": "string | null",
  "compensation": "string | null",
  "equal_opportunity": "string"
}
```

System prompt instructs: use active voice, specific skill versions, inclusive language, Flesch-Kincaid grade ≤ 12, no exclusionary phrases.

---

## 5. Docx Builder — `agents/jd_docx.py`

**Entry:** `build_docx(doc: JDDocument, brand_color: str, logo_bytes: bytes | None) -> bytes`

**Document structure:**
| Element | Style |
|---------|-------|
| Header | Role title (left) + date (right), thin accent line in `brand_color` |
| Logo | 3cm × 3cm image top-right, or grey placeholder box if absent |
| Section headings | Bold, `brand_color`, 14pt |
| Body text | Calibri 11pt, dark grey `#1A1A1A` |
| Bullet lists | Standard indent, 10pt |
| Footer | "Built with JDQI · Confidential" centred |

**Color schemes (presets + free input):**
| Name | Hex |
|------|-----|
| Corporate Navy (default) | `#1D3557` |
| JDQI Red | `#C8102E` |
| Charcoal | `#2D2D2D` |
| Custom | Free hex input |

---

## 6. Guardrails Integration

Reuses `agents/guardrails.py` (`check_guardrail`, `extract_report_text`).

| Gate | Trigger | On block |
|------|---------|----------|
| INPUT | Every user chat message | Error shown in chat; message not added to history; no LLM call |
| OUTPUT | After Draft Agent returns `JDDocument` (checks all text fields) | Error shown; download button not rendered |

For the output gate, a helper `extract_jd_text(doc: JDDocument) -> str` concatenates all prose fields for the guardrail check.

---

## 7. UI Design

`app.py` gains two tabs:
```python
tab1, tab2 = st.tabs(["🔍 Analyse JD", "📝 Build JD"])
```

**Build JD tab layout:**

```
┌──────────────────────────────────────────────┐
│  Brand Color  [● #1D3557 ▾]   Logo [Upload]  │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  Chat window (st.container, scrollable)       │
│  ┌──────────────────────────────────────┐    │
│  │ 🤖 Hi! I'll help you build a         │    │
│  │    JDQI-compliant JD. Let's start…  │    │
│  └──────────────────────────────────────┘    │
│  ┌──────────────────────────────────────┐    │
│  │ 👤 [user message]                    │    │
│  └──────────────────────────────────────┘    │
│                    ...                        │
│  [ ✉ Type your message…  ]  [ Send ▶ ]       │
└──────────────────────────────────────────────┘

── shown after generation confirmed + guardrail passed ──
┌──────────────────────────────────────────────┐
│  ✅ Bedrock Guardrail (OUTPUT)  Passed        │
│  📄 JD ready — [Role Title]                  │
│  [ ⬇ Download .docx ]   [ 🔄 Start over ]   │
└──────────────────────────────────────────────┘
```

**Behaviours:**
- Guardrail INPUT runs before each LLM call; blocked messages show an error in the chat area, are not added to history, and do not reach the agent
- Color picker: 3 preset buttons + text input for custom hex
- Logo upload: `st.file_uploader`, PNG/JPG, optional; stored in `st.session_state.logo_bytes`
- "Start over" clears all `builder_*` session state keys and reruns

---

## 8. New Files

| File | Purpose |
|------|---------|
| `agents/jd_builder_gather.py` | Phase 1: Gather agent — chat turns, `signal_ready` tool |
| `agents/jd_builder_draft.py` | Phase 2: Draft agent — JDQIBrief → JDDocument |
| `agents/jd_docx.py` | python-docx builder — JDDocument + brand → .docx bytes |

**Modified files:**
| File | Change |
|------|--------|
| `app.py` | Wrap existing content in tab 1; add Build JD tab 2 with chat UI |
| `models/context.py` | Add `JDQIBrief` and `JDDocument` TypedDicts |
| `requirements.txt` | Add `python-docx>=1.1.0` |

---

## 9. Key Design Decisions

- **Two-phase separation** — Gather agent fills a structured brief; Draft agent writes prose from the brief. The draft LLM never sees raw chat history, only the clean brief. Higher quality output.
- **`signal_ready` tool** — mirrors the `consult_advisor` tool pattern already in the codebase. Sonnet decides readiness internally; the tool call is the handoff signal.
- **Guardrail on every user message** — INPUT gate fires before any LLM call. Blocked messages are not stored in `builder_messages`, so the conversation history stays clean.
- **Tab layout** — wraps existing `app.py` content in `st.tabs`, zero regression risk to the Analyse tab.
- **python-docx over WeasyPrint/HTML** — simpler dependency for .docx output; no need for a browser renderer. WeasyPrint is already in use on the backend project (Adizes) but not here.
