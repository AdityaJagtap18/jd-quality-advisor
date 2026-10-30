# Guardrail JD Highlighter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the Analyse JD OUTPUT guardrail blocks, make a Haiku call to find exact problematic phrases in the JD, then display the JD with those phrases highlighted in amber.

**Architecture:** New `scan_jd_for_violations()` function in `agents/guardrails.py` (Haiku call → `list[str]`). New `_build_highlighted_html()` pure function + `_render_jd_with_highlights()` UI function in `app.py`. The output-block path in `run_pipeline()` calls both in sequence.

**Tech Stack:** `anthropic` SDK (`claude-haiku-4-5-20251001`), `json` stdlib, `html` stdlib, Streamlit `st.markdown(unsafe_allow_html=True)`, `pytest` + `unittest.mock`.

---

## File Map

| File | Change |
|------|--------|
| `agents/guardrails.py` | Add `import json`, `import anthropic`; add `scan_jd_for_violations()` |
| `app.py` | Add `scan_jd_for_violations` to guardrails import; add `_build_highlighted_html()`; add `_render_jd_with_highlights()`; update output-block path in `run_pipeline()` |
| `tests/test_guardrail_highlighter.py` | New — unit tests for both new functions |

---

## Task 1: `scan_jd_for_violations()` in `agents/guardrails.py`

**Files:**
- Modify: `agents/guardrails.py` (add imports at top, add function at bottom)
- Create: `tests/test_guardrail_highlighter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_guardrail_highlighter.py`:

```python
import pytest
from unittest.mock import MagicMock
from agents.guardrails import scan_jd_for_violations


def _make_client(response_text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def test_scan_returns_phrases_from_valid_json():
    client = _make_client('["young and energetic", "candidates aged 25-35"]')
    result = scan_jd_for_violations(
        "We want young and energetic candidates aged 25-35.",
        "Topic blocked: Discriminatory_Hiring_Criteria (DENY)",
        client,
    )
    assert result == ["young and energetic", "candidates aged 25-35"]


def test_scan_handles_text_around_json():
    client = _make_client('Here are the phrases: ["male preferred"]\nDone.')
    result = scan_jd_for_violations("male preferred applicants only.", "Topic blocked: X", client)
    assert result == ["male preferred"]


def test_scan_returns_empty_list_on_json_parse_failure():
    client = _make_client("Sorry, I cannot identify any phrases.")
    result = scan_jd_for_violations("Some JD text.", "Topic blocked: X", client)
    assert result == []


def test_scan_returns_empty_list_on_api_exception():
    client = MagicMock()
    client.messages.create.side_effect = Exception("API error")
    result = scan_jd_for_violations("Some JD text.", "Topic blocked: X", client)
    assert result == []


def test_scan_returns_empty_list_for_empty_jd():
    client = _make_client('["phrase"]')
    result = scan_jd_for_violations("", "Topic blocked: X", client)
    assert result == []
    client.messages.create.assert_not_called()


def test_scan_returns_empty_list_for_empty_array_response():
    client = _make_client("[]")
    result = scan_jd_for_violations("Normal JD text.", "Topic blocked: X", client)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ./jd-quality-advisor && source .venv/bin/activate
python -m pytest tests/test_guardrail_highlighter.py -v
```

Expected: `ImportError` or `AttributeError` — `scan_jd_for_violations` does not exist yet.

- [ ] **Step 3: Add imports to `agents/guardrails.py`**

After line 19 (`from typing import Optional`), add two imports so the block reads:

```python
import json
import os
from dataclasses import dataclass
from typing import Optional

import anthropic
import boto3
from botocore.exceptions import BotoCoreError, ClientError
```

(Replace the existing import block at lines 17–22 with the above.)

- [ ] **Step 4: Add `scan_jd_for_violations()` at the bottom of `agents/guardrails.py`**

Append after the `extract_report_text` function:

```python
def scan_jd_for_violations(
    jd_text: str,
    blocked_reason: str,
    client: anthropic.Anthropic,
) -> list[str]:
    """Call Claude Haiku to find verbatim phrases in jd_text that match the block reason.

    Returns a list of exact quoted strings from jd_text, or [] on any failure.
    """
    if not jd_text or not jd_text.strip():
        return []

    prompt = (
        f"You are analysing a job description that triggered an AI content guardrail.\n\n"
        f"Guardrail block reason: {blocked_reason}\n\n"
        "Scan the job description below and identify EXACT verbatim phrases or sentences "
        "that likely caused this guardrail violation.\n\n"
        "Guidelines by block type:\n"
        "- Discriminatory_Hiring_Criteria: age requirements, gender/race/religion/nationality "
        "preferences, physical appearance requirements, overly restrictive experience filters "
        "that exclude protected groups (e.g. 'young and energetic', 'candidates aged 25–35')\n"
        "- Content filter (hate/violence/sexual/insults): offensive language, slurs, explicit content\n"
        "- Blocked word/phrase: look for that exact word or phrase\n"
        "- PII detected: personal names, phone numbers, personal email addresses in the JD body\n\n"
        f"Job Description:\n{jd_text[:10_000]}\n\n"
        "Return ONLY a JSON array of verbatim strings copied exactly from the text above. "
        "If nothing specific is identifiable, return: []"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        return json.loads(raw[start : end + 1])
    except Exception:
        return []
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_guardrail_highlighter.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 6: Run full test suite to verify no regressions**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass (7 existing + 6 new = 13 total).

- [ ] **Step 7: Commit**

```bash
git add agents/guardrails.py tests/test_guardrail_highlighter.py
git commit -m "feat: add scan_jd_for_violations — Haiku call to find JD phrases that triggered guardrail"
```

---

## Task 2: `_build_highlighted_html()` + `_render_jd_with_highlights()` in `app.py`

**Files:**
- Modify: `app.py` (add two functions before `run_pipeline`)
- Modify: `tests/test_guardrail_highlighter.py` (add HTML tests)

- [ ] **Step 1: Add HTML tests to `tests/test_guardrail_highlighter.py`**

Append to the existing test file:

```python
from app import _build_highlighted_html


def test_build_html_highlights_phrase():
    html = _build_highlighted_html(
        "We want young professionals only.", ["young professionals only"]
    )
    assert "<mark" in html
    assert "young professionals only" in html


def test_build_html_highlights_all_occurrences():
    html = _build_highlighted_html(
        "male preferred, yes male preferred.", ["male preferred"]
    )
    assert html.count("<mark") == 2


def test_build_html_no_highlights_for_empty_phrases():
    html = _build_highlighted_html("Normal JD text.", [])
    assert "<mark" not in html
    assert "Normal JD text." in html


def test_build_html_escapes_html_chars_in_jd():
    html = _build_highlighted_html("JD with <b>bold</b> & symbols.", [])
    assert "<b>" not in html
    assert "&lt;b&gt;" in html
    assert "&amp;" in html


def test_build_html_phrase_not_in_jd_is_skipped():
    html = _build_highlighted_html("Normal JD text.", ["phrase not present"])
    assert "<mark" not in html
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_guardrail_highlighter.py::test_build_html_highlights_phrase -v
```

Expected: `ImportError` — `_build_highlighted_html` does not exist yet.

- [ ] **Step 3: Add `_build_highlighted_html()` to `app.py`**

Insert the following function in `app.py` immediately before the `run_pipeline` function definition (before line 56):

```python
def _build_highlighted_html(jd_text: str, phrases: list[str]) -> str:
    """Return the JD as an HTML block with each phrase wrapped in an amber <mark>."""
    import html as html_lib
    safe = html_lib.escape(jd_text)
    for phrase in phrases:
        safe_phrase = html_lib.escape(phrase)
        highlighted = (
            '<mark style="background:#FEF3C7;color:#92400E;'
            'padding:1px 4px;border-radius:3px;font-weight:600;">'
            f"{safe_phrase}</mark>"
        )
        safe = safe.replace(safe_phrase, highlighted)
    return (
        '<div style="background:white;border:1px solid #e2e8f0;border-radius:6px;'
        "padding:14px;font-family:monospace;font-size:13px;line-height:1.7;"
        'white-space:pre-wrap;max-height:300px;overflow-y:auto;">'
        f"{safe}</div>"
    )
