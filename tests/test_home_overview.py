"""Offline execution of actual homepage JavaScript without real APIs or credentials."""
import shutil
import subprocess
import unittest


class HomeOverviewTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node unavailable; standalone frontend check required")
    def test_actual_homepage_behavior_offline(self):
        result = subprocess.run(
            ["node", "tests/home_overview_checks.cjs"],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
