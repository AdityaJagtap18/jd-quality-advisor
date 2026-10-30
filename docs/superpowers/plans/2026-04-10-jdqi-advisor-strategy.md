# JD Quality Intelligence (JDQI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit app demonstrating the Claude Advisor Strategy — Sonnet specialists run 6 dimension analyzers in parallel, a Sonnet synthesis executor calls Opus via a tool call, producing a scored JDQI report with actionable recruiter suggestions.

**Architecture:** 9-agent pipeline: JD Parser → 6 parallel Specialist Analyzers (ThreadPoolExecutor) → Synthesis Executor (Sonnet, tool loop) → Advisor (Opus, on-demand via `consult_advisor` tool). All agents share a Python dict as context. UI updates live via Streamlit placeholders.

**Tech Stack:** Python 3.11+, `anthropic>=0.49.0`, `streamlit>=1.43.0`, `python-dotenv>=1.0.0`, venv

---

## File Map

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI: input form, pipeline progress, JDQI report, suggested additions |
| `agents/parser.py` | Agent 1: extract structured JD fields from raw text |
| `agents/specialists.py` | Agents 2–7: 6 dimension analyzers, run in parallel via ThreadPoolExecutor |
| `agents/advisor.py` | Agent 9: Opus advisor, reads full context, returns scored report |
| `agents/synthesizer.py` | Agent 8: Sonnet synthesis executor, tool loop, calls `consult_advisor` |
| `models/context.py` | TypedDict schemas for all shared context types |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for ANTHROPIC_API_KEY |

---

## Task 1: Scaffold — venv, dependencies, directory structure

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `agents/__init__.py`
- Create: `models/__init__.py`

- [ ] **Step 1: Create and activate virtual environment**

```bash
cd ./jd-quality-advisor
python3 -m venv .venv
source .venv/bin/activate
```

Expected: `(.venv)` appears in shell prompt.

- [ ] **Step 2: Create requirements.txt**

```
anthropic>=0.49.0
streamlit>=1.43.0
python-dotenv>=1.0.0
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: All three packages install without error.

- [ ] **Step 4: Create .env.example**

```
ANTHROPIC_API_KEY=your_key_here
```

- [ ] **Step 5: Create .env with actual key**

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=<your actual key>
```

- [ ] **Step 6: Create package init files**

`agents/__init__.py` — empty file.
`models/__init__.py` — empty file.

- [ ] **Step 7: Commit scaffold**

```bash
git add requirements.txt .env.example agents/__init__.py models/__init__.py
git commit -m "feat: scaffold JDQI project with venv and dependencies"
```

---

## Task 2: Shared context models

**Files:**
- Create: `models/context.py`

- [ ] **Step 1: Write models/context.py**

```python
from typing import TypedDict, Optional


class ParsedJD(TypedDict):
    role_title: str
    seniority_level: str          # junior | mid | senior | lead
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    reporting_structure: Optional[str]
    growth_path: Optional[str]
    success_criteria: Optional[str]
    compensation: Optional[str]


class CompletenessResult(TypedDict):
    score: int                    # 0–100
    findings: list[str]
    missing: list[str]


class SkillSpecificityResult(TypedDict):
    score: int
    findings: list[str]
    vague_skills: list[str]


class CognitiveLoadResult(TypedDict):
    score: int
    findings: list[str]
    word_count: int
    grade_level: float


class InclusionResult(TypedDict):
    score: int
    findings: list[str]
    flags: list[str]


class CompensationResult(TypedDict):
    score: int
    findings: list[str]
    band_present: bool


class RoleCoherenceResult(TypedDict):
    score: int
    findings: list[str]
    mismatches: list[str]


class DimensionResults(TypedDict):
    completeness: CompletenessResult
    skill_specificity: SkillSpecificityResult
    cognitive_load: CognitiveLoadResult
    inclusion_signals: InclusionResult
    compensation: CompensationResult
    role_coherence: RoleCoherenceResult


class SuggestedAddition(TypedDict):
    section: str
    suggestion: str
    impact: str


class DimensionBreakdown(TypedDict):
    dimension: str
    score: int
    narrative: str


class AdvisorReport(TypedDict):
    jdqi_score: int
    benchmark_comparison: str
    dimension_breakdown: list[DimensionBreakdown]
    suggested_additions: list[SuggestedAddition]


class JDQIContext(TypedDict, total=False):
    jd_text: str
    industry: str
    parsed_jd: ParsedJD
    dimension_results: DimensionResults
    advisor_report: AdvisorReport
```

- [ ] **Step 2: Commit**

```bash
git add models/context.py models/__init__.py
git commit -m "feat: add JDQI shared context TypedDict schemas"
```

---

## Task 3: JD Parser agent (Agent 1)

**Files:**
- Create: `agents/parser.py`

- [ ] **Step 1: Write agents/parser.py**

```python
import json
import anthropic
from models.context import ParsedJD

_SYSTEM = """You are a JD parser. Extract structured information from the job description.
Return ONLY valid JSON — no markdown, no explanation — matching this exact schema:
{
  "role_title": "string",
  "seniority_level": "junior|mid|senior|lead",
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill1"],
  "responsibilities": ["resp1", "resp2"],
  "reporting_structure": "string or null",
  "growth_path": "string or null",
  "success_criteria": "string or null",
  "compensation": "string or null"
}"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop opening fence line and closing ``` if present
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    return text


def run_parser(jd_text: str, industry: str, client: anthropic.Anthropic) -> ParsedJD:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Industry: {industry}\n\nJob Description:\n{jd_text}"
        }]
    )
    return json.loads(_strip_fences(response.content[0].text))
```

- [ ] **Step 2: Commit**

```bash
git add agents/parser.py
git commit -m "feat: add JD parser agent (Agent 1)"
```

---

## Task 4: Specialist analyzers (Agents 2–7)

**Files:**
- Create: `agents/specialists.py`

- [ ] **Step 1: Write agents/specialists.py**

```python
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
import anthropic
from models.context import (
    ParsedJD, DimensionResults,
    CompletenessResult, SkillSpecificityResult, CognitiveLoadResult,
    InclusionResult, CompensationResult, RoleCoherenceResult,
)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    return text


def _call(system: str, user: str, client: anthropic.Anthropic) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return json.loads(_strip_fences(response.content[0].text))


def _analyze_completeness(parsed_jd: ParsedJD, client: anthropic.Anthropic) -> CompletenessResult:
    system = """Evaluate JD completeness. Score 0–100 based on how many of these elements are present:
required_skills, preferred_skills, responsibilities, success_criteria, reporting_structure, growth_path.
Return ONLY valid JSON:
{"score": <int>, "findings": ["<observation>"], "missing": ["<element name>"]}"""
    return _call(system, f"Parsed JD:\n{json.dumps(parsed_jd, indent=2)}", client)


def _analyze_skill_specificity(parsed_jd: ParsedJD, client: anthropic.Anthropic) -> SkillSpecificityResult:
    system = """Evaluate skill specificity in the JD. High score (100) = all tools/skills have versions or
proficiency levels. Low score = vague terms like "experience with databases" with no specifics.
Return ONLY valid JSON:
{"score": <int>, "findings": ["<observation>"], "vague_skills": ["<skill>"]}"""
    return _call(system, f"Parsed JD:\n{json.dumps(parsed_jd, indent=2)}", client)


def _analyze_cognitive_load(jd_text: str, client: anthropic.Anthropic) -> CognitiveLoadResult:
    system = """Evaluate cognitive load of this JD text. Measure:
- word_count: exact word count
- grade_level: Flesch-Kincaid reading grade estimate (float)
- score: 0–100 readability score (100 = very readable, 0 = overwhelming jargon)
- findings: specific observations about length, jargon, or structure.
Return ONLY valid JSON:
{"score": <int>, "findings": ["<observation>"], "word_count": <int>, "grade_level": <float>}"""
    return _call(system, f"JD text:\n{jd_text}", client)


def _analyze_inclusion_signals(jd_text: str, client: anthropic.Anthropic) -> InclusionResult:
    system = """Scan this JD for exclusionary language that may deter qualified candidates.
Examples: "rockstar", "ninja", "young and dynamic", "native speaker", gendered pronouns used exclusively.
Score 0–100 (100 = fully inclusive, no flags).
Return ONLY valid JSON:
{"score": <int>, "findings": ["<observation>"], "flags": ["<exact phrase flagged>"]}"""
    return _call(system, f"JD text:\n{jd_text}", client)


