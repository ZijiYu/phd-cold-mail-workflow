"""Tests for the deterministic checks. Run: python -m unittest discover tests"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

import check_draft  # noqa: E402
import check_tracker  # noqa: E402


def run(fn, argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = fn(argv)
    return code, buf.getvalue()


class DraftChecks(unittest.TestCase):
    def test_good_examples_pass(self):
        for name in ["good_first.md", "good_early.md"]:
            code, out = run(check_draft.main, ["--strict", str(FIX / name)])
            self.assertEqual(code, 0, out)

    def test_good_followup_passes_in_followup_mode(self):
        code, out = run(check_draft.main, ["--strict", "--type", "followup", str(FIX / "good_followup.md")])
        self.assertEqual(code, 0, out)

    def test_bad_example_is_flagged(self):
        code, out = run(check_draft.main, ["--strict", str(FIX / "bad_first.md")])
        self.assertEqual(code, 1)
        for needle in ["subject carries little information", "greeting has no name", "deeply impressed", "admission"]:
            self.assertIn(needle, out)

    def test_placeholders_are_errors_but_links_are_not(self):
        code, out = run(check_draft.main, [str(FIX / "placeholders.md")])
        self.assertEqual(code, 1)
        self.assertIn("[Topic]", out)
        self.assertIn("{{paper}}", out)
        self.assertIn("TODO", out)
        self.assertNotIn("[my site]", out)

    def test_notes_after_rule_are_ignored(self):
        code, out = run(check_draft.main, [str(FIX / "good_first.md")])
        self.assertNotIn("[Name]", out)


class TrackerChecks(unittest.TestCase):
    def test_fixture(self):
        code, out = run(check_tracker.main, [str(FIX / "targets.csv"), "--today", "2026-10-28"])
        self.assertEqual(code, 1)
        self.assertIn("closed without close_reason", out)
        self.assertIn("unknown status 'waiting'", out)
        self.assertIn("max_contacts is 2", out)
        self.assertIn("sent 1 day(s) apart", out)
        self.assertIn("lakeview--whitfield: due 2026-10-20", out)
        self.assertIn("re-verify before sending", out)


if __name__ == "__main__":
    unittest.main()
