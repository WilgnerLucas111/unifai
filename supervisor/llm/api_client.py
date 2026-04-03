from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class MessageDelta:
    content: str
    finish_reason: str | None
    usage: dict | None


class ProviderAdapter(ABC):
    @abstractmethod
    def stream_message(self, prompt: str) -> Iterator[MessageDelta]:
        raise NotImplementedError


class MockProvider(ProviderAdapter):
    def stream_message(self, prompt: str) -> Iterator[MessageDelta]:
        yield MessageDelta(content="Mock ", finish_reason=None, usage=None)
        yield MessageDelta(content="response", finish_reason=None, usage=None)
        yield MessageDelta(
            content=".",
            finish_reason="stop",
            usage={"total_tokens": max(1, len(prompt) // 4) + 8},
        )