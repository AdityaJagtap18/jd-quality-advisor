# JD Quality Intelligence (JDQI) — Advisor Strategy Demo
**Date:** 2026-04-10  
**Status:** Approved

## Problem

AI hiring pipelines amplify whatever signal the JD carries — good or bad. A weak JD means weak resume scoring, miscalibrated assessments, narrowed candidate pools, and post-hire performance mismatches. This is "garbage in, garbage out at scale."

Three target segments with distinct failure modes:
- **High-tech Manufacturing** — JDs under-specified; HR copies old templates, missing tool chains (Cadence vs Altium), thermal analysis, SPICE proficiency
- **IT/SaaS/AI** — Skill inflation; "5 years React + 3 years K8s + ML" for a mid role causes candidate self-selection and post-hire mismatch
- **GCCs** — JDs copied from US/EU parent without India market calibration; wrong experience bands, wrong seniority framing

## Solution

A **JD Quality Intelligence (JDQI)** gate between JD upload and pipeline activation, built as a Streamlit demo using the Claude Advisor Strategy: Sonnet specialist agents run the analysis pipeline; Opus acts as the on-demand advisor for benchmark comparison and final recommendations.

## Architecture

### Pattern: Multi-Agent Pipeline + Advisor Gate

```
JD Text + Industry
        │
        ▼
Agent 1: JD Parser (Sonnet)
  Extracts: role, seniority, required/preferred skills,
  responsibilities, reporting structure, growth path,
  success criteria, compensation
        │ → writes parsed_jd to shared context
        ▼
Agents 2–7: Specialist Analyzers (Sonnet, parallel)
  2. Completeness      — required vs preferred, success criteria, reporting structure, growth path
  3. Skill Specificity — tools/versions/proficiency levels explicit vs vague
  4. Cognitive Load    — word count, reading grade level, jargon density
  5. Inclusion Signals — exclusionary language flags
  6. Compensation      — salary band present/absent
  7. Role Coherence    — seniority alignment, "5-year junior" detection
        │ → each writes dimension_results.{dimension} to shared context
        ▼
Agent 8: Synthesis Executor (Sonnet)
  Aggregates all 6 dimension results into structured brief
  Has ONE tool: consult_advisor(brief, full_context)
        │ → tool call to Advisor
        ▼
Agent 9: Advisor (Opus) — ON DEMAND
  Reads full shared context
  Returns:
    • Composite JDQI score (0–100)
    • Benchmark comparison narrative (industry-specific)
    • Per-dimension score + narrative
    • Suggested Additions (section, suggestion, impact)
        │ → writes advisor_report to shared context
        ▼
    JDQI Report UI
```

Agents 2–7 run concurrently via `asyncio.gather()` after Agent 1 completes. The advisor is invoked exactly once, on-demand, via a tool call from the synthesis executor — faithful to the advisor strategy diagram.

## Shared Context Schema

```python
# models/context.py

class ParsedJD(TypedDict):
    role_title: str
    seniority_level: str          # junior | mid | senior | lead
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    reporting_structure: str | None
    growth_path: str | None
    success_criteria: str | None
    compensation: str | None

class DimensionResult(TypedDict):
    score: int                    # 0–100
    findings: list[str]

class CompletenessResult(DimensionResult):
    missing: list[str]

class SkillSpecificityResult(DimensionResult):
    vague_skills: list[str]

class CognitiveLoadResult(DimensionResult):
    word_count: int
    grade_level: float

class InclusionResult(DimensionResult):
    flags: list[str]

class CompensationResult(DimensionResult):
    band_present: bool

class RoleCoherenceResult(DimensionResult):
    mismatches: list[str]

class DimensionResults(TypedDict):
    completeness: CompletenessResult
    skill_specificity: SkillSpecificityResult
    cognitive_load: CognitiveLoadResult
    inclusion_signals: InclusionResult
    compensation: CompensationResult
    role_coherence: RoleCoherenceResult

class SuggestedAddition(TypedDict):
    section: str                  # e.g. "Required Skills"
    suggestion: str               # e.g. "Add: Cadence Virtuoso, SPICE simulation"
    impact: str                   # e.g. "Prevents weak resume scoring for circuit design roles"

class DimensionBreakdown(TypedDict):
    dimension: str
    score: int
    narrative: str

class AdvisorReport(TypedDict):
    jdqi_score: int
    benchmark_comparison: str
    dimension_breakdown: list[DimensionBreakdown]
    suggested_additions: list[SuggestedAddition]

class JDQIContext(TypedDict):
    jd_text: str
    industry: str
    parsed_jd: ParsedJD
    dimension_results: DimensionResults
    advisor_report: AdvisorReport
```