def _analyze_compensation(parsed_jd: ParsedJD, jd_text: str, client: anthropic.Anthropic) -> CompensationResult:
    system = """Check whether this JD includes a compensation/salary band.
band_present = true only if a specific range or figure is stated.
Score: 100 if clear range stated, 50 if vague mention of "competitive salary", 0 if absent.
Return ONLY valid JSON:
{"score": <int>, "findings": ["<observation>"], "band_present": <bool>}"""
    user = f"Parsed JD:\n{json.dumps(parsed_jd, indent=2)}\n\nFull text:\n{jd_text}"
    return _call(system, user, client)


def _analyze_role_coherence(parsed_jd: ParsedJD, client: anthropic.Anthropic) -> RoleCoherenceResult:
    system = """Evaluate whether the JD requirements and responsibilities are coherent with the stated seniority level.
Flag issues like: "3 years experience" for a senior role, "5+ years required" for a mid role,
responsibilities that belong to a higher/lower level, or skill lists that mix entry-level and expert demands.
Score 0–100 (100 = fully coherent).
Return ONLY valid JSON:
{"score": <int>, "findings": ["<observation>"], "mismatches": ["<specific mismatch>"]}"""
    return _call(system, f"Parsed JD:\n{json.dumps(parsed_jd, indent=2)}", client)


_ANALYZERS = {
    "completeness":      lambda jd_text, parsed_jd, client: _analyze_completeness(parsed_jd, client),
    "skill_specificity": lambda jd_text, parsed_jd, client: _analyze_skill_specificity(parsed_jd, client),
    "cognitive_load":    lambda jd_text, parsed_jd, client: _analyze_cognitive_load(jd_text, client),
    "inclusion_signals": lambda jd_text, parsed_jd, client: _analyze_inclusion_signals(jd_text, client),
    "compensation":      lambda jd_text, parsed_jd, client: _analyze_compensation(parsed_jd, jd_text, client),
    "role_coherence":    lambda jd_text, parsed_jd, client: _analyze_role_coherence(parsed_jd, client),
}

_ERROR_DEFAULTS = {
    "completeness":      {"score": 0, "findings": [], "missing": []},
    "skill_specificity": {"score": 0, "findings": [], "vague_skills": []},
    "cognitive_load":    {"score": 0, "findings": [], "word_count": 0, "grade_level": 0.0},
    "inclusion_signals": {"score": 0, "findings": [], "flags": []},
    "compensation":      {"score": 0, "findings": [], "band_present": False},
    "role_coherence":    {"score": 0, "findings": [], "mismatches": []},
}


def run_specialists(
    jd_text: str,
    parsed_jd: ParsedJD,
    client: anthropic.Anthropic,
    progress_callback: Optional[Callable[[str, dict], None]] = None,
) -> DimensionResults:
    """Run all 6 specialist agents in parallel. Calls progress_callback(key, result) from main thread as each completes."""
    results: dict = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_key = {
            executor.submit(fn, jd_text, parsed_jd, client): key
            for key, fn in _ANALYZERS.items()
        }
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                results[key] = future.result()
            except Exception as e:
                results[key] = {**_ERROR_DEFAULTS[key], "findings": [f"Analysis failed: {e}"]}
            if progress_callback:
                progress_callback(key, results[key])

    return results  # type: ignore[return-value]
```

- [ ] **Step 2: Commit**

```bash
git add agents/specialists.py
git commit -m "feat: add 6 parallel specialist analyzer agents (Agents 2-7)"
```

---

## Task 5: Advisor agent (Agent 9 — Opus)

**Files:**
- Create: `agents/advisor.py`

- [ ] **Step 1: Write agents/advisor.py**

```python
import json
import anthropic
from models.context import JDQIContext, AdvisorReport


