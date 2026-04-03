from __future__ import annotations

from dataclasses import dataclass, field, replace


UNCLEAR_STATUS = "unclear"
AGILE_STATUS = "agile"
CURRENT_STATUS = "current"
CLEARED_STATUS = "cleared"


ALLOWED_TASK_STATUSES = {
    UNCLEAR_STATUS,
    AGILE_STATUS,
    CURRENT_STATUS,
    CLEARED_STATUS,
}


class StateTransitionError(ValueError):
    pass


def _normalize_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")

    return normalized


def _normalize_lines(values: list[str] | tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, list):
        if not isinstance(values, tuple):
            raise TypeError(f"{field_name} must be a list/tuple of strings")

    normalized: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise TypeError(f"{field_name}[{index}] must be a string")
        line = " ".join(value.split())
        if not line:
            raise ValueError(f"{field_name}[{index}] must not be empty")
        normalized.append(line)

    return tuple(normalized)


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    description: str
    constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    status: str = UNCLEAR_STATUS

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _normalize_text(self.task_id, "task_id"))
        object.__setattr__(self, "description", _normalize_text(self.description, "description"))
        object.__setattr__(self, "constraints", _normalize_lines(self.constraints, "constraints"))
        object.__setattr__(
            self,
            "acceptance_criteria",
            _normalize_lines(self.acceptance_criteria, "acceptance_criteria"),
        )

        normalized_status = _normalize_text(self.status, "status")
        if normalized_status not in ALLOWED_TASK_STATUSES:
            raise ValueError(f"status must be one of {sorted(ALLOWED_TASK_STATUSES)}")
        object.__setattr__(self, "status", normalized_status)


@dataclass
class SpecsLedger:
    _unclear_ledger: dict[str, TaskSpec] = field(default_factory=dict, init=False, repr=False)
    _agile_ledger: dict[str, TaskSpec] = field(default_factory=dict, init=False, repr=False)
    _current_ledger: dict[str, TaskSpec] = field(default_factory=dict, init=False, repr=False)
    _cleared_ledger: dict[str, TaskSpec] = field(default_factory=dict, init=False, repr=False)

    @property
    def unclear_ledger(self) -> tuple[TaskSpec, ...]:
        return tuple(self._copy_spec(spec) for spec in self._unclear_ledger.values())

    @property
    def agile_ledger(self) -> tuple[TaskSpec, ...]:
        return tuple(self._copy_spec(spec) for spec in self._agile_ledger.values())

    @property
    def current_ledger(self) -> tuple[TaskSpec, ...]:
        return tuple(self._copy_spec(spec) for spec in self._current_ledger.values())

    @property
    def cleared_ledger(self) -> tuple[TaskSpec, ...]:
        return tuple(self._copy_spec(spec) for spec in self._cleared_ledger.values())

    def add_unclear(self, spec: TaskSpec) -> None:
        if not isinstance(spec, TaskSpec):
            raise TypeError("spec must be a TaskSpec")
        if self._has_task(spec.task_id):
            raise ValueError(f"task_id already exists: {spec.task_id}")

        unclear_spec = replace(spec, status=UNCLEAR_STATUS)
        self._unclear_ledger[unclear_spec.task_id] = self._copy_spec(unclear_spec)

    def promote_to_agile(self, task_id: str) -> None:
        normalized_task_id = _normalize_text(task_id, "task_id")
        spec = self._unclear_ledger.pop(normalized_task_id, None)
        if spec is None:
            raise StateTransitionError(
                f"task_id '{normalized_task_id}' cannot be promoted to agile because it is not in unclear_ledger"
            )

        self._agile_ledger[normalized_task_id] = replace(spec, status=AGILE_STATUS)

    def move_to_current(self, task_id: str) -> None:
        normalized_task_id = _normalize_text(task_id, "task_id")
        if self._current_ledger:
            raise StateTransitionError("current_ledger already has an in-flight task")

        spec = self._agile_ledger.pop(normalized_task_id, None)
        if spec is None:
            raise StateTransitionError(
                f"task_id '{normalized_task_id}' cannot move to current because it is not in agile_ledger"
            )

        self._current_ledger[normalized_task_id] = replace(spec, status=CURRENT_STATUS)

    def mark_as_cleared(self, task_id: str) -> None:
        normalized_task_id = _normalize_text(task_id, "task_id")

        current_spec = self._current_ledger.pop(normalized_task_id, None)
        if current_spec is not None:
            self._cleared_ledger[normalized_task_id] = replace(current_spec, status=CLEARED_STATUS)
            return

        agile_spec = self._agile_ledger.pop(normalized_task_id, None)
        if agile_spec is not None:
            self._cleared_ledger[normalized_task_id] = replace(agile_spec, status=CLEARED_STATUS)
            return

        if normalized_task_id in self._unclear_ledger:
            raise StateTransitionError(
                f"task_id '{normalized_task_id}' cannot be cleared because it is still in unclear_ledger"
            )

        if normalized_task_id in self._cleared_ledger:
            raise StateTransitionError(
                f"task_id '{normalized_task_id}' is already in cleared_ledger"
            )

        raise StateTransitionError(
            f"task_id '{normalized_task_id}' cannot be cleared because it was never promoted"
        )

    def get_task_prompt_context(self, task_id: str) -> str:
        normalized_task_id = _normalize_text(task_id, "task_id")
        spec = self._find_task(normalized_task_id)
        if spec is None:
            raise KeyError(f"unknown task_id: {normalized_task_id}")

        constraints_lines = "\n".join(f"- {constraint}" for constraint in spec.constraints)
        acceptance_lines = "\n".join(f"- {criterion}" for criterion in spec.acceptance_criteria)

        return "\n".join(
            [
                f"Task ID: {spec.task_id}",
                f"Status: {spec.status}",
                "Description:",
                spec.description,
                "Constraints:",
                constraints_lines,
                "Acceptance Criteria:",
                acceptance_lines,
            ]
        )

    def _has_task(self, task_id: str) -> bool:
        return self._find_task(task_id) is not None

    def _find_task(self, task_id: str) -> TaskSpec | None:
        for ledger in (
            self._unclear_ledger,
            self._agile_ledger,
            self._current_ledger,
            self._cleared_ledger,
        ):
            spec = ledger.get(task_id)
            if spec is not None:
                return spec
        return None

    @staticmethod
    def _copy_spec(spec: TaskSpec) -> TaskSpec:
        return TaskSpec(
            task_id=spec.task_id,
            description=spec.description,
            constraints=tuple(spec.constraints),
            acceptance_criteria=tuple(spec.acceptance_criteria),
            status=spec.status,
        )
