import json
from typing import Callable, Optional
from agents.llm import LLMClient
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
    client: LLMClient,
    on_advisor_called: Optional[Callable[[], None]] = None,
) -> AdvisorReport:
    """
    Synthesis executor (Sonnet). Reviews dimension results, then invokes the
    consult_advisor tool exactly once to call the Opus advisor.
    Returns the AdvisorReport written to shared context.
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
            model="gpt-4.1-mini",
            max_tokens=600,
            tools=[_ADVISOR_TOOL],
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_block = next(b for b in response.content if b.type == "tool_use")

            # Notify the UI that the advisor is now being called
            if on_advisor_called:
                on_advisor_called()

            # Call the Opus advisor with the full shared context
            advisor_report = run_advisor(context, client)

            # Return the tool result to complete the executor's turn
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
            break

    if advisor_report is None:
        # Fallback: executor didn't use the tool — invoke advisor directly
        if on_advisor_called:
            on_advisor_called()
        advisor_report = run_advisor(context, client)

    return advisor_report