_SYSTEM = """You are a senior talent acquisition expert with deep knowledge of hiring best practices
across High-tech Manufacturing, IT/SaaS/AI, and GCC (Global Capability Centre) industries.

You will receive a complete JD quality analysis. Produce a comprehensive JDQI report.

Return ONLY valid JSON matching this exact schema (no markdown, no explanation):
{
  "jdqi_score": <int 0-100, weighted composite>,
  "benchmark_comparison": "<2-3 paragraph narrative comparing this JD to best-in-class JDs for this role and industry>",
  "dimension_breakdown": [
    {"dimension": "completeness", "score": <int>, "narrative": "<1-2 sentences>"},
    {"dimension": "skill_specificity", "score": <int>, "narrative": "<1-2 sentences>"},
    {"dimension": "cognitive_load", "score": <int>, "narrative": "<1-2 sentences>"},
    {"dimension": "inclusion_signals", "score": <int>, "narrative": "<1-2 sentences>"},
    {"dimension": "compensation", "score": <int>, "narrative": "<1-2 sentences>"},
    {"dimension": "role_coherence", "score": <int>, "narrative": "<1-2 sentences>"}
  ],
  "suggested_additions": [
    {"section": "<section name>", "suggestion": "<specific text or content to add>", "impact": "<why this matters for hiring outcomes>"},
    ... (3-6 suggestions, most impactful first)
  ]
}

Scoring weights: completeness 25%, skill_specificity 20%, role_coherence 20%, cognitive_load 15%, inclusion_signals 10%, compensation 10%."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    return text


def run_advisor(context: JDQIContext, client: anthropic.Anthropic) -> AdvisorReport:
    """Opus advisor — reads full shared context, returns scored JDQI report."""
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4000,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Role: {context['parsed_jd']['role_title']} | "
                f"Industry: {context['industry']} | "
                f"Seniority: {context['parsed_jd']['seniority_level']}\n\n"
                f"Specialist dimension results:\n{json.dumps(context['dimension_results'], indent=2)}\n\n"
                f"Original JD:\n{context['jd_text']}"
            )
        }]
    )
    return json.loads(_strip_fences(response.content[0].text))
```

- [ ] **Step 2: Commit**

```bash
git add agents/advisor.py
git commit -m "feat: add Opus advisor agent (Agent 9)"
```

---

## Task 6: Synthesis executor (Agent 8 — Sonnet tool loop)

**Files:**
- Create: `agents/synthesizer.py`

- [ ] **Step 1: Write agents/synthesizer.py**

```python
import json
from typing import Callable, Optional
import anthropic
from models.context import JDQIContext, AdvisorReport
from agents.advisor import run_advisor


_ADVISOR_TOOL = {
    "name": "consult_advisor",
    "description": (
        "Consult the Opus advisor for benchmark comparison, composite JDQI scoring, "
        "and recruiter-facing recommendations. Call this once with a brief summary "
        "of the most critical findings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "brief": {
                "type": "string",
                "description": "2-3 sentence summary of the JD and the most critical specialist findings",
            }
        },
        "required": ["brief"],
    },
}


def run_synthesizer(
    context: JDQIContext,
    client: anthropic.Anthropic,
    on_advisor_called: Optional[Callable[[], None]] = None,
) -> AdvisorReport:
    """
    Synthesis executor (Sonnet). Reviews dimension results, then calls consult_advisor
    tool exactly once to invoke the Opus advisor. Returns the AdvisorReport.
    """
    dim_summary = "\n".join(
        f"  {k}: score={v.get('score', 'N/A')}"
        for k, v in context.get("dimension_results", {}).items()
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"You are reviewing a JD for a {context['parsed_jd']['role_title']} role "
                f"in the {context['industry']} industry "
                f"(seniority: {context['parsed_jd']['seniority_level']}).\n\n"
                f"Specialist dimension scores:\n{dim_summary}\n\n"
                "Use the consult_advisor tool to get expert benchmark comparison "
                "and recruiter recommendations. Pass a brief summary of the most critical findings."
            ),
        }
    ]

    advisor_report: Optional[AdvisorReport] = None

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            tools=[_ADVISOR_TOOL],
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_block = next(b for b in response.content if b.type == "tool_use")

            # Notify UI that advisor is now being called
            if on_advisor_called:
                on_advisor_called()

            # Call Opus advisor with the full shared context
            advisor_report = run_advisor(context, client)

            # Return the tool result to complete the executor's loop
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": json.dumps({
                            "status": "completed",
                            "jdqi_score": advisor_report["jdqi_score"],
                        }),
                    }
                ],
            })

        elif response.stop_reason == "end_turn":
            break
        else:
            # Unexpected stop reason — break and fall through to fallback
            break

    if advisor_report is None:
        # Fallback: executor didn't call the tool — invoke advisor directly
        if on_advisor_called:
            on_advisor_called()
        advisor_report = run_advisor(context, client)

    return advisor_report
```

- [ ] **Step 2: Commit**

```bash
git add agents/synthesizer.py
git commit -m "feat: add synthesis executor with consult_advisor tool loop (Agent 8)"
```

---

## Task 7: Streamlit app

**Files:**
- Create: `app.py`

- [ ] **Step 1: Write app.py**

```python
import os
import anthropic
import streamlit as st
from dotenv import load_dotenv

from agents.parser import run_parser
from agents.specialists import run_specialists
from agents.synthesizer import run_synthesizer
from models.context import JDQIContext

load_dotenv()

INDUSTRIES = ["High-tech Manufacturing", "IT/SaaS/AI", "GCC", "Other"]

DIM_LABELS = {
    "completeness": "Completeness",
    "skill_specificity": "Skill Specificity",
    "cognitive_load": "Cognitive Load",
    "inclusion_signals": "Inclusion Signals",
    "compensation": "Compensation",
    "role_coherence": "Role Coherence",
}

SCORE_LABEL = {
    (75, 100): ("Excellent", "normal"),
    (50, 74):  ("Fair", "off"),
    (0, 49):   ("Needs Work", "inverse"),
}


def _score_label(score: int) -> tuple[str, str]:
    for (lo, hi), val in SCORE_LABEL.items():
        if lo <= score <= hi:
            return val
    return ("Unknown", "off")


def _get_client() -> anthropic.Anthropic:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        st.error(
            "ANTHROPIC_API_KEY not found. "
            "Create a `.env` file with `ANTHROPIC_API_KEY=your_key` and restart."
        )
        st.stop()
    return anthropic.Anthropic(api_key=key)


def run_pipeline(jd_text: str, industry: str, client: anthropic.Anthropic) -> None:
    context: JDQIContext = {"jd_text": jd_text, "industry": industry}

    st.divider()
    st.subheader("Pipeline")

    # ── Agent 1: Parser ──────────────────────────────────────────────
    parser_ph = st.empty()
    parser_ph.info("⏳ **Agent 1 — JD Parser** (Sonnet)  Extracting structure...")
    try:
        context["parsed_jd"] = run_parser(jd_text, industry, client)
        parser_ph.success(
            f"✅ **Agent 1 — JD Parser**  "
            f"`{context['parsed_jd']['role_title']}` · "
            f"{context['parsed_jd']['seniority_level']} · "
            f"{len(context['parsed_jd']['required_skills'])} required skills"
        )
    except Exception as e:
        parser_ph.error(f"❌ JD Parser failed — {e}")
        return

    # ── Agents 2–7: Specialists (parallel) ──────────────────────────
    st.write("**Agents 2–7 — Specialist Analyzers** (Sonnet, parallel)")
    spec_cols = st.columns(3)
    spec_placeholders: dict[str, st.delta_generator.DeltaGenerator] = {}
    dims = list(DIM_LABELS.keys())

    for i, dim in enumerate(dims):
        ph = spec_cols[i % 3].empty()
        ph.info(f"⏳ {DIM_LABELS[dim]}")
        spec_placeholders[dim] = ph

    def on_specialist_done(key: str, result: dict) -> None:
        spec_placeholders[key].success(f"✅ {DIM_LABELS[key]} — {result.get('score', '?')}/100")

    try:
        context["dimension_results"] = run_specialists(
            jd_text, context["parsed_jd"], client, on_specialist_done
        )
    except Exception as e:
        st.error(f"Specialist analysis failed — {e}")
        return

    # ── Agent 8: Synthesis + Advisor ─────────────────────────────────
    synth_ph = st.empty()
    synth_ph.info("⏳ **Agent 8 — Synthesis Executor** (Sonnet)  Building brief...")

    advisor_ph = st.empty()
    advisor_ph.warning("🔶 **Agent 9 — Advisor** (Opus)  Waiting for tool call...")

    def on_advisor_called() -> None:
        synth_ph.info("⏳ **Agent 8 — Synthesis Executor**  Tool call dispatched → Advisor")
        advisor_ph.warning("🔶 **Agent 9 — Advisor** (Opus)  Consulting... (this may take ~30s)")

    try:
        context["advisor_report"] = run_synthesizer(context, client, on_advisor_called)
        synth_ph.success("✅ **Agent 8 — Synthesis Executor**  Complete")
        advisor_ph.success(
            f"✅ **Agent 9 — Advisor** (Opus)  "
            f"JDQI Score: {context['advisor_report']['jdqi_score']}/100"
        )
    except Exception as e:
        advisor_ph.error(f"❌ Advisor failed — {e}")
        st.button("Retry Advisor", on_click=lambda: None)
        return

    # Store result for re-render on button clicks
    st.session_state.jdqi_context = context
    st.session_state.accepted = []


def display_report(context: JDQIContext) -> None:
    report = context["advisor_report"]
    score = report["jdqi_score"]
    label, delta_color = _score_label(score)

    st.divider()
    st.subheader("JDQI Report")

    col1, col2 = st.columns([1, 3])
    col1.metric("JDQI Score", f"{score} / 100", delta=label, delta_color=delta_color)
    col2.progress(score / 100)

    # ── Dimension breakdown ──────────────────────────────────────────
    st.subheader("Dimension Breakdown")
    for item in report["dimension_breakdown"]:
        dim = item["dimension"]
        c1, c2, c3 = st.columns([2, 1, 5])
        c1.write(f"**{DIM_LABELS.get(dim, dim.replace('_', ' ').title())}**")
        c2.write(f"**{item['score']}**/100")
        c3.progress(item["score"] / 100)
        st.caption(f"  {item['narrative']}")

    # ── Benchmark comparison ─────────────────────────────────────────
    with st.expander("Benchmark Comparison (Opus Analysis)", expanded=False):
        st.write(report["benchmark_comparison"])

    # ── Suggested additions ──────────────────────────────────────────
    st.divider()
    st.subheader("Suggested Additions")
    st.caption("Accept suggestions to build your revised JD additions.")

    for i, s in enumerate(report["suggested_additions"]):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 4, 3, 1])
            c1.write(f"**{s['section']}**")
            c2.write(s["suggestion"])
            c3.caption(s["impact"])
            if c4.button("Accept", key=f"accept_{i}"):
                entry = f"[{s['section']}] {s['suggestion']}"
                if entry not in st.session_state.accepted:
                    st.session_state.accepted.append(entry)

    if st.session_state.get("accepted"):
        st.subheader("Revised JD Additions")
        st.code("\n\n".join(st.session_state.accepted), language=None)
        st.button(
            "Clear selections",
            on_click=lambda: st.session_state.update({"accepted": []}),
        )


def main() -> None:
    st.set_page_config(
        page_title="JD Quality Intelligence",
        page_icon="🎯",
        layout="wide",
    )
    st.title("🎯 JD Quality Intelligence (JDQI)")
    st.caption(
        "**Claude Advisor Strategy demo** — "
        "Sonnet specialists analyse in parallel · Opus advisor consulted on-demand via tool call"
    )

    client = _get_client()

    # ── Input form ───────────────────────────────────────────────────
    with st.form("jd_form"):
        jd_text = st.text_area(
            "Paste your Job Description",
            height=320,
            placeholder="Paste the full JD text here…",
        )
        industry = st.selectbox("Industry", INDUSTRIES)
        submitted = st.form_submit_button("Analyse JD ▶", type="primary", use_container_width=True)

    if submitted:
        if not jd_text.strip():
            st.warning("Please paste a job description before analysing.")
        else:
            # Reset previous results
            st.session_state.jdqi_context = None
            st.session_state.accepted = []
            run_pipeline(jd_text, industry, client)

    # ── Render stored report (persists across Accept button clicks) ──
    if st.session_state.get("jdqi_context"):
        display_report(st.session_state.jdqi_context)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "feat: add Streamlit JDQI app with 4-screen pipeline UI"
```

---

## Task 8: Launch

- [ ] **Step 1: Verify .env has ANTHROPIC_API_KEY set**

```bash
grep ANTHROPIC_API_KEY ./jd-quality-advisor/.env
```

Expected: `ANTHROPIC_API_KEY=sk-ant-...` (your actual key)

- [ ] **Step 2: Activate venv and run Streamlit**

```bash
cd ./jd-quality-advisor
source .venv/bin/activate
streamlit run app.py --server.port 8501
```

Expected: Streamlit opens at http://localhost:8501

- [ ] **Step 3: Smoke test**

Paste a sample JD (any real JD), select industry, click "Analyse JD".
Verify:
- Parser completes and shows role title
- 6 specialists update to ✅ as they complete
- Advisor status changes to "Consulting..."
- Final JDQI score appears
- Dimension breakdown renders with progress bars
- Suggested additions table shows with Accept buttons
