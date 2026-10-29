"""Minimal Gmail client: OAuth (loopback + PKCE), reply search, threads, drafts.

Scopes requested:
  - gmail.readonly : find replies and sent messages, read threads
  - gmail.compose  : create and update drafts

Google has no drafts-only scope; gmail.compose technically also permits
sending. This client never calls a send endpoint - sending stays a manual
click in Gmail, as the skill requires.

Uses only the standard library. The HTTP transport is injectable for tests.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Callable

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me"

# transport(method, url, headers, body_bytes) -> (status, response_bytes)
Transport = Callable[[str, str, dict, "bytes | None"], "tuple[int, bytes]"]


class GmailError(Exception):
    def __init__(self, message: str, status: int = 502, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


CLIENT_ID_RE = re.compile(r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$")
READ_SCOPE, COMPOSE_SCOPE = SCOPES


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise GmailError(f"cannot reach Google: {e.reason}", 502)


def _write_private(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class GmailClient:
    def __init__(self, state_dir: Path, transport: Transport = urllib_transport):
        self.state_dir = Path(state_dir)
        self.client_file = self.state_dir / "google_client.json"
        self.token_file = self.state_dir / "google_token.json"
        self.reauth_file = self.state_dir / "google_reauth.json"
        self.transport = transport
        self._pending: dict[str, dict] = {}  # oauth state -> {verifier, redirect_uri, created}

    # ------------------------------------------------------------ config
    def client_config(self) -> dict | None:
        if not self.client_file.is_file():
            return None
        raw = json.loads(self.client_file.read_text(encoding="utf-8"))
        cfg = raw.get("installed") or raw.get("web") or raw
        if not cfg.get("client_id") or not cfg.get("client_secret"):
            return None
        return cfg

    def save_client(self, downloaded: dict | None = None, client_id: str = "", client_secret: str = "") -> dict:
        """Store the OAuth client from the downloaded JSON or from pasted values."""
        if downloaded:
            if "web" in downloaded and "installed" not in downloaded:
                raise GmailError("这个凭据是“Web 应用”类型。请在 Google Cloud 里新建一个“桌面应用”（Desktop app）类型的客户端，再下载它的 JSON。", 400, "client_type")
            cfg = downloaded.get("installed") or downloaded
            client_id = str(cfg.get("client_id", ""))
            client_secret = str(cfg.get("client_secret", ""))
        client_id, client_secret = client_id.strip(), client_secret.strip()
        if not CLIENT_ID_RE.match(client_id):
            raise GmailError("客户端 ID 格式不对，应该形如 123456789-xxxx.apps.googleusercontent.com。", 400, "client_id")
        if not client_secret:
            raise GmailError("缺少客户端密钥（client secret）。下载的 JSON 文件里有，或在客户端详情页复制。", 400, "client_secret")
        old = self.client_config()
        if old and old.get("client_id") != client_id:
            self.token_file.unlink(missing_ok=True)  # tokens belong to the old client
        _write_private(self.client_file, {"installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": AUTH_URL,
            "token_uri": TOKEN_URL,
        }})
        return self.status()

    def remove_client(self) -> None:
        self.disconnect()
        self.client_file.unlink(missing_ok=True)
        self.reauth_file.unlink(missing_ok=True)

    def _token(self) -> dict | None:
        if not self.token_file.is_file():
            return None
        return json.loads(self.token_file.read_text(encoding="utf-8"))

    def _reauth(self) -> dict:
        if not self.reauth_file.is_file():
            return {}
        try:
            return json.loads(self.reauth_file.read_text(encoding="utf-8"))
        except ValueError:
            return {}

    def status(self) -> dict:
        tok = self._token()
        connected = bool(tok and tok.get("refresh_token"))
        scopes = (tok or {}).get("scope", "").split()
        reauth = {} if connected else self._reauth()
        return {
            "configured": self.client_config() is not None,
            "connected": connected,
            "email": (tok or {}).get("email", ""),
            "scopes": scopes,
            "can_read": connected and READ_SCOPE in scopes,
            "can_draft": connected and COMPOSE_SCOPE in scopes,
            "reauth": bool(reauth),
            "reauth_email": reauth.get("email", ""),
            "client_file": str(self.client_file),
        }

    # ------------------------------------------------------------ oauth
    def start_auth(self, redirect_uri: str) -> str:
        cfg = self.client_config()
        if not cfg:
            raise GmailError("还没有设置 Google OAuth 客户端，先完成“连接 Gmail”里的设置步骤。", 400, "not_configured")
        now = time.time()
        self._pending = {k: v for k, v in self._pending.items() if now - v["created"] < 600}
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(64)
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        self._pending[state] = {"verifier": verifier, "redirect_uri": redirect_uri, "created": now}
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        hint = (self._token() or {}).get("email") or self._reauth().get("email")
        if hint:
            params["login_hint"] = hint  # Google pre-selects the account
        return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    def finish_auth(self, code: str, state: str) -> dict:
        pending = self._pending.pop(state, None)
        if not pending or time.time() - pending["created"] > 600:
            raise GmailError("OAuth state is invalid or expired; start the connection again", 400)
        cfg = self.client_config()
        if not cfg:
            raise GmailError("Google OAuth client not configured", 400)
        tok = self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": pending["redirect_uri"],
            "code_verifier": pending["verifier"],
        })
        if not tok.get("refresh_token"):
            raise GmailError("Google 没有返回长期授权。请到 Google 账号的“第三方应用访问权限”里移除这个应用，再连接一次。", 400, "no_refresh_token")
        granted = tok.get("scope", "").split()
        if READ_SCOPE not in granted:
            raise GmailError("授权时没有勾选“查看你的电子邮件”，面板无法识别回信。请重新连接，并勾选两项权限。", 400, "missing_scope")
        _write_private(self.token_file, tok)
        profile = self.api("GET", "/profile")
        tok["email"] = profile.get("emailAddress", "")
        _write_private(self.token_file, tok)
        self.reauth_file.unlink(missing_ok=True)
        return self.status()

    def disconnect(self) -> None:
        tok = self._token()
        if tok and tok.get("refresh_token"):
            try:
                self.transport("POST", REVOKE_URL, {"Content-Type": "application/x-www-form-urlencoded"},
                               urllib.parse.urlencode({"token": tok["refresh_token"]}).encode())
            except GmailError:
                pass  # still remove the local token
        self.token_file.unlink(missing_ok=True)

    def _token_request(self, form: dict) -> dict:
        status, body = self.transport("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"},
                                      urllib.parse.urlencode(form).encode())
        data = json.loads(body or b"{}")
        if status != 200:
            raise GmailError(f"token request failed: {data.get('error_description') or data.get('error') or status}",
                             400, str(data.get("error", "")))
        data["expires_at"] = time.time() + int(data.get("expires_in", 3600)) - 60
        return data

    def _access_token(self) -> str:
        tok = self._token()
        if not tok or not tok.get("refresh_token"):
            raise GmailError("Gmail is not connected", 409)
        if tok.get("access_token") and tok.get("expires_at", 0) > time.time():
            return tok["access_token"]
        cfg = self.client_config()
        if not cfg:
            raise GmailError("Google OAuth client not configured", 400, "not_configured")
        try:
            fresh = self._token_request({
                "grant_type": "refresh_token",
                "refresh_token": tok["refresh_token"],
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
            })
        except GmailError as e:
            if e.code != "invalid_grant":
                raise
            # Revoked, password changed, or the 7-day limit of a Testing-mode app.
            _write_private(self.reauth_file, {"email": tok.get("email", ""), "at": int(time.time())})
            self.token_file.unlink(missing_ok=True)
            raise GmailError("Gmail 授权已失效（测试模式下 Google 授权 7 天后过期）。点右上角“重新连接 Gmail”即可。",
                             401, "gmail_reauth")
        tok.update({k: v for k, v in fresh.items() if k != "refresh_token" or v})
        _write_private(self.token_file, tok)
        return tok["access_token"]

    # ------------------------------------------------------------ api
    def api(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = API + path + (f"?{urllib.parse.urlencode(params, doseq=True)}" if params else "")
        headers = {"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        status, resp = self.transport(method, url, headers, data)
        payload = json.loads(resp or b"{}") if resp else {}
        if status >= 400:
            msg = (payload.get("error") or {}).get("message") if isinstance(payload.get("error"), dict) else payload.get("error")
            raise GmailError(f"Gmail API {status}: {msg or 'request failed'}", 404 if status == 404 else 502)
        return payload

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        listing = self.api("GET", "/messages", {"q": query, "maxResults": max_results})
        out = []
        for m in listing.get("messages", []):
            msg = self.api("GET", f"/messages/{m['id']}", {
                "format": "metadata",
                "metadataHeaders": ["From", "To", "Subject", "Date", "Message-ID"],
            })
            out.append(_summarize(msg))
        out.sort(key=lambda m: m["timestamp"], reverse=True)
        return out

    def thread(self, thread_id: str) -> list[dict]:
        t = self.api("GET", f"/threads/{thread_id}", {"format": "full"})
        msgs = []
        for m in t.get("messages", []):
            s = _summarize(m)
            s["body"] = _plain_text(m.get("payload", {}))
            msgs.append(s)
        msgs.sort(key=lambda m: m["timestamp"])
        return msgs

    def save_draft(self, to: str, subject: str, body: str, draft_id: str = "",
                   thread_id: str = "", in_reply_to: str = "") -> dict:
        """Create a draft, or update `draft_id` if it still exists. Never sends."""
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(body)
        message: dict = {"raw": _b64url(msg.as_bytes())}
        if thread_id:
            message["threadId"] = thread_id
        if draft_id:
            try:
                d = self.api("PUT", f"/drafts/{draft_id}", body={"id": draft_id, "message": message})
                return {"draft_id": d.get("id", draft_id), "message_id": d.get("message", {}).get("id", ""), "updated": True}
            except GmailError as e:
                if e.status != 404:
                    raise
        d = self.api("POST", "/drafts", body={"message": message})
        return {"draft_id": d.get("id", ""), "message_id": d.get("message", {}).get("id", ""), "updated": False}


# ---------------------------------------------------------------- helpers

def _headers(msg: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _summarize(msg: dict) -> dict:
    h = _headers(msg)
    ts = int(msg.get("internalDate", "0")) / 1000
    if not ts and h.get("date"):
        try:
            ts = parsedate_to_datetime(h["date"]).timestamp()
        except (TypeError, ValueError):
            ts = 0
    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "from": h.get("from", ""),
        "to": h.get("to", ""),
        "subject": h.get("subject", ""),
        "message_id_header": h.get("message-id", ""),
        "date": datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else "",
        "timestamp": ts,
        "snippet": unescape(msg.get("snippet", "")),
        "labels": msg.get("labelIds", []),
    }


def _plain_text(payload: dict) -> str:
    def walk(p: dict) -> tuple[str, str]:
        mime = p.get("mimeType", "")
        data = p.get("body", {}).get("data")
        if data and mime == "text/plain":
            return _b64url_decode(data).decode("utf-8", "replace"), ""
        if data and mime == "text/html":
            return "", _b64url_decode(data).decode("utf-8", "replace")
        plain, html = "", ""
        for part in p.get("parts", []) or []:
            a, b = walk(part)
            plain = plain or a
            html = html or b
        return plain, html

    plain, html = walk(payload)
    if plain:
        return plain.strip()
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(re.sub(r"\n{3,}", "\n\n", text)).strip()


AUTO_REPLY = re.compile(r"(out of (the )?office|automatic reply|auto[- ]?reply|away from|on leave|vacation|自动回复)", re.I)
BOUNCE_SENDERS = re.compile(r"(mailer-daemon|postmaster)", re.I)


def epoch(d: str) -> int:
    return int(datetime.combine(date.fromisoformat(d[:10]), datetime.min.time(), tzinfo=timezone.utc).timestamp())
