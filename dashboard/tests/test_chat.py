"""Chat endpoint tests with a fake Claude Code CLI (tests/fake_claude.py)."""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient
    from dashboard.app.api import create_app
    from dashboard.app.chat import StreamParser
except ImportError as e:  # pragma: no cover
    raise unittest.SkipTest(f"dashboard dependencies not installed: {e}")

SAMPLE = ROOT / "dashboard" / "tests" / "fixtures" / "outreach"


def events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(SAMPLE, self.tmp / "data")
        self.bin = self.tmp / "claude"
        self.bin.write_text(f"#!/bin/sh\nexec {sys.executable} {HERE / 'fake_claude.py'} \"$@\"\n")
        self.bin.chmod(self.bin.stat().st_mode | stat.S_IEXEC)
        self.log = self.tmp / "argv.jsonl"
        os.environ["FAKE_CLAUDE_LOG"] = str(self.log)
        os.environ.pop("FAKE_CLAUDE_MODE", None)
        self.app = create_app(self.tmp / "data", self.tmp / "state", claude_bin=str(self.bin), workdir=ROOT)
        self.c = TestClient(self.app, base_url="http://127.0.0.1:8765")
        self.c.headers["Authorization"] = f"Bearer {self.app.state.token}"

    def tearDown(self):
        os.environ.pop("FAKE_CLAUDE_LOG", None)
        os.environ.pop("FAKE_CLAUDE_MODE", None)
        shutil.rmtree(self.tmp)

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()]

    def test_status(self):
        s = self.c.get("/api/chat/status").json()
        self.assertTrue(s["available"])
        self.assertIn("9.9.9", s["version"])

    def test_requires_token(self):
        anon = TestClient(self.app, base_url="http://127.0.0.1:8765")
        self.assertEqual(anon.post("/api/chat", json={"message": "hi"}).status_code, 401)

    def test_stream_and_guardrails(self):
        r = self.c.post("/api/chat", json={"message": "看看 Dana", "campaign": "fall-2027", "target_id": "lakeview--dana-whitfield"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("text/event-stream"))
        evs = events(r.text)
        types = [e["type"] for e in evs]
        self.assertEqual(types[0], "session")
        self.assertIn("text_delta", types)
        tool = next(e for e in evs if e["type"] == "tool")
        self.assertEqual((tool["name"], tool["label"], tool["summary"]), ("Read", "读取", "README.md"))
        self.assertTrue(any(e["type"] == "tool_result" and "README" in e["preview"] for e in evs))
        self.assertNotIn("subagent", r.text)
        done = evs[-1]
        self.assertEqual(done["type"], "done")
        self.assertEqual(done["denied"], ["Bash"])
        self.assertAlmostEqual(done["cost_usd"], 0.0123)

        argv = self.calls()[0]["argv"]
        prompt = argv[argv.index("-p") + 1]
        self.assertIn("[面板上下文]", prompt)
        self.assertIn("lakeview--dana-whitfield", prompt)
        self.assertTrue(prompt.endswith("看看 Dana"))
        self.assertIn("--strict-mcp-config", argv)
        self.assertNotIn("--mcp-config", argv)
        self.assertNotIn("bypassPermissions", argv)
        allowed = argv[argv.index("--allowedTools") + 1: argv.index("--disallowedTools")]
        self.assertNotIn("Bash", allowed)                       # no unrestricted shell
        self.assertTrue(all(not a.startswith("mcp__") for a in allowed))
        self.assertEqual(self.calls()[0]["cwd"], str(ROOT))
        self.assertIn("--add-dir", argv)                        # data folder outside the repo

    def test_resume_session(self):
        sid = "abcdef12-3456-7890-abcd-ef1234567890"
        evs = events(self.c.post("/api/chat", json={"message": "继续", "session_id": sid}).text)
        argv = self.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--resume") + 1], sid)
        self.assertEqual(evs[-1]["session_id"], sid)

    def test_rejects_flag_like_ids(self):
        self.assertEqual(self.c.post("/api/chat", json={"message": "x", "session_id": "--dangerously"}).status_code, 422)
        self.assertEqual(self.c.post("/api/chat", json={"message": "x", "model": "--x"}).status_code, 422)
        self.assertEqual(self.c.post("/api/chat", json={"message": ""}).status_code, 422)

    def test_logged_out_is_explained(self):
        os.environ["FAKE_CLAUDE_MODE"] = "logged_out"
        evs = events(self.c.post("/api/chat", json={"message": "hi"}).text)
        self.assertEqual(evs[-1]["type"], "error")
        self.assertIn("登录", evs[-1]["message"])

    def test_missing_cli(self):
        app = create_app(self.tmp / "data", self.tmp / "state2", claude_bin=str(self.tmp / "nope"), workdir=ROOT)
        c = TestClient(app, base_url="http://127.0.0.1:8765")
        c.headers["Authorization"] = f"Bearer {app.state.token}"
        old = os.environ.get("PATH", "")
        os.environ["PATH"] = str(self.tmp)   # no `claude` here
        try:
            import dashboard.app.chat as chat_mod
            orig = chat_mod.find_claude
            chat_mod.find_claude = lambda explicit=None: None
            try:
                self.assertFalse(c.get("/api/chat/status").json()["available"])
                evs = events(c.post("/api/chat", json={"message": "hi"}).text)
                self.assertEqual(evs[0]["type"], "error")
            finally:
                chat_mod.find_claude = orig
        finally:
            os.environ["PATH"] = old


class ParserTests(unittest.TestCase):
    def test_summaries(self):
        p = StreamParser([ROOT])
        ev = p.feed({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "WebSearch", "input": {"query": "Zhaozheng Yin fall 2027"}},
            {"type": "tool_use", "id": "b", "name": "Edit", "input": {"file_path": str(ROOT / "outreach/fall-2027/targets.csv")}},
        ]}})
        self.assertEqual([e["summary"] for e in ev], ["Zhaozheng Yin fall 2027", "outreach/fall-2027/targets.csv"])
        self.assertEqual([e["label"] for e in ev], ["搜索网页", "修改"])


if __name__ == "__main__":
    unittest.main()
