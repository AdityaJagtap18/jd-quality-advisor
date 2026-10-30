import json
from agents.llm import LLMClient
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
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    return text


def run_parser(jd_text: str, industry: str, client: LLMClient) -> ParsedJD:
    response = client.messages.create(
        model="gpt-4.1-mini",
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Industry: {industry}\n\nJob Description:\n{jd_text}"
        }]
    )
    return json.loads(_strip_fences(response.content[0].text))
