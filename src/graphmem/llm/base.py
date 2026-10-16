
"""Shared models and interface for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class Message:
    """A single message exchanged with an LLM."""

    role: str
    content: str


@dataclass
class LLMResponse:
    """Normalized response returned by an LLM provider."""

    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
    )
    latency_ms: float = 0.0


class LLMProvider(ABC):
    """Provider-independent interface for text generation."""

    @abstractmethod
    def generate(
        self,
        messages: Sequence[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Generate a response from messages, optionally using tools."""
        raise NotImplementedError
