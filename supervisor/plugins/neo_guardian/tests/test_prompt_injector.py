import datetime
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SUPERVISOR_DIR = ROOT / "supervisor"

import sys

sys.path.insert(0, str(SUPERVISOR_DIR))

from plugins.neo_guardian.prompt_injector import SystemInjector


class SystemInjectorTests(unittest.TestCase):
    def test_get_physics_context_contains_system_details(self):
        injector = SystemInjector(project_root=str(ROOT))
        original_cwd = os.getcwd()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                os.chdir(tmp_dir)
                context = injector.get_physics_context()

            self.assertTrue(context.startswith("<system_physics>"))
            self.assertTrue(context.endswith("</system_physics>"))
            self.assertIn(f"OS: {os.uname().sysname} {os.uname().release}", context)
            self.assertIn("Current Date (UTC):", context)
            self.assertIn("Working Directory:", context)

            date_line = next(line for line in context.splitlines() if line.startswith("Current Date (UTC): "))
            datetime.datetime.fromisoformat(date_line.split(": ", 1)[1])
        finally:
            os.chdir(original_cwd)

    def test_inject_specs_ledger_inserts_content_when_present(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            specs_file = Path(tmp_dir) / "SPECS.md"
            specs_file.write_text("# Specs\n- Rule 0 first\n", encoding="utf-8")

            injector = SystemInjector(project_root=tmp_dir)
            result = injector.inject_specs_ledger("Base prompt")

            self.assertIn("Base prompt", result)
            self.assertIn("<specs_ledger>", result)
            self.assertIn("# Specs", result)
            self.assertIn("- Rule 0 first", result)
            self.assertIn("</specs_ledger>", result)

    def test_inject_specs_ledger_returns_base_prompt_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            injector = SystemInjector(project_root=tmp_dir)
            base_prompt = "Base prompt"

            self.assertEqual(injector.inject_specs_ledger(base_prompt), base_prompt)


if __name__ == "__main__":
    unittest.main()