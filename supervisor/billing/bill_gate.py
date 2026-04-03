from __future__ import annotations

import threading
from dataclasses import dataclass


class BudgetExceededError(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetConfig:
    max_tokens: int
    max_usd: float

    def __post_init__(self) -> None:
        if not isinstance(self.max_tokens, int):
            raise TypeError("max_tokens must be an integer")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")

        if not isinstance(self.max_usd, (int, float)):
            raise TypeError("max_usd must be numeric")
        if float(self.max_usd) < 0:
            raise ValueError("max_usd must be greater than or equal to zero")
        object.__setattr__(self, "max_usd", float(self.max_usd))


class BillGate:
    __slots__ = ("_config", "__consumed_tokens", "__consumed_usd", "_lock")

    def __init__(self, config: BudgetConfig) -> None:
        if not isinstance(config, BudgetConfig):
            raise TypeError("config must be a BudgetConfig")

        self._config = config
        self.__consumed_tokens = 0
        self.__consumed_usd = 0.0
        self._lock = threading.Lock()

    @property
    def config(self) -> BudgetConfig:
        return self._config

    @property
    def consumed_tokens(self) -> int:
        with self._lock:
            return self.__consumed_tokens

    @property
    def consumed_usd(self) -> float:
        with self._lock:
            return self.__consumed_usd

    def request_budget(self, estimated_tokens: int) -> bool:
        normalized_estimate = self._normalize_token_amount(estimated_tokens, field_name="estimated_tokens")

        with self._lock:
            projected_tokens = self.__consumed_tokens + normalized_estimate
            if projected_tokens > self._config.max_tokens:
                raise BudgetExceededError(
                    "Budget exceeded before execution: "
                    f"projected_tokens={projected_tokens}, max_tokens={self._config.max_tokens}"
                )
            return True

    def commit_usage(self, actual_tokens: int) -> None:
        normalized_actual = self._normalize_token_amount(actual_tokens, field_name="actual_tokens")

        with self._lock:
            projected_tokens = self.__consumed_tokens + normalized_actual
            if projected_tokens > self._config.max_tokens:
                raise BudgetExceededError(
                    "Budget exceeded while committing usage: "
                    f"projected_tokens={projected_tokens}, max_tokens={self._config.max_tokens}"
                )
            self.__consumed_tokens = projected_tokens

    @staticmethod
    def _normalize_token_amount(value: int, field_name: str) -> int:
        if not isinstance(value, int):
            raise TypeError(f"{field_name} must be an integer")
        if value < 0:
            raise ValueError(f"{field_name} must be greater than or equal to zero")
        return value
