from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def ephemeral_env(secrets: dict | None) -> Iterator[None]:
    if secrets is None:
        secrets = {}

    if not isinstance(secrets, dict):
        raise TypeError("secrets must be a dictionary")

    normalized: dict[str, str] = {}
    for key, value in secrets.items():
        if not isinstance(key, str) or not key:
            raise TypeError("secret keys must be non-empty strings")
        if value is None:
            raise TypeError(f"secret value for key '{key}' must not be None")
        normalized[key] = str(value)

    previous_values: dict[str, str | None] = {}

    try:
        for key, value in normalized.items():
            previous_values[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key in normalized:
            previous = previous_values.get(key)
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous