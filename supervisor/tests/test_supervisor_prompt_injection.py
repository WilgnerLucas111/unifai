import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

spec = importlib.util.spec_from_file_location("unifai_supervisor_runtime_prompt", SUPERVISOR_DIR / "supervisor.py")
supervisor_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(supervisor_runtime)


class FakeSystemInjector:
    def __init__(self):
        self.calls = []

    def get_physics_context(self) -> str:
        self.calls.append("get_physics_context")
        return "<system_physics>\nOS: TestOS 1.0\nCurrent Date (UTC): 2026-04-02T00:00:00\nWorking Directory: /tmp/test\n</system_physics>"

    def inject_specs_ledger(self, base_prompt: str, specs_path: str = "SPECS.md") -> str:
        self.calls.append(("inject_specs_ledger", base_prompt, specs_path))
        if not base_prompt:
            return "<specs_ledger>\n# Demo Specs\n- Rule 0 first\n</specs_ledger>"
        return f"{base_prompt}\n\n<specs_ledger>\n# Demo Specs\n- Rule 0 first\n</specs_ledger>"


class SupervisorPromptInjectionTests(unittest.TestCase):
    def test_prepare_task_spec_mounts_prompt_context(self):
        runtime = supervisor_runtime.SupervisorRuntime(system_injector=FakeSystemInjector())

        mounted = runtime.prepare_task_spec({"type": "llm", "prompt": "Base prompt"})

        self.assertIn("system_physics", mounted)
        self.assertIn("<system_physics>", mounted["prompt"])
        self.assertIn("Base prompt", mounted["prompt"])
        self.assertIn("<specs_ledger>", mounted["prompt"])

    def test_prepare_task_spec_creates_prompt_when_missing(self):
        runtime = supervisor_runtime.SupervisorRuntime(system_injector=FakeSystemInjector())

        mounted = runtime.prepare_task_spec({"type": "tool", "cmd": "date"})

        self.assertIn("system_physics", mounted)
        self.assertIn("prompt", mounted)
        self.assertTrue(mounted["prompt"].startswith("<system_physics>"))
        self.assertIn("<specs_ledger>", mounted["prompt"])


if __name__ == "__main__":
    unittest.main()