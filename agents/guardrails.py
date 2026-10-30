"""
Azure AI Content Safety guardrail.

Replaces the former AWS Bedrock `apply_guardrail` gate. Used as an input gate
(JD text / chat message) and output gate (advisor report / drafted JD).

Checks:
  1. Harm categories (Hate, SelfHarm, Sexual, Violence) via Content Safety
     `text:analyze` — blocks at or above CONTENT_SAFETY_MIN_SEVERITY (default 4).
  2. Prompt Shields (`text:shieldPrompt`) on INPUT — blocks jailbreak/injection attempts.
  3. Discriminatory-hiring policy check on OUTPUT — an LLM classifier
     (replaces the Bedrock `Discriminatory_Hiring_Criteria` topic policy).

Any failure to run a check (missing config, HTTP error) blocks the pipeline.

Config (.env):
    AZURE_CONTENT_SAFETY_ENDPOINT   https://<resource>.cognitiveservices.azure.com/
    AZURE_CONTENT_SAFETY_KEY
    CONTENT_SAFETY_MIN_SEVERITY     optional: 2 (strict) | 4 (default) | 6 (lenient)
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

import httpx

from agents.llm import LLMClient, make_client

_API_VERSION = "2024-09-01"
_CHUNK = 9_000            # API limit is 10k chars per request
_MAX_CHARS = 50_000
_CATEGORIES = ["Hate", "SelfHarm", "Sexual", "Violence"]

_POLICY_SYSTEM = (
    "You are a hiring-compliance reviewer. Decide whether the text contains "
    "Discriminatory_Hiring_Criteria: age requirements or preferences, gender/race/religion/"
    "nationality/caste preferences, physical-appearance requirements, marital or family status "
    "requirements, or other protected-characteristic criteria used to include or exclude "
    "candidates. A proper equal-opportunity statement that welcomes all candidates is NOT a "
    "violation. Return ONLY JSON: {\"violation\": true|false}"
)


@dataclass
class GuardrailResult:
    passed: bool
    action: str           # "NONE", "GUARDRAIL_INTERVENED" or "AZURE_ERROR"
    blocked_reason: Optional[str] = None


def _config() -> tuple[str, str] | None:
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "").strip().rstrip("/")
    key = os.getenv("AZURE_CONTENT_SAFETY_KEY", "").strip()
    return (endpoint, key) if endpoint and key else None


def _min_severity() -> int:
    try:
        return int(os.getenv("CONTENT_SAFETY_MIN_SEVERITY", "4"))
    except ValueError:
        return 4


def _post(endpoint: str, key: str, op: str, body: dict) -> dict:
    resp = httpx.post(
        f"{endpoint}/contentsafety/{op}",
        params={"api-version": _API_VERSION},
        headers={"Ocp-Apim-Subscription-Key": key},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _chunks(text: str) -> list[str]:
    text = text[:_MAX_CHARS]
    return [text[i:i + _CHUNK] for i in range(0, len(text), _CHUNK)]


def _harm_reasons(endpoint: str, key: str, chunk: str) -> list[str]:
    data = _post(endpoint, key, "text:analyze", {
        "text": chunk,
        "categories": _CATEGORIES,
        "outputType": "FourSeverityLevels",
    })
    threshold = _min_severity()
    return [
        f"Content filter: {c['category']} [severity={c['severity']}]"
        for c in data.get("categoriesAnalysis", [])
        if c.get("severity", 0) >= threshold
    ]


def _shield_reasons(endpoint: str, key: str, chunk: str) -> list[str]:
    data = _post(endpoint, key, "text:shieldPrompt", {"userPrompt": chunk, "documents": []})
    if data.get("userPromptAnalysis", {}).get("attackDetected"):
        return ["Prompt Shield: prompt injection / jailbreak attempt detected"]
    return []


def _policy_reasons(text: str) -> list[str]:
    response = make_client().messages.create(
        max_tokens=50,
        system=_POLICY_SYSTEM,
        messages=[{"role": "user", "content": text[:_MAX_CHARS]}],
    )
    raw = response.content[0].text if response.content else ""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("policy check returned no JSON")
    if json.loads(raw[start:end + 1]).get("violation"):
        return ["Topic blocked: Discriminatory_Hiring_Criteria (DENY)"]
    return []


def check_guardrail(text: str, source: str) -> GuardrailResult:
    """
    Apply the Azure content guardrail to `text`.

    Args:
        text:   The text to evaluate.
        source: "INPUT" or "OUTPUT"

    Returns:
        GuardrailResult with passed=True if nothing was flagged, passed=False
        (with blocked_reason) if blocked or if a check could not be run.
    """
    if not text or not text.strip():
        return GuardrailResult(passed=True, action="NONE")

    cfg = _config()
    if cfg is None:
        return GuardrailResult(
            passed=False,
            action="AZURE_ERROR",
            blocked_reason="Azure Content Safety not configured — set AZURE_CONTENT_SAFETY_ENDPOINT and AZURE_CONTENT_SAFETY_KEY in .env",
        )
    endpoint, key = cfg

    reasons: list[str] = []
    try:
        for chunk in _chunks(text):
            reasons += _harm_reasons(endpoint, key, chunk)
            if source == "INPUT":
                reasons += _shield_reasons(endpoint, key, chunk)
        if source == "OUTPUT":
            reasons += _policy_reasons(text)
    except Exception as exc:  # hard gate: any failure blocks the pipeline
        return GuardrailResult(passed=False, action="AZURE_ERROR", blocked_reason=str(exc))

    if reasons:
        return GuardrailResult(
            passed=False,
            action="GUARDRAIL_INTERVENED",
            blocked_reason="; ".join(dict.fromkeys(reasons)),
        )
    return GuardrailResult(passed=True, action="NONE")


def extract_report_text(report: dict) -> str:
    """Flatten an AdvisorReport dict to a single string for output guardrail check."""
    parts: list[str] = []

    if bc := report.get("benchmark_comparison"):
        parts.append(bc)

    for item in report.get("dimension_breakdown", []):
        if n := item.get("narrative"):
            parts.append(n)

    for item in report.get("suggested_additions", []):
        if s := item.get("suggestion"):
            parts.append(s)
        if imp := item.get("impact"):
            parts.append(imp)

    return "\n\n".join(parts)


def scan_jd_for_violations(
    jd_text: str,
    blocked_reason: str,
    client: LLMClient,
) -> list[str]:
    """Ask the LLM to find verbatim phrases in jd_text that match the block reason.

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
            model="gpt-4.1-mini",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        parsed = json.loads(raw[start : end + 1])
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, str)]
    except Exception:
        return []
