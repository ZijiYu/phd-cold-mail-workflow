"""Chat with Claude Code from the dashboard.

Each message runs the local Claude Code CLI in print mode inside the repo:

    claude -p <message> --output-format stream-json --verbose --include-partial-messages
           [--resume <session_id>] --allowedTools ... --strict-mcp-config ...

and its JSON lines are turned into a small set of events for the browser
(sent as Server-Sent Events). Claude Code uses your own login and settings;
the dashboard only starts it and relays what it prints.

Guardrails:
  - --strict-mcp-config with no --mcp-config: no MCP servers load, so no
    Gmail or other connector tools exist in these runs (it cannot send email);
  - an allowlist of tools: read/search files, edit files in the repo and the
    data folder, web search/fetch, and the skill's two check scripts. Anything
    else (other shell commands, git push, ...) is denied, because print mode
    has nobody to approve it;
  - one run at a time, killed when the browser stops listening.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import AsyncIterator

ALLOWED_TOOLS = [
    "Read", "Glob", "Grep", "LS",
    "Edit", "MultiEdit", "Write", "TodoWrite",
    "WebSearch", "WebFetch", "Skill",
    "Bash(python3 cold-email/scripts/check_draft.py:*)",
    "Bash(python3 cold-email/scripts/check_tracker.py:*)",
]
DISALLOWED_TOOLS = ["Bash(git push:*)", "Bash(curl:*)", "Bash(rm:*)"]

SYSTEM_PROMPT = """You are running inside Ken's PhD outreach dashboard (套磁工作台), started from its chat panel.
- The working directory is the phd-cold-mail-workflow repo. The cold-email skill lives in cold-email/: read cold-email/SKILL.md (and the references it points to) before discovery, drafting, follow-ups or tracker work, and follow it.
- Campaign data: {data_dir}/<campaign>/targets.csv, programs.csv and drafts/*.md. The dashboard re-reads these files after every reply, so edits show up immediately. Keep the CSV header and every column; change only the rows and cells you mean to; never reorder or drop columns.
- You cannot send email and must not try. Drafts are written to drafts/*.md; Ken reviews them and pushes them to Gmail drafts from the dashboard, then sends them himself.
- Shell access is limited to the skill's check scripts (python3 cold-email/scripts/check_draft.py / check_tracker.py). Do not ask for other commands.
- Verify facts about professors (recruiting, moves, emails) from their pages before writing them, and cite the URL in source_urls.
- Reply in Chinese, briefly. Each message may start with a [面板上下文] block describing what Ken is looking at; use it, but don't repeat it back."""

TOOL_LABELS = {
    "Read": "读取", "Glob": "查找文件", "Grep": "搜索内容", "LS": "列目录",
    "Edit": "修改", "MultiEdit": "修改", "Write": "写入", "TodoWrite": "更新任务清单",
    "WebSearch": "搜索网页", "WebFetch": "打开网页", "Bash": "运行", "Skill": "使用技能", "Task": "分派子任务",
}


def find_claude(explicit: str | None = None) -> str | None:
    """Locate the Claude Code CLI: explicit path, $PHD_CLAUDE_BIN, PATH, then the usual install spots."""
    for c in (explicit, os.environ.get("PHD_CLAUDE_BIN")):
        if c and Path(c).expanduser().is_file():
            return str(Path(c).expanduser())
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for p in (home / ".claude/local/claude", home / ".local/bin/claude", Path("/opt/homebrew/bin/claude"),
              Path("/usr/local/bin/claude"), home / ".npm-global/bin/claude"):
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def _short(path: str, roots: list[Path]) -> str:
    for r in roots:
        try:
            return str(Path(path).resolve().relative_to(r.resolve()))
        except (ValueError, OSError):
            continue
    return path


class ChatRunner:
    def __init__(self, workdir: Path, data_dir: Path, binary: str | None = None, timeout_s: int = 1800):
        self.workdir = Path(workdir).resolve()
        self.data_dir = Path(data_dir).resolve()
        self._explicit = binary
        self.timeout_s = timeout_s
        self._lock = asyncio.Lock()
        self._proc: asyncio.subprocess.Process | None = None
        self._version: tuple[str, str] | None = None

    # ------------------------------------------------------------ status
    def binary(self) -> str | None:
        return find_claude(self._explicit)

    def status(self) -> dict:
        b = self.binary()
        if not b:
            return {"available": False, "busy": self.busy,
                    "detail": "没有找到 Claude Code 命令行（claude）。先安装并登录 Claude Code，或用环境变量 PHD_CLAUDE_BIN 指定路径。"}
        if not self._version or self._version[0] != b:
            try:
                out = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=15)
                self._version = (b, (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else "")
            except (OSError, subprocess.SubprocessError) as e:
                return {"available": False, "busy": self.busy, "path": b, "detail": f"claude 无法运行：{e}"}
        return {"available": True, "busy": self.busy, "path": b, "version": self._version[1], "workdir": str(self.workdir)}

    @property
    def busy(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    # ------------------------------------------------------------ command
    def command(self, binary: str, prompt: str, session_id: str | None, model: str | None) -> list[str]:
        cmd = [binary, "-p", prompt,
               "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--permission-mode", "default",
               "--allowedTools", *ALLOWED_TOOLS,
               "--disallowedTools", *DISALLOWED_TOOLS,
               "--strict-mcp-config",
               "--append-system-prompt", SYSTEM_PROMPT.format(data_dir=self.data_dir)]
        if not _inside(self.data_dir, self.workdir):
            cmd += ["--add-dir", str(self.data_dir)]
        if session_id:
            cmd += ["--resume", session_id]
        if model:
            cmd += ["--model", model]
        return cmd

    @staticmethod
    def context_block(campaign: str | None, target: dict | None, data_dir: Path) -> str:
        lines = []
        if campaign:
            lines.append(f"申请季：{campaign}（文件：{data_dir / campaign}/targets.csv、programs.csv、drafts/）")
        if target:
            lines.append(f"Ken 正在看：{target.get('professor', '')}（{target.get('institution', '')}），"
                         f"target_id={target.get('target_id', '')}，状态 {target.get('status', '')}")
        return ("[面板上下文]\n" + "\n".join(lines) + "\n[/面板上下文]\n\n") if lines else ""

    # ------------------------------------------------------------ run
    async def stop(self) -> bool:
        p = self._proc
        if p and p.returncode is None:
            p.terminate()
            try:
                await asyncio.wait_for(p.wait(), 5)
            except asyncio.TimeoutError:
                p.kill()
            return True
        return False

    async def run(self, message: str, session_id: str | None = None, model: str | None = None,
                  context: str = "") -> AsyncIterator[dict]:
        binary = self.binary()
        if not binary:
            yield {"type": "error", "message": self.status()["detail"]}
            return
        if self._lock.locked():
            yield {"type": "error", "message": "Claude 还在处理上一条消息，等它完成或点“停止”。"}
            return
        async with self._lock:
            # A fresh, independent Claude Code session even if the dashboard itself
            # was started from inside another Claude Code session.
            env = {k: v for k, v in os.environ.items()
                   if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
                                "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PID")}
            try:
                self._proc = await asyncio.create_subprocess_exec(
                    *self.command(binary, context + message, session_id, model),
                    cwd=self.workdir, env=env, stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=16 * 1024 * 1024)
            except OSError as e:
                yield {"type": "error", "message": f"无法启动 claude：{e}"}
                return
            proc = self._proc
            parser = StreamParser([self.workdir, self.data_dir])
            got_result = False
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.timeout_s
            try:
                assert proc.stdout is not None
                while True:
                    raw = await asyncio.wait_for(proc.stdout.readline(), max(1.0, deadline - loop.time()))
                    if not raw:
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    for ev in parser.feed(obj):
                        got_result = got_result or ev["type"] == "done"
                        yield ev
                await proc.wait()
            except asyncio.TimeoutError:
                await self.stop()
                got_result = True
                yield {"type": "error", "message": f"超过 {self.timeout_s // 60} 分钟，已停止。"}
            finally:
                if proc.returncode is None:   # browser went away or we were cancelled
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), 5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        proc.kill()
                self._proc = None
            if not got_result:
                err = b""
                if proc.stderr is not None:
                    try:
                        err = await asyncio.wait_for(proc.stderr.read(4000), 2)
                    except (asyncio.TimeoutError, ValueError):
                        pass
                msg = err.decode("utf-8", "replace").strip()
                if proc.returncode in (-15, -9, 143, 137):
                    yield {"type": "stopped"}
                else:
                    yield {"type": "error", "message": _friendly(msg) or f"claude 退出（代码 {proc.returncode}），没有返回结果。"}


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _friendly(stderr: str) -> str:
    if re.search(r"not logged in|please run /login|invalid api key|authentication", stderr, re.I):
        return "Claude Code 还没登录：在终端运行一次 claude，按提示登录后再试。"
    if re.search(r"No conversation found|session.*not found", stderr, re.I):
        return "找不到之前的对话（可能已过期）。点“新对话”重新开始。"
    return stderr[-600:]


class StreamParser:
    """Turn Claude Code stream-json objects into browser events.

    Events: session, text_delta, text, tool, tool_result, done, error."""

    def __init__(self, roots: list[Path]):
        self.roots = roots
        self.tools: dict[str, str] = {}

    def feed(self, o: dict) -> list[dict]:
        t = o.get("type")
        if t == "system" and o.get("subtype") == "init":
            return [{"type": "session", "session_id": o.get("session_id"), "model": o.get("model")}]
        if t == "stream_event":
            ev = o.get("event") or {}
            if o.get("parent_tool_use_id"):
                return []
            if ev.get("type") == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                return [{"type": "text_delta", "text": ev["delta"].get("text", "")}]
            return []
        if t == "assistant":
            if o.get("parent_tool_use_id"):
                return []
            out = []
            for block in (o.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text"):
                    out.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "tool_use":
                    name = block.get("name", "")
                    self.tools[block.get("id", "")] = name
                    out.append({"type": "tool", "id": block.get("id"), "name": name,
                                "label": TOOL_LABELS.get(name, name), "summary": self.summarize(name, block.get("input") or {})})
            return out
        if t == "user":
            out = []
            content = (o.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result":
                    out.append({"type": "tool_result", "id": block.get("tool_use_id"),
                                "is_error": bool(block.get("is_error")), "preview": _preview(block.get("content"))})
            return out
        if t == "result":
            denials = [d.get("tool_name", "") for d in o.get("permission_denials") or []]
            return [{"type": "done", "session_id": o.get("session_id"), "is_error": bool(o.get("is_error")),
                     "result": o.get("result", ""), "cost_usd": o.get("total_cost_usd"),
                     "duration_ms": o.get("duration_ms"), "num_turns": o.get("num_turns"), "denied": denials}]
        return []

    def summarize(self, name: str, inp: dict) -> str:
        if "file_path" in inp:
            return _short(str(inp["file_path"]), self.roots)
        if name == "Bash":
            return str(inp.get("command", ""))[:160]
        if name == "WebSearch":
            return str(inp.get("query", ""))
        if name == "WebFetch":
            return str(inp.get("url", ""))
        if name in ("Grep", "Glob"):
            return str(inp.get("pattern", ""))
        if name == "TodoWrite":
            todos = inp.get("todos") or []
            return f"{len(todos)} 项"
        if name == "Skill":
            return str(inp.get("skill") or inp.get("command") or "")
        for v in inp.values():
            if isinstance(v, str):
                return v[:120]
        return ""


def _preview(content) -> str:
    if isinstance(content, list):
        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    s = re.sub(r"\s+", " ", str(content or "")).strip()
    return s[:200]
