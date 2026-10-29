#!/usr/bin/env python3
"""Stand-in for the Claude Code CLI in tests.

Records its argv to $FAKE_CLAUDE_LOG and prints a short stream-json run.
FAKE_CLAUDE_MODE=logged_out prints a login error and exits 1."""
import json
import os
import sys

if "--version" in sys.argv:
    print("9.9.9 (Claude Code)")
    sys.exit(0)

log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")

if os.environ.get("FAKE_CLAUDE_MODE") == "logged_out":
    print("Invalid API key · Please run /login", file=sys.stderr)
    sys.exit(1)

sid = sys.argv[sys.argv.index("--resume") + 1] if "--resume" in sys.argv else "11111111-2222-3333-4444-555555555555"


def emit(o):
    print(json.dumps(o), flush=True)


emit({"type": "system", "subtype": "init", "session_id": sid, "model": "claude-test"})
emit({"type": "stream_event", "session_id": sid, "event": {"type": "content_block_delta", "index": 0,
      "delta": {"type": "text_delta", "text": "我先看一下"}}})
emit({"type": "stream_event", "session_id": sid, "event": {"type": "content_block_delta", "index": 0,
      "delta": {"type": "text_delta", "text": "表格。"}}})
emit({"type": "assistant", "session_id": sid, "message": {"content": [
    {"type": "text", "text": "我先看一下表格。"},
    {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {"file_path": os.path.join(os.getcwd(), "README.md")}}]}})
emit({"type": "user", "session_id": sid, "message": {"content": [
    {"type": "tool_result", "tool_use_id": "tu_1", "content": [{"type": "text", "text": "# README\nhello"}]}]}})
emit({"type": "assistant", "session_id": sid, "parent_tool_use_id": "tu_x", "message": {"content": [
    {"type": "text", "text": "subagent text that should be hidden"}]}})
emit({"type": "assistant", "session_id": sid, "message": {"content": [{"type": "text", "text": "看完了。"}]}})
emit({"type": "result", "subtype": "success", "session_id": sid, "is_error": False, "result": "看完了。",
      "total_cost_usd": 0.0123, "duration_ms": 2100, "num_turns": 2,
      "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "git push"}}]})