```

- [ ] **Step 4: Add `_render_jd_with_highlights()` to `app.py`**

Insert immediately after `_build_highlighted_html()` (still before `run_pipeline`):

```python
def _render_jd_with_highlights(jd_text: str, phrases: list[str]) -> None:
    """Render the JD panel with highlighted phrases below the guardrail error banner."""
    count = len(phrases)
    badge_color = "#ef4444" if count > 0 else "#64748b"
    badge_text = (
        f"{count} phrase{'s' if count != 1 else ''} flagged"
        if count > 0
        else "no specific phrases identified"
    )
    st.markdown(
        '<div style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-top:8px;">'
        '<div style="background:#1e293b;color:#f8fafc;padding:10px 14px;'
        'font-size:13px;font-weight:600;">'
        f'🔍 Issues found in your JD '
        f'<span style="background:{badge_color};color:white;font-size:11px;'
        f'padding:2px 8px;border-radius:10px;margin-left:6px;">{badge_text}</span>'
        "</div></div>",
        unsafe_allow_html=True,
    )
    if phrases:
        st.caption(
            "Highlighted phrases likely triggered the guardrail — revise them and re-analyse."
        )
        st.markdown(_build_highlighted_html(jd_text, phrases), unsafe_allow_html=True)
    else:
        st.caption(
            "Could not automatically pinpoint specific phrases. "
            "Review your JD for language that could be considered discriminatory or exclusionary."
        )
```

- [ ] **Step 5: Run HTML tests to verify they pass**

```bash
python -m pytest tests/test_guardrail_highlighter.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_guardrail_highlighter.py
git commit -m "feat: add _build_highlighted_html and _render_jd_with_highlights for guardrail blocker UX"
```

---

## Task 3: Wire into `run_pipeline()` + manual smoke test

**Files:**
- Modify: `app.py` — update guardrails import line and output-block path in `run_pipeline()`

- [ ] **Step 1: Update the guardrails import in `app.py`**

Change line 9 from:

```python
from agents.guardrails import check_guardrail, extract_report_text
```

to:

```python
from agents.guardrails import check_guardrail, extract_report_text, scan_jd_for_violations
```

- [ ] **Step 2: Update the output-block path in `run_pipeline()`**

Find this block in `run_pipeline()` (around lines 134–139):

```python
    if not gr_out.passed:
        output_ph.error(
            f"🚫 **Bedrock Guardrail (OUTPUT) — Blocked.**  {gr_out.blocked_reason or 'content policy violation'}"
        )
        return
```

Replace it with:

```python
    if not gr_out.passed:
        output_ph.error(
            f"🚫 **Bedrock Guardrail (OUTPUT) — Blocked.**  {gr_out.blocked_reason or 'content policy violation'}"
        )
        with st.spinner("Scanning JD for problematic phrases…"):
            phrases = scan_jd_for_violations(jd_text, gr_out.blocked_reason or "", client)
        _render_jd_with_highlights(jd_text, phrases)
        return
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all 13 tests pass, no regressions.

- [ ] **Step 4: Smoke test in browser**

Restart the Streamlit server:

```bash
pkill -f "streamlit run" 2>/dev/null; sleep 1
source .venv/bin/activate && streamlit run app.py --server.port 8501 &
```

Open http://localhost:8501. Paste a JD containing discriminatory language such as:

```
We are looking for a young and energetic Marketing Lead.
Requirements:
- Candidates aged 25–35 preferred
- Strong communication skills
- MBA preferred
```

Click **Analyse JD**. Verify:
1. The pipeline runs all 9 agents as normal
2. The OUTPUT guardrail block banner appears in red
3. A spinner appears briefly: "Scanning JD for problematic phrases…"
4. The dark "Issues found in your JD" header appears with a red badge
5. The JD text is rendered below with "young and energetic" and "25–35" (or similar) highlighted in amber
6. A caption reads: "Highlighted phrases likely triggered the guardrail — revise them and re-analyse."

- [ ] **Step 5: Final commit**

```bash
git add app.py
git commit -m "feat: wire guardrail JD highlighter into run_pipeline output-block path"
```
