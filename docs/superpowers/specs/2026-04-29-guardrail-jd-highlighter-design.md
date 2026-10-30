# Design: Guardrail Output Block — JD Highlighter

**Date:** 2026-04-29  
**Feature:** When the OUTPUT Bedrock guardrail blocks the advisor report, scan the original JD text with Claude Haiku and display it with problematic phrases highlighted.

---

## Problem

When the Analyse JD pipeline's OUTPUT guardrail blocks (e.g. `Discriminatory_Hiring_Criteria`), the user currently sees only a terse error message. They have no visibility into *which part of their JD* caused the issue, making it hard to fix and re-submit.

The guardrail checks the **advisor report**, not the JD directly — but the report discusses discriminatory language *because it found it in the JD*. The root cause is always in the JD text.

---

## Solution

On output guardrail block, make a single targeted Claude Haiku call to identify exact verbatim phrases in the JD that match the block reason. Render the JD with those phrases wrapped in `<mark>` highlight spans inside a Streamlit `st.markdown(unsafe_allow_html=True)` block.

No retry, no rewrite — this is a diagnostic display only.

---

## Data Flow

```
run_pipeline() — output guardrail blocks
    │
    ├── show existing error banner (unchanged)
    │
    └── scan_jd_for_violations(jd_text, blocked_reason, client)
            │  Haiku call — ~2s
            ▼
        list[str]  — exact quoted phrases from JD
            │
            └── _render_jd_with_highlights(jd_text, phrases)
                    │  HTML escape + <mark> injection
                    ▼
                st.markdown(unsafe_allow_html=True)
                    — scrollable JD with amber highlights
                    — phrase count badge
                    — caption explaining what to do
```

---

## Components

### 1. `agents/guardrails.py` — `scan_jd_for_violations()`

```python
def scan_jd_for_violations(
    jd_text: str,
    blocked_reason: str,
    client: anthropic.Anthropic,
) -> list[str]:
```

- Model: `claude-haiku-4-5-20251001`
- Max tokens: 512 (phrase list is short)
- System prompt: instructs Haiku to find verbatim phrases matching the block category
- Returns JSON array of exact quoted strings from the JD
- On any exception (API error, JSON parse failure): returns `[]` — never crashes the UI
- Prompt maps known block category names to concrete examples:
  - `Discriminatory_Hiring_Criteria` → age requirements, gender/race preferences, physical requirements, nationality bias
  - `contentPolicy` filters → hate speech, violence, etc.
  - Blocked word/phrase → that exact word
  - PII → personal identifiers
- Extracts JSON from response by finding the first `[` … `]` array block (inline, not shared with advisor/draft helpers)

### 2. `app.py` — `_render_jd_with_highlights()`

```python
def _render_jd_with_highlights(jd_text: str, phrases: list[str]) -> None:
```

- HTML-escapes the full JD text
- For each phrase (HTML-escaped): replaces **all occurrences** with `<mark>` span
  - Style: `background:#FEF3C7; color:#92400E; padding:1px 3px; border-radius:3px; font-weight:600`
- Wraps in `<div>` with `white-space:pre-wrap`, monospace font, max-height 300px, overflow-y scroll
- Renders via `st.markdown(..., unsafe_allow_html=True)`
- Header row: dark banner reading "🔍 Issues found in your JD" + red badge with phrase count
- Caption below: "Highlighted phrases likely triggered the guardrail. Revise them and re-analyse."
- If `phrases` is empty: shows a fallback message — "Could not automatically pinpoint specific phrases. Review the JD for language that could be considered discriminatory or exclusionary."

### 3. `app.py` — `run_pipeline()` — output block path

Current code (lines 134–139):
```python
if not gr_out.passed:
    output_ph.error(...)
    return
```

New code:
```python
if not gr_out.passed:
    output_ph.error(...)
    with st.spinner("Scanning JD for problematic phrases…"):
        phrases = scan_jd_for_violations(jd_text, gr_out.blocked_reason or "", client)
    _render_jd_with_highlights(jd_text, phrases)
    return
```

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| Haiku API error | `scan_jd_for_violations` returns `[]`; fallback message shown |
| JSON parse failure | Same — returns `[]` |
| Phrase not found in JD text | Skip that phrase silently (substring match miss) |
| All phrases miss | Fallback message shown |
| Output guardrail passes | No change — existing happy path untouched |

---

## Guardrail Import

`app.py` already imports `check_guardrail` and `extract_report_text` from `agents.guardrails`. The new `scan_jd_for_violations` is added to the same import line. The `anthropic.Anthropic` client is already threaded through `run_pipeline()` so no signature changes needed.

---

## Out of Scope

- No course-correction or auto-rewrite (that's Build JD's loop — not Analyse JD's job)
- No highlighting for INPUT guardrail blocks (JD text is immediately visible to the user in the form)
- No changes to the Build JD tab
- No changes to the guardrail configuration or Bedrock settings

---

## Files Changed

| File | Change |
|------|--------|
| `agents/guardrails.py` | Add `scan_jd_for_violations()` |
| `app.py` | Add `_render_jd_with_highlights()`; update output-block path in `run_pipeline()` |
