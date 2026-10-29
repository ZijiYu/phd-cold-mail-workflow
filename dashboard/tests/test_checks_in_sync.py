"""The dashboard vendors the skill's check scripts; keep the copies identical."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "cold-email" / "scripts"
VENDORED = ROOT / "dashboard" / "app" / "checks"


class ChecksInSync(unittest.TestCase):
    def test_copies_match(self):
        if not SKILL.is_dir():
            self.skipTest("skill folder not present next to the dashboard")
        for name in ("check_draft.py", "check_tracker.py"):
            with self.subTest(name=name):
                self.assertEqual(
                    (SKILL / name).read_text(encoding="utf-8"),
                    (VENDORED / name).read_text(encoding="utf-8"),
                    f"{name} differs; run: cp cold-email/scripts/{name} dashboard/app/checks/",
                )


if __name__ == "__main__":
    unittest.main()
