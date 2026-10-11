"""Run actual integrated frontend helpers with offline DOM/API fixtures."""
import shutil
import subprocess
import unittest


class IntegratedUiTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node unavailable; standalone frontend check required")
    def test_integrated_frontend_offline(self):
        result = subprocess.run(
            ["node", "tests/integrated_ui_checks.cjs"],
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
