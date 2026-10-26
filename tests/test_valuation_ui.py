"""Run actual price-workspace behavior offline, independently of the live UI QA."""
import shutil
import subprocess
import unittest


class ValuationUiTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_actual_workspace_price_controls_and_request_races(self):
        result = subprocess.run(
            ["node", "tests/valuation_ui_checks.cjs"], capture_output=True,
            text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
