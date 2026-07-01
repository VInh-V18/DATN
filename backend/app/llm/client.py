"""LLM Client - bộ não suy luận của agent (mục 2.2, 2.3).

Cung cấp một giao diện thống nhất cho tool-calling, hỗ trợ cả Ollama (Qwen chạy
nội bộ) và Claude API, đúng theo lựa chọn linh hoạt local/cloud ở Chương 4.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.tools.specs import ToolSpec


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None


class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None) -> ChatResult: ...

    @abstractmethod
    def tool_result_message(self, tool_call: ToolCall, output: Any) -> dict[str, Any]: ...


class OllamaLLMClient(LLMClient):
    def __init__(self, host: str | None = None, model: str | None = None) -> None:
        import ollama

        settings = get_settings()
        self._client = ollama.Client(host=host or settings.ollama_host)
        self.model = model or settings.ollama_model

    @staticmethod
    def _to_ollama_tools(tools: list[ToolSpec]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def chat(self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None) -> ChatResult:
        response = self._client.chat(
            model=self.model,
            messages=messages,
            tools=self._to_ollama_tools(tools) if tools else None,
        )
        message = response["message"]
        tool_calls = []
        for i, call in enumerate(message.get("tool_calls") or []):
            fn = call["function"]
            args = fn["arguments"]
            if isinstance(args, str):
                args = json.loads(args or "{}")
            tool_calls.append(ToolCall(id=call.get("id", str(i)), name=fn["name"], arguments=args))
        return ChatResult(content=message.get("content", ""), tool_calls=tool_calls, raw=response)

    def tool_result_message(self, tool_call: ToolCall, output: Any) -> dict[str, Any]:
        return {"role": "tool", "content": json.dumps(output, ensure_ascii=False, default=str)}


class AnthropicLLMClient(LLMClient):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        import anthropic

        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=api_key or settings.anthropic_api_key)
        self.model = model or settings.anthropic_model

    @staticmethod
    def _to_anthropic_tools(tools: list[ToolSpec]) -> list[dict]:
        return [
            {"name": tool.name, "description": tool.description, "input_schema": tool.parameters} for tool in tools
        ]

    def chat(self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None) -> ChatResult:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        non_system = [m for m in messages if m["role"] != "system"]
        response = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system or None,
            messages=non_system,
            tools=self._to_anthropic_tools(tools) if tools else None,
        )
        content_text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
        return ChatResult(content=content_text, tool_calls=tool_calls, raw=response)

    def tool_result_message(self, tool_call: ToolCall, output: Any) -> dict[str, Any]:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(output, ensure_ascii=False, default=str),
                }
            ],
        }


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicLLMClient()
    return OllamaLLMClient()
