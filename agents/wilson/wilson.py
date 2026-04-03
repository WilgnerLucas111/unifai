from __future__ import annotations

from supervisor.types.signal_dto import TaskSignal


class WilsonAgent:
    @staticmethod
    def render_report(signal: TaskSignal) -> str:
        if not isinstance(signal, TaskSignal):
            raise TypeError("signal must be a TaskSignal")

        return "\n".join(
            [
                "# Wilson Signal Report",
                "",
                f"- Task ID: {signal.task_id}",
                f"- Status: {signal.status}",
                "",
                "## Summary",
                signal.summary,
            ]
        )
