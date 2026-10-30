"""
Phase 1: JD Builder Gather Agent (Sonnet).

gather_turn(messages, client) -> (reply: str, brief: JDQIBrief | None)
    Send one chat turn. Returns the agent's reply text and,
    when the agent calls signal_ready, the completed JDQIBrief dict.
    brief is None on normal conversational turns.
"""

from agents.llm import LLMClient
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
Once you have covered all topics (or the user has consciously skipped them), IMMEDIATELY call the
signal_ready tool with the complete JDQIBrief. Do NOT write a message saying you are ready — just
call the tool. Do NOT call it until you have at least: role_title, industry, seniority_level,
responsibilities (>=3), required_skills (>=2 with version/level).

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
    client: LLMClient,
) -> tuple[str, "JDQIBrief | None"]:
    """
    Send one conversational turn to the Gather agent.

    Args:
        messages: Full chat history in chat message format
                  [{"role": "user"|"assistant", "content": "..."}]
                  Must start with a user message (strip leading assistant
                  messages before passing).
        client:   LLM client instance.

    Returns:
        (reply, brief) where brief is a JDQIBrief dict if signal_ready was
        called this turn, or None for a normal conversational response.
    """
    _READY_PHRASES = (
        "have everything i need", "have all the information", "have enough information",
        "i now have everything", "ready to write", "ready to generate",
        "let me compile", "let me draft", "let me put this together",
        "i have what i need",
    )

    # If the previous assistant turn already declared readiness without calling the tool,
    # force tool_choice="any" so the model MUST call signal_ready this turn.
    last_assistant_text = ""
    for m in reversed(messages):
        if m["role"] == "assistant":
            c = m["content"]
            last_assistant_text = c if isinstance(c, str) else ""
            break

    force_tool = any(p in last_assistant_text.lower() for p in _READY_PHRASES)
    tool_choice: dict = {"type": "any"} if force_tool else {"type": "auto"}

    response = client.messages.create(
        model="gpt-4.1-mini",
        max_tokens=1000,
        system=_SYSTEM,
        tools=[_SIGNAL_READY_TOOL],
        tool_choice=tool_choice,
        messages=messages,
    )

    if response.stop_reason == "tool_use":
        tool_block = next(b for b in response.content if b.type == "tool_use")
        brief: JDQIBrief = tool_block.input  # type: ignore[assignment]

        text_parts = [b.text for b in response.content if b.type == "text"]
        reply = (
            " ".join(text_parts).strip()
            or "I have everything I need to write your JD. Shall I generate it now?"
        )
        return reply, brief

    text_parts = [b.text for b in response.content if b.type == "text"]
    reply = " ".join(text_parts).strip()

    # Secondary safety net: if the current reply also declares readiness without the tool call,
    # fire a forced follow-up with tool_choice="any".
    # Use the plain text string (not response.content) to avoid including any ToolUseBlock
    # in the assistant message without a corresponding tool_result.
    if reply and any(p in reply.lower() for p in _READY_PHRASES):
        follow_up = list(messages) + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "Please call the signal_ready tool now with everything you've gathered."},
        ]
        forced = client.messages.create(
            model="gpt-4.1-mini",
            max_tokens=1000,
            system=_SYSTEM,
            tools=[_SIGNAL_READY_TOOL],
            tool_choice={"type": "any"},
            messages=follow_up,
        )
        if forced.stop_reason == "tool_use":
            tool_block = next(b for b in forced.content if b.type == "tool_use")
            brief = tool_block.input  # type: ignore[assignment]
            return reply, brief

    return reply, None
