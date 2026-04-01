import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_DIR = ROOT / "supervisor"
MORPHEUS_DAEMON = SUPERVISOR_DIR / "morpheus" / "daemon.py"

spec = importlib.util.spec_from_file_location("unifai_morpheus_daemon", MORPHEUS_DAEMON)
morpheus_daemon = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = morpheus_daemon
spec.loader.exec_module(morpheus_daemon)


class MorpheusDaemonTests(unittest.TestCase):
    def test_candidate_is_accepted_when_evidence_matches_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "state.txt"
            target.write_text("gateway restart hint ready", encoding="utf-8")

            daemon = morpheus_daemon.MorpheusDaemon(root)
            candidate = morpheus_daemon.MemoryCandidate(
                candidate_id="c1",
                claim="Gateway hint is present",
                evidence=(
                    morpheus_daemon.EvidenceRequest(
                        path="state.txt",
                        contains_all=("gateway", "hint"),
                    ),
                ),
            )

            report = daemon.consolidate((candidate,))
            self.assertEqual(report.accepted, 1)
            self.assertEqual(report.rejected, 0)
            self.assertEqual(report.verdicts[0].status, "accepted")

    def test_candidate_is_rejected_when_required_token_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "state.txt"
            target.write_text("gateway restart", encoding="utf-8")

            daemon = morpheus_daemon.MorpheusDaemon(root)
            candidate = morpheus_daemon.MemoryCandidate(
                candidate_id="c2",
                claim="Codex auth marker exists",
                evidence=(
                    morpheus_daemon.EvidenceRequest(
                        path="state.txt",
                        contains_all=("codex auth error",),
                    ),
                ),
            )

            report = daemon.consolidate((candidate,))
            self.assertEqual(report.accepted, 0)
            self.assertEqual(report.rejected, 1)
            self.assertEqual(report.verdicts[0].status, "rejected")

    def test_candidate_without_evidence_stays_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            daemon = morpheus_daemon.MorpheusDaemon(root)
            candidate = morpheus_daemon.MemoryCandidate(
                candidate_id="c3",
                claim="No proof attached",
                evidence=(),
            )

            report = daemon.consolidate((candidate,))
            self.assertEqual(report.uncertain, 1)
            self.assertEqual(report.verdicts[0].status, "uncertain")


if __name__ == "__main__":
    unittest.main()