import copy
import itertools

from restaurant_management_system.chatbot.llm import LLMReply, LLMUnavailableError, ToolCall

_ids = itertools.count(1)


def say(text: str | None) -> LLMReply:
    """A final answer from the model."""
    return LLMReply(content=text)


def call(name: str, **arguments) -> LLMReply:
    """The model asks to run one tool."""
    return LLMReply(content=None, tool_calls=[ToolCall(id=f"call_{next(_ids)}", name=name, arguments=arguments)])


def calls(*requests: tuple[str, dict]) -> LLMReply:
    """The model asks to run several tools at once."""
    return LLMReply(
        content=None,
        tool_calls=[ToolCall(id=f"call_{next(_ids)}", name=n, arguments=a) for n, a in requests],
    )


class ScriptedLLM:
    """Returns pre-written replies in order and records every request it receives."""

    def __init__(self, *replies: LLMReply | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []

    async def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        self.requests.append({"messages": copy.deepcopy(messages), "tools": tools})
        if not self.replies:
            raise AssertionError("The bot asked the model more times than the test scripted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def last_tool_result(self) -> dict:
        """The most recent tool message the bot sent back to the model, parsed."""
        import json

        for message in reversed(self.requests[-1]["messages"]):
            if message["role"] == "tool":
                return json.loads(message["content"])
        raise AssertionError("No tool result was sent to the model")


def unavailable() -> LLMUnavailableError:
    return LLMUnavailableError("model is down")


class RecordingProvider:
    """Stands in for the WhatsApp provider and remembers what was sent."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def send(self, phone: str, body: str) -> bool:
        if self.fail:
            raise RuntimeError("provider is down")
        self.sent.append((phone, body))
        return True
