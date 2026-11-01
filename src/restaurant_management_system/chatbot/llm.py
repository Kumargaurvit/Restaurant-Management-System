import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

from openai import AsyncOpenAI

from restaurant_management_system.config import get_settings


class LLMUnavailableError(RuntimeError):
    """The language model cannot be used (not configured, or the call failed)."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply: ...


class OpenAIClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                temperature=0.3,
            )
        except Exception as error:  # network, auth, rate limit: the guest still gets an answer
            raise LLMUnavailableError(str(error)) from error

        message = response.choices[0].message
        calls = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
        return LLMReply(content=message.content, tool_calls=calls)


@lru_cache
def get_llm_client() -> LLMClient:
    settings = get_settings()
    if not settings.openai_api_key:
        raise LLMUnavailableError("OPENAI_API_KEY is not set")
    return OpenAIClient(settings.openai_api_key, settings.openai_model)


def get_optional_llm() -> LLMClient | None:
    """FastAPI dependency: the client, or None when no API key is configured."""
    try:
        return get_llm_client()
    except LLMUnavailableError:
        return None
