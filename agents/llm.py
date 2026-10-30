"""
Azure OpenAI adapter exposing the `client.messages.create(...)` shape the agents use.

Agents pass Anthropic-style arguments (system, messages, tools, tool_choice) and read
Anthropic-style responses (response.content blocks, response.stop_reason). This module
translates both directions so only the client construction differs.

Config (.env):
    AZURE_OPENAI_API_KEY      key for the Azure OpenAI resource
    AZURE_OPENAI_ENDPOINT     https://<resource>.openai.azure.com/
    AZURE_OPENAI_DEPLOYMENT   deployment name of your gpt-4.1-mini deployment
    AZURE_OPENAI_API_VERSION  optional, default 2024-12-01-preview
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from openai import AzureOpenAI


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class LLMResponse:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"


def _get(block: Any, key: str) -> Any:
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)


def _convert_messages(system: str | None, messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})

    for m in messages:
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        if role == "assistant":
            text = "".join(_get(b, "text") or "" for b in content if _get(b, "type") == "text")
            tool_calls = [
                {
                    "id": _get(b, "id"),
                    "type": "function",
                    "function": {"name": _get(b, "name"), "arguments": json.dumps(_get(b, "input"))},
                }
                for b in content if _get(b, "type") == "tool_use"
            ]
            msg: dict = {"role": "assistant", "content": text or None}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
        else:
            for b in content:
                if _get(b, "type") == "tool_result":
                    out.append({
                        "role": "tool",
                        "tool_call_id": _get(b, "tool_use_id"),
                        "content": str(_get(b, "content")),
                    })
                elif _get(b, "type") == "text":
                    out.append({"role": "user", "content": _get(b, "text")})
    return out


def _convert_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


class _Messages:
    def __init__(self, client: AzureOpenAI, deployment: str):
        self._client = client
        self._deployment = deployment

    def create(
        self,
        *,
        model: str | None = None,  # accepted for call-site compatibility; deployment is used
        max_tokens: int,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self._deployment,  # Azure routes by deployment name
            "max_tokens": max_tokens,
            "messages": _convert_messages(system, messages),
        }
        if tools:
            kwargs["tools"] = _convert_tools(tools)
            kind = (tool_choice or {}).get("type", "auto")
            kwargs["tool_choice"] = "required" if kind == "any" else "auto"

        choice = self._client.chat.completions.create(**kwargs).choices[0]
        msg = choice.message

        content: list = []
        if msg.content:
            content.append(TextBlock(text=msg.content))
        for tc in msg.tool_calls or []:
            content.append(ToolUseBlock(
                id=tc.id,
                name=tc.function.name,
                input=json.loads(tc.function.arguments or "{}"),
            ))

        stop = "tool_use" if msg.tool_calls else "end_turn"
        return LLMResponse(content=content, stop_reason=stop)


class LLMClient:
    """Drop-in replacement for anthropic.Anthropic for the .messages.create surface."""

    def __init__(self, api_key: str, endpoint: str, deployment: str, api_version: str):
        azure = AzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)
        self.messages = _Messages(azure, deployment)


def make_client() -> LLMClient:
    """Build a client from env vars. Raises KeyError naming the first missing variable."""
    return LLMClient(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )
