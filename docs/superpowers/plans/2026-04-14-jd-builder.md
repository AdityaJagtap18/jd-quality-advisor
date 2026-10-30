# JD Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a chat-driven JD Builder tab to the JDQI Streamlit app — a two-phase agent pipeline (Gather → Draft) that produces a branded downloadable `.docx`, gated by Bedrock Guardrails on every user message and the final output.

**Architecture:** Phase 1 Gather agent (Sonnet) conducts an adaptive conversation, filling a `JDQIBrief` struct; when complete it calls a `signal_ready` tool. Phase 2 Draft agent (Sonnet) receives the clean brief and writes structured `JDDocument` prose. A python-docx builder renders the document with configurable brand color and optional logo.

**Tech Stack:** Python 3.11, anthropic SDK 0.49+, Streamlit 1.43+, python-docx 1.1+, boto3 (existing), existing `agents/guardrails.py`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `models/context.py` | Modify | Add `JDQIBrief`, `JDDocument` TypedDicts |
| `agents/jd_builder_gather.py` | Create | Phase 1: chat turns, `signal_ready` tool loop |
| `agents/jd_builder_draft.py` | Create | Phase 2: brief → JDDocument prose |
| `agents/jd_docx.py` | Create | python-docx builder + `extract_jd_text` helper |
| `tests/test_jd_docx.py` | Create | Unit tests for docx builder (pure computation, no LLM) |
| `app.py` | Modify | Wrap existing content in tab 1; add Build JD tab 2 |
| `requirements.txt` | Modify | Add `python-docx>=1.1.0` |

---

## Task 1: Add TypedDicts to models/context.py

**Files:**
- Modify: `models/context.py`

- [ ] **Step 1: Append `JDQIBrief` and `JDDocument` TypedDicts**

Open `models/context.py` and append after the existing `JDQIContext` class:

```python
class RequiredSkill(TypedDict):
    name: str
    version_or_level: str


class SkippedDimension(TypedDict):
    dimension: str
    jdqi_impact_note: str


class JDQIBrief(TypedDict, total=False):
    role_title: str
    industry: str
    seniority_level: str          # junior | mid | senior | lead | director
    location: str
    remote_policy: str            # on-site | hybrid | remote | flexible
    company_description: str
    responsibilities: list[str]
    required_skills: list[RequiredSkill]
    preferred_skills: list[str]
    success_criteria: list[str]
    reporting_structure: Optional[str]
    growth_path: Optional[str]
    compensation: Optional[str]
    inclusion_statement: Optional[str]
    skipped_dimensions: list[SkippedDimension]


class JDDocument(TypedDict, total=False):
    role_title: str
    about_company: str
    about_role: str
    responsibilities: list[str]
    required_skills: list[str]
    preferred_skills: list[str]
    success_criteria: list[str]
    reporting_structure: Optional[str]
    growth_path: Optional[str]
    compensation: Optional[str]
    equal_opportunity: str
```

- [ ] **Step 2: Verify import works**

```bash
cd ./jd-quality-advisor
source .venv/bin/activate
python -c "from models.context import JDQIBrief, JDDocument, RequiredSkill; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add models/context.py
git commit -m "feat: add JDQIBrief and JDDocument TypedDicts"
```

---

## Task 2: Install python-docx and update requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add python-docx to requirements.txt**

```
anthropic>=0.49.0
streamlit>=1.43.0
python-dotenv>=1.0.0
boto3>=1.34.0
python-docx>=1.1.0
```

- [ ] **Step 2: Install in venv**

```bash
source .venv/bin/activate && pip install "python-docx>=1.1.0" -q
python -c "import docx; print('python-docx', docx.__version__)"
```

Expected: `python-docx 1.1.x` (or similar)

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add python-docx dependency"
```

---

## Task 3: Build `agents/jd_docx.py` + tests

**Files:**
- Create: `agents/jd_docx.py`
- Create: `tests/test_jd_docx.py`

- [ ] **Step 1: Create tests/test_jd_docx.py with failing tests**

```bash
mkdir -p ./jd-quality-advisor/tests
touch ./jd-quality-advisor/tests/__init__.py
```

Create `tests/test_jd_docx.py`:

```python
import pytest
from agents.jd_docx import _hex_to_rgb, extract_jd_text, build_docx
from models.context import JDDocument


_SAMPLE_DOC: JDDocument = {
    "role_title": "Senior ML Engineer",
    "about_company": "We build AI-powered hiring tools.",
    "about_role": "You will lead ML infrastructure.",
    "responsibilities": ["Design model pipelines", "Mentor junior engineers"],
    "required_skills": ["Python 3.11 (expert)", "PyTorch 2.x (advanced)"],
    "preferred_skills": ["Kubernetes", "MLflow"],
    "success_criteria": ["Ship v1 model pipeline within 90 days"],
    "reporting_structure": "Reports to VP of Engineering",
    "growth_path": "Path to Staff Engineer within 18 months",
    "compensation": "₹40–55 LPA + equity",
    "equal_opportunity": "We are an equal opportunity employer.",
}


def test_hex_to_rgb_navy():
    assert _hex_to_rgb("#1D3557") == (29, 53, 87)


def test_hex_to_rgb_red():
    assert _hex_to_rgb("#C8102E") == (200, 16, 46)


def test_hex_to_rgb_without_hash():
    assert _hex_to_rgb("2D2D2D") == (45, 45, 45)


def test_extract_jd_text_contains_key_fields():
    text = extract_jd_text(_SAMPLE_DOC)
    assert "Senior ML Engineer" in text
    assert "AI-powered hiring tools" in text
    assert "PyTorch 2.x" in text
    assert "equal opportunity" in text


def test_extract_jd_text_excludes_none_fields():
    doc: JDDocument = {
        "role_title": "Engineer",
        "about_company": "Acme Corp",
        "about_role": "Build things",
        "responsibilities": ["Do work"],
        "required_skills": ["Python"],
        "preferred_skills": [],
        "success_criteria": [],
        "equal_opportunity": "EOE",
    }
    text = extract_jd_text(doc)
    assert text  # non-empty
    assert "None" not in text


def test_build_docx_returns_bytes():
    result = build_docx(_SAMPLE_DOC, "#1D3557", None)
    assert isinstance(result, bytes)
    assert len(result) > 1000  # a real docx is never tiny


def test_build_docx_with_invalid_color_falls_back():
    # Should not raise — falls back to default navy
    result = build_docx(_SAMPLE_DOC, "not-a-color", None)
    assert isinstance(result, bytes)
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd ./jd-quality-advisor
source .venv/bin/activate
python -m pytest tests/test_jd_docx.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` — `agents/jd_docx.py` doesn't exist yet.

- [ ] **Step 3: Create `agents/jd_docx.py`**

```python
"""
Docx builder for JD Builder module.

build_docx(doc, brand_color, logo_bytes) -> bytes
    Renders a JDDocument as a branded .docx file.

extract_jd_text(doc) -> str
    Flattens all prose fields for Bedrock guardrail OUTPUT check.
"""

import io
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt, RGBColor

from models.context import JDDocument


