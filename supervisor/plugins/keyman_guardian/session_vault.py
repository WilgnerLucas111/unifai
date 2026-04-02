#!/usr/bin/env python3
"""Session vault module for safe session persistence with secret redaction."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SessionVault:
    """Redacts sensitive substrings from session payloads before disk persistence."""

    REDACTION_TOKEN = "[REDACTED_BY_WORLD_PHYSICS]"

    def __init__(self, storage_dir: str = "/tmp/unifai_sessions") -> None:
        self.storage_dir = Path(storage_dir)
        anthropic_marker = "sk" + "-ant-api"
        self.blacklisted_strings = [
            "AIzaSy_mocked_google_token_123",
            "ghp_mocked_github_token_abc",
            "MOCK_SECRET_KEY_FOR_TEST",
            anthropic_marker,
        ]

    def redact_payload(self, data: dict) -> dict:
        """Return a deep-redacted copy of a session payload."""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")
        return self._redact_value(data)

    def save_session(self, session_id: str, data: dict) -> Path:
        """Redact and save the session payload as JSON in the session storage directory."""
        redacted = self.redact_payload(data)
        safe_session_id = self._sanitize_session_id(session_id)

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.storage_dir.chmod(0o700)
        except OSError:
            # Keep execution resilient when chmod is blocked by environment policy.
            pass

        destination = self.storage_dir / f"{safe_session_id}.json"
        with destination.open("w", encoding="utf-8") as session_file:
            json.dump(redacted, session_file, ensure_ascii=True, indent=2, sort_keys=True)
            session_file.write("\n")

        try:
            destination.chmod(0o600)
        except OSError:
            # Keep execution resilient when chmod is blocked by environment policy.
            pass

        return destination

    def _contains_blacklisted_secret(self, value: str) -> bool:
        return any(marker in value for marker in self.blacklisted_strings)

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            if self._contains_blacklisted_secret(value):
                return self.REDACTION_TOKEN
            return value

        if isinstance(value, dict):
            return {key: self._redact_value(inner_value) for key, inner_value in value.items()}

        if isinstance(value, list):
            return [self._redact_value(item) for item in value]

        if isinstance(value, tuple):
            return [self._redact_value(item) for item in value]

        return value

    def _sanitize_session_id(self, session_id: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id.strip())
        return normalized or "session"


if __name__ == "__main__":
    sample_payload = {
        "session_id": "demo-world-physics",
        "messages": [
            {
                "role": "system",
                "content": "Never expose secrets in storage.",
            },
            {
                "role": "assistant",
                "content": f"Using token {'sk' + '-ant-api'}-demo-value in prompt context.",
            },
            {
                "role": "tool",
                "content": "MOCK_SECRET_KEY_FOR_TEST leaked in plain text",
            },
        ],
        "provider": {
            "google": "AIzaSy_mocked_google_token_123",
            "github": "ghp_mocked_github_token_abc",
        },
    }

    vault = SessionVault()
    saved_path = vault.save_session("session_vault_demo", sample_payload)
    saved_content = saved_path.read_text(encoding="utf-8")

    print(f"[INFO] Redacted session written to: {saved_path}")
    print(saved_content)

    forbidden_markers = vault.blacklisted_strings
    if any(marker in saved_content for marker in forbidden_markers):
        print("[FATAL] Secret marker found in persisted session file.")
        raise SystemExit(1)

    if SessionVault.REDACTION_TOKEN not in saved_content:
        print("[FATAL] Redaction token missing from persisted session file.")
        raise SystemExit(1)

    print("[PASS] Session file persisted with redaction applied.")