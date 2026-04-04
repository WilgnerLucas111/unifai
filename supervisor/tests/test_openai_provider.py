from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.llm.api_client import OpenAICompatibleProvider


class FakeStreamResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __enter__(self) -> "FakeStreamResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def __iter__(self):
        return iter(self._lines)


class OpenAICompatibleProviderTests(unittest.TestCase):
    def test_stream_message_reads_content_and_usage_from_sse(self) -> None:
        provider = OpenAICompatibleProvider(
            base_url="http://localhost:1234/v1",
            api_key="test-key",
            model_name="llama-local",
        )
        response_lines = [
            b'data: {"choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}' + b"\n",
            b'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}' + b"\n",
            b"data: [DONE]\n",
        ]

        with patch("urllib.request.urlopen", return_value=FakeStreamResponse(response_lines)) as mocked_urlopen:
            deltas = list(provider.stream_message("Say hello"))

        self.assertEqual([d.content for d in deltas], ["Hel", "lo", ""])
        self.assertIsNone(deltas[0].usage)
        self.assertIsNone(deltas[1].usage)
        self.assertEqual(deltas[-1].finish_reason, "stop")
        self.assertEqual(deltas[-1].usage, {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5})

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.method, "POST")
        request_body = json.loads(request.data.decode("utf-8"))
        self.assertTrue(request_body["stream"])
        self.assertEqual(request_body["stream_options"], {"include_usage": True})
        self.assertEqual(request_body["model"], "llama-local")

    def test_stream_message_generates_usage_fallback_when_missing(self) -> None:
        provider = OpenAICompatibleProvider(
            base_url="http://localhost:1234/v1",
            api_key="test-key",
            model_name="llama-local",
        )
        response_lines = [
            b'data: {"choices":[{"delta":{"content":"Local"},"finish_reason":null}]}' + b"\n",
            b'data: {"choices":[{"delta":{"content":" model"},"finish_reason":"stop"}]}' + b"\n",
            b"data: [DONE]\n",
        ]

        with patch("urllib.request.urlopen", return_value=FakeStreamResponse(response_lines)):
            deltas = list(provider.stream_message("Use local model"))

        self.assertEqual([d.content for d in deltas], ["Local", " model", ""])
        self.assertEqual(deltas[-1].finish_reason, "stop")

        usage = deltas[-1].usage
        assert isinstance(usage, dict)
        self.assertIn("total_tokens", usage)
        self.assertIsInstance(usage["total_tokens"], int)
        self.assertGreater(usage["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