_DEFAULT_COLOR = "#1D3557"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse a hex color string (with or without #) to an (r, g, b) tuple."""
    hex_color = hex_color.lstrip("#").strip()
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return r, g, b
    except (ValueError, IndexError):
        return _hex_to_rgb(_DEFAULT_COLOR)


def _rgb_color(hex_color: str) -> RGBColor:
    r, g, b = _hex_to_rgb(hex_color)
    return RGBColor(r, g, b)


def _add_heading(doc: Document, text: str, brand_color: str, level: int = 1) -> None:
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        run.font.color.rgb = _rgb_color(brand_color)
        run.font.bold = True
        run.font.size = Pt(13 if level == 1 else 11)


def _add_bullet_list(doc: Document, items: list[str]) -> None:
    for item in items:
        if item:
            doc.add_paragraph(item, style="List Bullet")


def _add_accent_bar(doc: Document, brand_color: str) -> None:
    """Add a thin colored horizontal rule using a bottom border on an empty paragraph."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    r, g, b = _hex_to_rgb(brand_color)
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), f"{r:02X}{g:02X}{b:02X}")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _set_header_footer(doc: Document, role_title: str, brand_color: str) -> None:
    from datetime import date

    section = doc.sections[0]

    # Header
    header = section.header
    header.is_linked_to_previous = False
    htable = header.add_table(1, 2, width=doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin)
    htable.style = "Table Grid"
    htable.rows[0].cells[0].text = role_title
    htable.rows[0].cells[1].text = date.today().strftime("%d %b %Y")
    htable.rows[0].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for cell in htable.rows[0].cells:
        for para in cell.paragraphs:
            for run in para.runs:
                run.font.color.rgb = _rgb_color(brand_color)
                run.font.size = Pt(9)
    # Remove table borders
    for cell in htable.rows[0].cells:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcBorders = OxmlElement("w:tcBorders")
        for border_name in ("top", "left", "bottom", "right"):
            border = OxmlElement(f"w:{border_name}")
            border.set(qn("w:val"), "none")
            tcBorders.append(border)
        tcPr.append(tcBorders)

    # Footer
    footer = section.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    fp.text = "Built with JDQI  ·  Confidential"
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in fp.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)


def _add_logo(doc: Document, logo_bytes: Optional[bytes]) -> None:
    if logo_bytes:
        stream = io.BytesIO(logo_bytes)
        try:
            doc.add_picture(stream, width=Cm(3))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            return
        except Exception:
            pass
    # Placeholder box
    p = doc.add_paragraph("[Company Logo]")
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for run in p.runs:
        run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)
        run.font.size = Pt(9)


def build_docx(
    doc: JDDocument,
    brand_color: str,
    logo_bytes: Optional[bytes],
) -> bytes:
    """
    Render a JDDocument as a branded .docx file.

    Args:
        doc:         JDDocument dict from the Draft agent.
        brand_color: Hex color string (e.g. "#1D3557") for headings and accents.
        logo_bytes:  Raw image bytes (PNG/JPG) or None for placeholder.

    Returns:
        Raw .docx bytes suitable for st.download_button.
    """
    d = Document()

    # Set default font
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    style.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)

    _set_header_footer(d, doc.get("role_title", "Job Description"), brand_color)
    _add_logo(d, logo_bytes)
    _add_accent_bar(d, brand_color)

    role_title = doc.get("role_title", "Job Description")
    title_p = d.add_heading(role_title, level=0)
    for run in title_p.runs:
        run.font.color.rgb = _rgb_color(brand_color)
        run.font.size = Pt(20)

    _add_accent_bar(d, brand_color)

    sections = [
        ("About the Company", doc.get("about_company")),
        ("About the Role",    doc.get("about_role")),
    ]
    for heading, body in sections:
        if body:
            _add_heading(d, heading, brand_color)
            d.add_paragraph(body)

    list_sections = [
        ("Key Responsibilities",   doc.get("responsibilities") or []),
        ("What You'll Need",       doc.get("required_skills") or []),
        ("Nice to Have",           doc.get("preferred_skills") or []),
        ("What Success Looks Like", doc.get("success_criteria") or []),
    ]
    for heading, items in list_sections:
        if items:
            _add_heading(d, heading, brand_color)
            _add_bullet_list(d, items)

    optional_text_sections = [
        ("Reporting Structure", doc.get("reporting_structure")),
        ("Growth Path",         doc.get("growth_path")),
        ("Compensation & Benefits", doc.get("compensation")),
    ]
    for heading, body in optional_text_sections:
        if body:
            _add_heading(d, heading, brand_color)
            d.add_paragraph(body)

    eoe = doc.get("equal_opportunity")
    if eoe:
        _add_heading(d, "Equal Opportunity", brand_color)
        p = d.add_paragraph(eoe)
        for run in p.runs:
            run.font.italic = True

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def extract_jd_text(doc: JDDocument) -> str:
    """Flatten all prose fields of a JDDocument for the Bedrock OUTPUT guardrail check."""
    parts: list[str] = []
    for key in ("role_title", "about_company", "about_role", "reporting_structure",
                "growth_path", "compensation", "equal_opportunity"):
        val = doc.get(key)
        if val:
            parts.append(val)
    for key in ("responsibilities", "required_skills", "preferred_skills", "success_criteria"):
        items = doc.get(key) or []
        parts.extend(i for i in items if i)
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests — all should pass**

```bash
python -m pytest tests/test_jd_docx.py -v
```

Expected output:
```
tests/test_jd_docx.py::test_hex_to_rgb_navy PASSED
tests/test_jd_docx.py::test_hex_to_rgb_red PASSED
tests/test_jd_docx.py::test_hex_to_rgb_without_hash PASSED
tests/test_jd_docx.py::test_extract_jd_text_contains_key_fields PASSED
tests/test_jd_docx.py::test_extract_jd_text_excludes_none_fields PASSED
tests/test_jd_docx.py::test_build_docx_returns_bytes PASSED
tests/test_jd_docx.py::test_build_docx_with_invalid_color_falls_back PASSED
7 passed
```

- [ ] **Step 5: Commit**

```bash
git add agents/jd_docx.py tests/__init__.py tests/test_jd_docx.py
git commit -m "feat: add jd_docx builder with branded docx generation"
```

---

## Task 4: Build `agents/jd_builder_gather.py`

**Files:**
- Create: `agents/jd_builder_gather.py`

- [ ] **Step 1: Create `agents/jd_builder_gather.py`**

```python
"""
Phase 1: JD Builder Gather Agent (Sonnet).

gather_turn(messages, client) -> (reply: str, brief: JDQIBrief | None)
    Send one chat turn. Returns the agent's reply text and,
    when the agent calls signal_ready, the completed JDQIBrief dict.
    brief is None on normal conversational turns.
"""

import anthropic
from models.context import JDQIBrief


_SYSTEM = """You are a specialist JD consultant helping a user build a JDQI-compliant job description.
JDQI evaluates JDs on 6 dimensions with these scoring weights:
  Completeness 25% · Skill Specificity 20% · Role Coherence 20%
  Cognitive Load 15% · Inclusion Signals 10% · Compensation 10%

YOUR JOB:
Ask ONE question at a time. Adapt your follow-up depth to how expert the user's answers sound.
If a user gives rich, detailed answers, move on quickly. If answers are vague, ask one clarifying follow-up.

COVER THESE TOPICS IN ORDER:
1. Role basics: title, industry, seniority level, location, remote policy
2. Company context: 2-3 sentence company/team description
3. Key responsibilities: 4-6 bullet-level statements
4. Required skills: specific tools/technologies WITH version or proficiency level
   (e.g. "Python 3.11 expert" not just "Python")
5. Preferred/nice-to-have skills
6. Success criteria: what does good look like in the first 90 days?
7. Reporting structure: who does this role report to?
8. Growth path: what's the career trajectory from this role?
9. Compensation: salary band or range (if willing to share)
10. Inclusion signals: any specific D&I commitments or equal opportunity statement

SKIPPING RULES:
If the user wants to skip a topic, WARN them with the estimated JDQI score impact before moving on.
Example: "Skipping compensation will likely reduce your JDQI score by ~10 points since Compensation
is weighted at 10%. Want to proceed without it?"
Record every skipped dimension in skipped_dimensions.

WHEN READY:
Once you have covered all topics (or the user has consciously skipped them), call the signal_ready tool
with the complete JDQIBrief. Do NOT call it until you have at least: role_title, industry,
seniority_level, responsibilities (≥3), required_skills (≥2 with version/level).

TONE: Professional but conversational. One question per message. Never list all questions at once."""


_SIGNAL_READY_TOOL = {
    "name": "signal_ready",
    "description": (
        "Call this when you have gathered enough information to write a complete, "
        "JDQI-compliant JD. Do not call it until you have at minimum: role_title, "
        "industry, seniority_level, at least 3 responsibilities, and at least 2 "
        "required skills with version or proficiency level."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "role_title":          {"type": "string"},
            "industry":            {"type": "string"},
            "seniority_level":     {"type": "string", "enum": ["junior", "mid", "senior", "lead", "director"]},
            "location":            {"type": "string"},
            "remote_policy":       {"type": "string", "enum": ["on-site", "hybrid", "remote", "flexible"]},
            "company_description": {"type": "string"},
            "responsibilities":    {"type": "array", "items": {"type": "string"}},
            "required_skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":             {"type": "string"},
                        "version_or_level": {"type": "string"},
                    },
                    "required": ["name", "version_or_level"],
                },
            },
            "preferred_skills":    {"type": "array", "items": {"type": "string"}},
            "success_criteria":    {"type": "array", "items": {"type": "string"}},
            "reporting_structure": {"type": ["string", "null"]},
            "growth_path":         {"type": ["string", "null"]},
            "compensation":        {"type": ["string", "null"]},
            "inclusion_statement": {"type": ["string", "null"]},
            "skipped_dimensions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dimension":        {"type": "string"},
                        "jdqi_impact_note": {"type": "string"},
                    },
                    "required": ["dimension", "jdqi_impact_note"],
                },
            },
        },
        "required": [
            "role_title", "industry", "seniority_level",
            "responsibilities", "required_skills",
            "preferred_skills", "success_criteria", "skipped_dimensions",
        ],
    },
}

_GREETING = (
    "Hi! I'm your JD consultant. I'll guide you through building a "
    "JDQI-compliant job description — covering skills, responsibilities, "
    "compensation, and more. Let's start: **What role are you hiring for, "
    "and which industry is your company in?**"
)


def greeting() -> str:
    """Return the opening message to seed the chat."""
    return _GREETING


def gather_turn(
    messages: list[dict],
    client: anthropic.Anthropic,
) -> tuple[str, "JDQIBrief | None"]:
    """
    Send one conversational turn to the Gather agent.

    Args:
        messages: Full chat history in Anthropic message format
                  [{"role": "user"|"assistant", "content": "..."}]
        client:   Anthropic client instance.

    Returns:
        (reply, brief) where brief is a JDQIBrief dict if signal_ready was
        called this turn, or None for a normal conversational response.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=_SYSTEM,
        tools=[_SIGNAL_READY_TOOL],
        messages=messages,
    )

    if response.stop_reason == "tool_use":
        tool_block = next(b for b in response.content if b.type == "tool_use")
        brief: JDQIBrief = tool_block.input  # type: ignore[assignment]

        # Extract any text the agent wrote before calling the tool
        text_parts = [b.text for b in response.content if b.type == "text"]
        reply = (
            " ".join(text_parts).strip()
            or "I have everything I need to write your JD. Shall I generate it now?"
        )
        return reply, brief

    reply = response.content[0].text if response.content else ""
    return reply, None
```

- [ ] **Step 2: Verify import**

```bash
source .venv/bin/activate
python -c "from agents.jd_builder_gather import gather_turn, greeting; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agents/jd_builder_gather.py
git commit -m "feat: add JD Builder gather agent (Phase 1)"
```

---

## Task 5: Build `agents/jd_builder_draft.py`

**Files:**
- Create: `agents/jd_builder_draft.py`

- [ ] **Step 1: Create `agents/jd_builder_draft.py`**

```python
"""
Phase 2: JD Builder Draft Agent (Sonnet).

draft_jd(brief, client) -> JDDocument
    Receives a clean JDQIBrief and writes a complete,
    JDQI-optimised JD. Returns structured JDDocument dict.
"""

import json

import anthropic
from models.context import JDQIBrief, JDDocument


_SYSTEM = """You are an expert technical writer specialising in JDQI-compliant job descriptions.

You will receive a structured JDQIBrief. Write a complete, professional JD.

WRITING RULES:
- Use active voice and action verbs for responsibilities ("Lead", "Design", "Own", not "Responsible for")
- Include exact version/proficiency for every required skill (e.g. "Python 3.11 (expert level)")
- Keep Flesch-Kincaid reading grade ≤ 12 — clear, direct sentences
- Zero exclusionary phrases: no "rockstar", "ninja", "young and dynamic", "native speaker"
- If compensation is provided, include it exactly as given
- Equal opportunity statement: professional, warm, inclusive

Return ONLY valid JSON — no markdown fences, no commentary — matching this exact schema:
{
  "role_title": "<string>",
  "about_company": "<2-3 sentence company/team description>",
  "about_role": "<2-3 sentence role summary>",
  "responsibilities": ["<action-verb led statement>", ...],
  "required_skills": ["<skill name + version/level>", ...],
  "preferred_skills": ["<skill>", ...],
  "success_criteria": ["<measurable outcome>", ...],
  "reporting_structure": "<string or null>",
  "growth_path": "<string or null>",
  "compensation": "<string or null>",
  "equal_opportunity": "<string>"
}"""


def _extract_json(text: str) -> str:
    """Extract first { ... } block, tolerating trailing text or fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def draft_jd(brief: JDQIBrief, client: anthropic.Anthropic) -> JDDocument:
    """
    Generate a complete JDDocument from a JDQIBrief.

    Args:
        brief:  Structured brief produced by the Gather agent.
        client: Anthropic client instance.

    Returns:
        JDDocument dict with all prose sections filled.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Write a complete JDQI-compliant JD from this brief:\n\n"
                f"{json.dumps(brief, indent=2)}"
            ),
        }],
    )
    return json.loads(_extract_json(response.content[0].text))
```

- [ ] **Step 2: Verify import**

```bash
source .venv/bin/activate
python -c "from agents.jd_builder_draft import draft_jd; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agents/jd_builder_draft.py
git commit -m "feat: add JD Builder draft agent (Phase 2)"
```

---

## Task 6: Update `app.py` — Add tabs and Build JD tab UI

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add imports at top of app.py**

After the existing imports block, add:

```python
from agents.jd_builder_gather import gather_turn, greeting
from agents.jd_builder_draft import draft_jd
from agents.jd_docx import build_docx, extract_jd_text
```

- [ ] **Step 2: Add Build JD session state initialisation in `main()`**

In `main()`, after the existing session state init lines (`if "jdqi_context" not in ...`), add:

```python
    # ── Build JD tab session state ───────────────────────────────────
    if "builder_messages" not in st.session_state:
        st.session_state.builder_messages = []
    if "jdqi_brief" not in st.session_state:
        st.session_state.jdqi_brief = None
    if "jd_document" not in st.session_state:
        st.session_state.jd_document = None
    if "ready_to_generate" not in st.session_state:
        st.session_state.ready_to_generate = False
    if "brand_color" not in st.session_state:
        st.session_state.brand_color = "#1D3557"
    if "logo_bytes" not in st.session_state:
        st.session_state.logo_bytes = None
