import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
from agents.llm import LLMClient
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


def _call(system: str, user: str, client: LLMClient) -> dict:
    response = client.messages.create(
        model="gpt-4.1-mini",
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return json.loads(_strip_fences(response.content[0].text))


def _analyze_completeness(parsed_jd: ParsedJD, client: LLMClient) -> CompletenessResult:
    system = """Evaluate JD completeness. Score 0–100 based on how many of these elements are present:
required_skills, preferred_skills, responsibilities, success_criteria, reporting_structure, growth_path.
Return ONLY valid JSON (no markdown):
{"score": <int>, "findings": ["<observation>"], "missing": ["<element name>"]}"""
    return _call(system, f"Parsed JD:\n{json.dumps(parsed_jd, indent=2)}", client)


def _analyze_skill_specificity(parsed_jd: ParsedJD, client: LLMClient) -> SkillSpecificityResult:
    system = """Evaluate skill specificity in the JD. High score (100) = all tools/skills have versions or
proficiency levels. Low score = vague terms like "experience with databases" with no specifics.
Return ONLY valid JSON (no markdown):
{"score": <int>, "findings": ["<observation>"], "vague_skills": ["<skill>"]}"""
    return _call(system, f"Parsed JD:\n{json.dumps(parsed_jd, indent=2)}", client)


def _analyze_cognitive_load(jd_text: str, client: LLMClient) -> CognitiveLoadResult:
    system = """Evaluate cognitive load of this JD text. Measure:
- word_count: exact word count
- grade_level: Flesch-Kincaid reading grade estimate (float)
- score: 0–100 readability score (100 = very readable, 0 = overwhelming jargon)
- findings: specific observations about length, jargon, or structure.
Return ONLY valid JSON (no markdown):
{"score": <int>, "findings": ["<observation>"], "word_count": <int>, "grade_level": <float>}"""
    return _call(system, f"JD text:\n{jd_text}", client)


def _analyze_inclusion_signals(jd_text: str, client: LLMClient) -> InclusionResult:
    system = """Scan this JD for exclusionary language that may deter qualified candidates.
Examples: "rockstar", "ninja", "young and dynamic", "native speaker", gendered pronouns used exclusively.
Score 0–100 (100 = fully inclusive, no flags).
Return ONLY valid JSON (no markdown):
{"score": <int>, "findings": ["<observation>"], "flags": ["<exact phrase flagged>"]}"""
    return _call(system, f"JD text:\n{jd_text}", client)


def _analyze_compensation(parsed_jd: ParsedJD, jd_text: str, client: LLMClient) -> CompensationResult:
    system = """Check whether this JD includes a compensation/salary band.
band_present = true only if a specific range or figure is stated.
Score: 100 if clear range stated, 50 if vague mention of "competitive salary", 0 if absent.
Return ONLY valid JSON (no markdown):
{"score": <int>, "findings": ["<observation>"], "band_present": <bool>}"""
    user = f"Parsed JD:\n{json.dumps(parsed_jd, indent=2)}\n\nFull text:\n{jd_text}"
    return _call(system, user, client)


def _analyze_role_coherence(parsed_jd: ParsedJD, client: LLMClient) -> RoleCoherenceResult:
    system = """Evaluate whether the JD requirements and responsibilities are coherent with the stated seniority level.
Flag issues like: "3 years experience" for a senior role, "5+ years required" for a mid role,
responsibilities that belong to a higher/lower level, or skill lists that mix entry-level and expert demands.
Score 0–100 (100 = fully coherent).
Return ONLY valid JSON (no markdown):
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

_ERROR_DEFAULTS: dict[str, dict] = {
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
    client: LLMClient,
    progress_callback: Optional[Callable[[str, dict], None]] = None,
) -> DimensionResults:
    """Run all 6 specialist agents in parallel via ThreadPoolExecutor.
    Calls progress_callback(key, result) from the main thread as each completes."""
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
