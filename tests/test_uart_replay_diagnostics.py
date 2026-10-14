"""Retain failed RTL replay inputs without relaxing exact comparisons."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _reproduce_core as core


class ReplayDiagnosticsTest(unittest.TestCase):
    def fixture(self, folder):
        root = Path(folder) / "retained"
        relative = [
            "rtl/ben-marshall-uart/trace_manifest.json",
            "rtl/ben-marshall-uart/import_report.json",
            "rtl/ben-marshall-uart/generated/manifest.json",
            "rtl/ben-marshall-uart/generated/compile.log",
            "rtl/ben-marshall-uart/generated/uart_tx.v",
            "rtl/ben-marshall-uart/generated/uart_rx.v",
            "models/uart-loopback-rtl.json", "models/rtl-campaign.json",
        ]
        relative += [f"rtl/ben-marshall-uart/traces/trace-{i}.csv" for i in range(33)]
        for name in relative:
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"retained bytes\n")
        candidate = Path(folder) / "rebuilt"
        shutil.copytree(root, candidate)
        return root, candidate, Path(folder) / "diagnostics"

    def test_exact_replay_does_not_create_failure_material(self):
        with tempfile.TemporaryDirectory() as folder:
            root, candidate, diagnostic = self.fixture(folder)
            with patch.object(core, "ROOT", root):
                result = core.compare_uart_rebuild(candidate, diagnostic)
            self.assertEqual(result, {"byte_identical_files": 41, "traces": 33})
            self.assertFalse(diagnostic.exists())

    def test_manifest_mismatch_fails_and_retains_actual_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root, candidate, diagnostic = self.fixture(folder)
            rel = Path("rtl/ben-marshall-uart/trace_manifest.json")
            (candidate / rel).write_bytes(b"different tool provenance\n")
            with patch.object(core, "ROOT", root):
                with self.assertRaisesRegex(AssertionError, "trace_manifest.json"):
                    core.compare_uart_rebuild(candidate, diagnostic)
            self.assertEqual((diagnostic / rel).read_bytes(), b"different tool provenance\n")
            self.assertEqual((root / rel).read_bytes(), b"retained bytes\n")
            self.assertEqual(len(list(diagnostic.rglob("*.csv"))), 33)


if __name__ == "__main__":
    unittest.main()