## Agent Contracts

| Agent | Model | Reads from context | Writes to context |
|---|---|---|---|
| JD Parser | claude-sonnet-4-6 | `jd_text`, `industry` | `parsed_jd` |
| Completeness | claude-sonnet-4-6 | `parsed_jd` | `dimension_results.completeness` |
| Skill Specificity | claude-sonnet-4-6 | `parsed_jd` | `dimension_results.skill_specificity` |
| Cognitive Load | claude-sonnet-4-6 | `jd_text` | `dimension_results.cognitive_load` |
| Inclusion Signals | claude-sonnet-4-6 | `jd_text` | `dimension_results.inclusion_signals` |
| Compensation | claude-sonnet-4-6 | `parsed_jd`, `jd_text` | `dimension_results.compensation` |
| Role Coherence | claude-sonnet-4-6 | `parsed_jd` | `dimension_results.role_coherence` |
| Synthesis Executor | claude-sonnet-4-6 | full context | calls `consult_advisor()` tool |
| Advisor | claude-opus-4-6 | full context (via tool arg) | `advisor_report` |

Each specialist agent is a single `messages.create()` call with a structured JSON output instruction. No tool loops needed for specialists. The synthesis executor runs an agentic loop (processes the `consult_advisor` tool call result and writes back).

## File Structure

```
agent-orchestration/
├── app.py                     # Streamlit entry point + UI logic
├── agents/
│   ├── __init__.py
│   ├── parser.py              # Agent 1: JD Parser
│   ├── specialists.py         # Agents 2–7: async specialist analyzers
│   ├── synthesizer.py         # Agent 8: Synthesis executor + consult_advisor tool
│   └── advisor.py             # Agent 9: Opus advisor
├── models/
│   ├── __init__.py
│   └── context.py             # TypedDict schemas (above)
├── requirements.txt
└── .env.example
```

## Streamlit UI — 4 Screens

### Screen 1: Input
- Text area: "Paste your Job Description"
- Dropdown: Industry (High-tech Manufacturing / IT-SaaS-AI / GCC / Other)
- "Analyse JD" button

### Screen 2: Pipeline Progress (live during run)
Live status indicators per agent, updated as each completes.
Advisor step rendered in amber/orange to distinguish it as the on-demand call.

```
✅  JD Parser                     Done
⏳  Running 6 specialist agents...
    ├── Completeness              ✅
    ├── Skill Specificity         ⏳
    ├── Cognitive Load            ✅
    ├── Inclusion Signals         ✅
    ├── Compensation              ✅
    └── Role Coherence            ✅
⬜  Synthesis Executor
🔶  Advisor (Opus) — On-demand
```

### Screen 3: JDQI Report
- Composite score badge (0–100 with Fair/Good/Excellent label)
- Dimension scorecard: progress bar + score + one-line narrative for each of 6 dimensions
- Benchmark comparison narrative (collapsible)

### Screen 4: Suggested Additions
- Table: Section | Suggestion | Impact | [Accept] [Skip]
- Accepted suggestions accumulate in a "Revised JD Additions" copyable text box

## Error Handling

- JD Parser failure (unparseable JD): surface error on Screen 2, abort pipeline
- Specialist agent failure: mark dimension as "Unable to analyse", score = null, continue pipeline
- Advisor failure: surface error with retry button; do not show partial report
- API key missing: clear error on startup before any UI renders

## Dependencies

```
anthropic>=0.49.0
streamlit>=1.43.0
python-dotenv>=1.0.0
```

Python 3.11+. No database. No external APIs beyond Anthropic.

## Out of Scope (v1)

- Saving/exporting the JDQI report as PDF
- Storing JD history or comparison across submissions
- Streaming token output from agents
- Auth / multi-user sessions
