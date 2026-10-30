import json
from agents.llm import LLMClient
from models.context import JDQIContext, AdvisorReport


_SYSTEM = """You are a senior talent acquisition expert with deep knowledge of hiring best practices
across High-tech Manufacturing, IT/SaaS/AI, and GCC (Global Capability Centre) industries.

You will receive a complete JD quality analysis. Produce a comprehensive JDQI report.

Return ONLY valid JSON — no markdown, no explanation — matching this exact schema:
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


def _extract_json(text: str) -> str:
    """Strip markdown fences then extract the first complete JSON object."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()

    # Find the outermost { ... } in case the model appended trailing text
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
                return text[start:i + 1]
    return text[start:]  # malformed — return what we have and let json.loads report it


def run_advisor(context: JDQIContext, client: LLMClient) -> AdvisorReport:
    """Opus advisor — reads full shared context, returns scored JDQI report."""
    response = client.messages.create(
        model="gpt-4.1-mini",
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
    return json.loads(_extract_json(response.content[0].text))
