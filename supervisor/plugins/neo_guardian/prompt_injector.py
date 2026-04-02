#!/usr/bin/env python3
"""Dynamic prompt injector for the Neo Guardian layer."""

import datetime
import json
import os
import platform
import tempfile


class SystemInjector:
    """Builds situational prompt context for the Supervisor and agents."""

    def __init__(self, project_root: str | None = None) -> None:
        self.project_root = project_root or self._resolve_project_root()

    def _resolve_project_root(self) -> str:
        current_file = os.path.abspath(__file__)
        return os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(current_file)
                )
            )
        )

    def get_physics_context(self) -> str:
        """Return a system physics snapshot formatted as XML."""
        os_name = f"{platform.system()} {platform.release()}"
        current_date_utc = datetime.datetime.utcnow().isoformat()
        working_directory = os.getcwd()

        return (
            "<system_physics>\n"
            f"OS: {os_name}\n"
            f"Current Date (UTC): {current_date_utc}\n"
            f"Working Directory: {working_directory}\n"
            "</system_physics>"
        )

    def inject_specs_ledger(self, base_prompt: str, specs_path: str = "SPECS.md") -> str:
        """Inject the specs ledger into a base prompt when the file exists."""
        specs_file_path = os.path.join(self.project_root, specs_path)
        if not os.path.isfile(specs_file_path):
            return base_prompt

        with open(specs_file_path, "r", encoding="utf-8") as specs_file:
            specs_content = specs_file.read()

        specs_block = f"<specs_ledger>\n{specs_content}\n</specs_ledger>"
        if not base_prompt:
            return specs_block

        return f"{base_prompt}\n\n{specs_block}"


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="unifai-system-injector-") as demo_root:
        specs_path = os.path.join(demo_root, "SPECS.md")
        with open(specs_path, "w", encoding="utf-8") as specs_file:
            specs_file.write("# Demo Specs\n- Keep context grounded.\n- Never hallucinate task scope.\n")

        injector = SystemInjector(project_root=demo_root)
        physics_context = injector.get_physics_context()
        dummy_prompt = "You are the UnifAI assistant."
        injected_prompt = injector.inject_specs_ledger(dummy_prompt)

        print(physics_context)
        print(injected_prompt)
        print(
            json.dumps(
                {
                    "physics_context_emitted": True,
                    "specs_injected": "<specs_ledger>" in injected_prompt,
                },
                indent=2,
                sort_keys=True,
            )
        )