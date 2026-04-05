from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from typing import Iterator
import urllib.request


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


class OpenAICompatibleProvider(ProviderAdapter):
    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        model_name: str = "local-model",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    def stream_message(self, prompt: str) -> Iterator[MessageDelta]:
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        request_data = json.dumps(payload).encode("utf-8")
        request_headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        if self.api_key:
            request_headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=request_data,
            headers=request_headers,
            method="POST",
        )

        usage_summary = None
        finish_reason = None
        completion_chars = 0

        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue

                data_payload = line[len("data:") :].strip()
                if not data_payload:
                    continue
                if data_payload == "[DONE]":
                    break

                try:
                    event = json.loads(data_payload)
                except json.JSONDecodeError:
                    continue

                usage = event.get("usage")
                normalized_usage = self._normalize_usage(usage)
                if normalized_usage is not None:
                    usage_summary = normalized_usage

                choices = event.get("choices")
                if not isinstance(choices, list):
                    continue

                for choice in choices:
                    if not isinstance(choice, dict):
                        continue

                    delta = choice.get("delta")
                    if isinstance(delta, dict):
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            completion_chars += len(content)
                            yield MessageDelta(content=content, finish_reason=None, usage=None)

                    candidate_finish_reason = choice.get("finish_reason")
                    if isinstance(candidate_finish_reason, str):
                        finish_reason = candidate_finish_reason

        final_usage = usage_summary
        if final_usage is None:
            final_usage = self._estimate_usage(prompt, completion_chars)

        yield MessageDelta(content="", finish_reason=finish_reason or "stop", usage=final_usage)

    def _normalize_usage(self, usage: object) -> dict | None:
        if not isinstance(usage, dict):
            return None

        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")

        normalized = {}
        if isinstance(prompt_tokens, int):
            normalized["prompt_tokens"] = prompt_tokens
        if isinstance(completion_tokens, int):
            normalized["completion_tokens"] = completion_tokens
        if isinstance(total_tokens, int):
            normalized["total_tokens"] = total_tokens

        if "total_tokens" not in normalized and isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
            normalized["total_tokens"] = prompt_tokens + completion_tokens

        if "total_tokens" not in normalized:
            return None

        return normalized

    def _estimate_usage(self, prompt: str, completion_chars: int) -> dict:
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, completion_chars // 4)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }