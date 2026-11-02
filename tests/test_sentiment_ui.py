"""Actual radar UI behavior, with no browser or network."""
import shutil
import subprocess
import unittest
class SentimentUiTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_actual_radar_reset_failure_escaping_weights_and_late_responses(self):
        result = subprocess.run(["node","tests/sentiment_ui_checks.cjs"], capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
