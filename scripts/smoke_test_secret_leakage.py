#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

from security.secret_injector import ephemeral_env


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def _assert_secret_absent(secret_key: str, secret_value: str) -> int:
    if secret_key in os.environ:
        return _fail(f"Secret key leaked in environment: {secret_key}")
    if secret_value in os.environ.values():
        return _fail("Secret value leaked in environment values.")
    return 0


def main() -> int:
    print("=== UnifAI Smoke Test: Secret Env Leakage (Rule 0) ===")

    transient_secret_key = "UNIFAI_PROVIDER_API_KEY"
    transient_secret_value = "MOCK_API_KEY_123"
    restore_secret_key = "UNIFAI_RESTORE_CHECK_KEY"

    original_transient = os.environ.get(transient_secret_key)
    original_restore = os.environ.get(restore_secret_key)

    try:
        os.environ.pop(transient_secret_key, None)
        os.environ[restore_secret_key] = "ORIGINAL_VALUE"

        with ephemeral_env({transient_secret_key: transient_secret_value}):
            if os.environ.get(transient_secret_key) != transient_secret_value:
                return _fail("Secret was not injected during success path.")

        absent_result = _assert_secret_absent(transient_secret_key, transient_secret_value)
        if absent_result != 0:
            return absent_result

        with ephemeral_env({restore_secret_key: "OVERRIDE_VALUE"}):
            if os.environ.get(restore_secret_key) != "OVERRIDE_VALUE":
                return _fail("Existing env key was not overridden inside context.")

        if os.environ.get(restore_secret_key) != "ORIGINAL_VALUE":
            return _fail("Existing env key was not restored after context exit.")

        try:
            with ephemeral_env({transient_secret_key: transient_secret_value}):
                if os.environ.get(transient_secret_key) != transient_secret_value:
                    return _fail("Secret was not injected during exception path.")
                raise RuntimeError("simulated provider crash")
        except RuntimeError:
            pass
        else:
            return _fail("Expected simulated provider crash was not raised.")

        absent_result = _assert_secret_absent(transient_secret_key, transient_secret_value)
        if absent_result != 0:
            return absent_result

    finally:
        if original_transient is None:
            os.environ.pop(transient_secret_key, None)
        else:
            os.environ[transient_secret_key] = original_transient

        if original_restore is None:
            os.environ.pop(restore_secret_key, None)
        else:
            os.environ[restore_secret_key] = original_restore

    print("[PASS] Secret env leakage smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())