```

- [ ] **Step 3: Wrap existing main() body in tabs**

Replace everything after `client = _get_client()` in `main()` with:

```python
    tab1, tab2 = st.tabs(["🔍 Analyse JD", "📝 Build JD"])

    with tab1:
        # ── Input form ───────────────────────────────────────────────────
        with st.form("jd_form"):
            jd_text = st.text_area(
                "Paste your Job Description",
                height=320,
                placeholder="Paste the full JD text here…",
            )
            industry = st.selectbox("Industry", INDUSTRIES)
            submitted = st.form_submit_button(
                "Analyse JD ▶", type="primary", use_container_width=True
            )

        if submitted:
            if not jd_text.strip():
                st.warning("Please paste a job description before analysing.")
            else:
                st.session_state.jdqi_context = None
                st.session_state.accepted = []
                run_pipeline(jd_text, industry, client)

        # ── Render stored report (persists across Accept button clicks) ──
        if st.session_state.jdqi_context is not None:
            display_report(st.session_state.jdqi_context)

    with tab2:
        _build_jd_tab(client)
```

- [ ] **Step 4: Add `_build_jd_tab()` function**

Add this function above `main()` in `app.py`:

```python
_BRAND_PRESETS = {
    "Corporate Navy": "#1D3557",
    "JDQI Red":       "#C8102E",
    "Charcoal":       "#2D2D2D",
}


def _build_jd_tab(client: anthropic.Anthropic) -> None:
    """Render the Build JD chat tab."""

    # ── Brand settings ───────────────────────────────────────────────
    with st.expander("⚙️ Brand Settings", expanded=False):
        bcols = st.columns(len(_BRAND_PRESETS) + 1)
        for i, (name, hex_val) in enumerate(_BRAND_PRESETS.items()):
            if bcols[i].button(f"● {name}", key=f"preset_{name}"):
                st.session_state.brand_color = hex_val
                st.rerun()
        custom = bcols[-1].text_input(
            "Custom hex", value=st.session_state.brand_color, key="custom_color_input"
        )
        if custom != st.session_state.brand_color and custom.startswith("#") and len(custom) == 7:
            st.session_state.brand_color = custom

        logo_file = st.file_uploader("Company Logo (PNG/JPG, optional)", type=["png", "jpg", "jpeg"])
        if logo_file:
            st.session_state.logo_bytes = logo_file.read()

    st.caption(f"Brand color: `{st.session_state.brand_color}`")

    # ── Seed greeting on first load ──────────────────────────────────
    if not st.session_state.builder_messages:
        first = greeting()
        st.session_state.builder_messages.append({"role": "assistant", "content": first})

    # ── Chat display ─────────────────────────────────────────────────
    for msg in st.session_state.builder_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Download section (shown after successful generation) ─────────
    if st.session_state.jd_document is not None:
        st.divider()
        role = st.session_state.jd_document.get("role_title", "Job Description")
        st.success(f"📄 JD ready — **{role}**")
        docx_bytes = build_docx(
            st.session_state.jd_document,
            st.session_state.brand_color,
            st.session_state.logo_bytes,
        )
        col1, col2 = st.columns(2)
        col1.download_button(
            "⬇ Download .docx",
            data=docx_bytes,
            file_name=f"{role.replace(' ', '_')}_JD.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        if col2.button("🔄 Start over"):
            for key in ("builder_messages", "jdqi_brief", "jd_document",
                        "ready_to_generate", "logo_bytes"):
                st.session_state[key] = [] if key == "builder_messages" else None
            st.session_state.ready_to_generate = False
            st.rerun()
        return  # Don't show chat input once JD is done

    # ── Generate button (shown when gather agent signals ready) ──────
    if st.session_state.ready_to_generate and st.session_state.jdqi_brief:
        if st.button("✅ Generate JD now", type="primary"):
            with st.spinner("✍️ Drafting your JD…"):
                doc = draft_jd(st.session_state.jdqi_brief, client)

            # OUTPUT guardrail
            out_ph = st.empty()
            out_ph.info("🛡️ Bedrock Guardrail (OUTPUT) — Validating…")
            gr_out = check_guardrail(extract_jd_text(doc), "OUTPUT")
            if not gr_out.passed:
                out_ph.error(
                    f"🚫 Bedrock Guardrail (OUTPUT) — Blocked. {gr_out.blocked_reason}"
                )
                return
            out_ph.success("✅ Bedrock Guardrail (OUTPUT) — Passed")
            st.session_state.jd_document = doc
            st.rerun()

    # ── Chat input ───────────────────────────────────────────────────
    user_input = st.chat_input("Type your message…")
    if not user_input:
        return

    # INPUT guardrail
    gr_in = check_guardrail(user_input, "INPUT")
    if not gr_in.passed:
        with st.chat_message("assistant"):
            st.error(f"🚫 Bedrock Guardrail (INPUT) — Blocked. {gr_in.blocked_reason}")
        return

    # Add user message and display
    st.session_state.builder_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build Anthropic-format history.
    # Anthropic API requires history to start with a user message, so strip
    # any leading assistant messages (the display-only greeting seed).
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.builder_messages
    ]
    while history and history[0]["role"] == "assistant":
        history = history[1:]

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            reply, brief = gather_turn(history, client)
        st.markdown(reply)

    st.session_state.builder_messages.append({"role": "assistant", "content": reply})

    if brief is not None:
        st.session_state.jdqi_brief = brief
        st.session_state.ready_to_generate = True

    st.rerun()
```

- [ ] **Step 5: Verify the app starts without errors**

```bash
source .venv/bin/activate
python -c "import app; print('import OK')"
```

Expected: `import OK`

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: add Build JD tab — two-phase gather→draft chat UI with guardrails"
```

---

## Task 7: Smoke-test end-to-end in browser

- [ ] **Step 1: Start Streamlit**

```bash
source .venv/bin/activate
streamlit run app.py --server.port 8501 --server.headless true &
sleep 3 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8501
```

Expected: `200`

- [ ] **Step 2: Verify tab navigation**

Open http://localhost:8501. Confirm two tabs appear: `🔍 Analyse JD` and `📝 Build JD`. Click each — both should render without errors.

- [ ] **Step 3: Verify greeting appears**

Click `📝 Build JD` tab. Confirm the assistant greeting message appears automatically (not empty chat).

- [ ] **Step 4: Verify INPUT guardrail fires**

Type a benign message like "We need a senior Python engineer". Confirm:
- Bedrock Guardrail (INPUT) check runs (visible in network/logs or the message appears in chat)
- Assistant responds with a follow-up question

- [ ] **Step 5: Verify Analyse JD tab still works**

Switch to `🔍 Analyse JD` tab. Paste any JD text, run analysis. Confirm JDQI pipeline still runs cleanly — no regression.

- [ ] **Step 6: Commit final**

```bash
git add -A
git commit -m "feat: JD Builder module complete — chat gather→draft→docx with guardrails"
```

---

## Task 8: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

Expected:
```
tests/test_jd_docx.py::test_hex_to_rgb_navy PASSED
tests/test_jd_docx.py::test_hex_to_rgb_red PASSED
tests/test_jd_docx.py::test_hex_to_rgb_without_hash PASSED
tests/test_jd_docx.py::test_extract_jd_text_contains_key_fields PASSED
tests/test_jd_docx.py::test_extract_jd_text_excludes_none_fields PASSED
tests/test_jd_docx.py::test_build_docx_returns_bytes PASSED
tests/test_jd_docx.py::test_build_docx_with_invalid_color_falls_back PASSED
7 passed
```
