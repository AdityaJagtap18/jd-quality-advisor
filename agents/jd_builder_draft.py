"""
Phase 2: JD Builder Draft Agent (Sonnet).

draft_jd(brief, client) -> JDDocument
    Receives a clean JDQIBrief and writes a complete,
    JDQI-optimised JD. Returns structured JDDocument dict.
"""

import json

from agents.llm import LLMClient
from models.context import JDQIBrief, JDDocument


_SYSTEM = """You are an expert technical writer specialising in JDQI-compliant job descriptions.

You will receive a structured JDQIBrief. Write a complete, professional JD.

WRITING RULES:
- Use active voice and action verbs for responsibilities ("Lead", "Design", "Own", not "Responsible for")
- Include exact version/proficiency for every required skill (e.g. "Python 3.11 (expert level)")
- Keep Flesch-Kincaid reading grade <= 12 — clear, direct sentences
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


def draft_jd(
    brief: JDQIBrief,
    client: LLMClient,
    guardrail_feedback: str | None = None,
) -> JDDocument:
    """
    Generate a complete JDDocument from a JDQIBrief.

    Args:
        brief:               Structured brief produced by the Gather agent.
        client:              LLM client instance.
        guardrail_feedback:  If a previous attempt was blocked, pass the
                             blocked_reason string here so the agent can
                             course-correct before the next guardrail check.

    Returns:
        JDDocument dict with all prose sections filled.
    """
    user_content = (
        f"Write a complete JDQI-compliant JD from this brief:\n\n"
        f"{json.dumps(brief, indent=2)}"
    )

    if guardrail_feedback:
        user_content += (
            f"\n\n---\nGUARDRAIL CORRECTIONS REQUIRED:\n"
            f"Your previous draft was blocked for the following reasons:\n"
            f"{guardrail_feedback}\n\n"
            f"Rewrite the ENTIRE JD avoiding ALL of these issues:\n"
            f"- Remove or replace every blocked word/phrase with a professional alternative\n"
            f"- Do not mention protected characteristics (ethnicity, disability, sexual orientation,\n"
            f"  religion, age, gender, race, etc.) anywhere in the document\n"
            f"- For the equal_opportunity field use only general language such as:\n"
            f"  \"We welcome applications from all qualified candidates and are committed to\n"
            f"   building an inclusive team.\"\n"
            f"- Ensure no sentence could be read as a discriminatory hiring criterion"
        )

    response = client.messages.create(
        model="gpt-4.1-mini",
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    return json.loads(_extract_json(response.content[0].text))
