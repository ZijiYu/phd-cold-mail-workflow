"""In-memory stand-in for Google's OAuth and Gmail endpoints, used by tests."""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from datetime import datetime, timezone

ME = "applicant@example.com"


def _ts(d: str) -> int:
    return int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() * 1000)


def msg(mid, thread, frm, to, subject, when, body, labels=("INBOX",)):
    return {"id": mid, "threadId": thread, "from": frm, "to": to, "subject": subject,
            "internalDate": str(_ts(when)), "body": body, "labelIds": list(labels),
            "message_id": f"<{mid}@mail.example.com>"}


DEFAULT_MAILBOX = [
    # Priya: approved in the tracker, but the user already sent it from Gmail.
    msg("m1", "t1", ME, "praman@example.edu", "Fall 2027 PhD inquiry: stopping rules", "2026-10-26T14:00:00", "Dear Professor Raman, ...", ["SENT"]),
    # Marcus: sent 10/12, he replied 10/27.
    msg("m2", "t2", ME, "mhale@example.edu", "Fall 2027 PhD inquiry", "2026-10-12T13:00:00", "Dear Professor Hale, ...", ["SENT"]),
    msg("m3", "t2", "Marcus Hale <mhale@example.edu>", ME, "Re: Fall 2027 PhD inquiry", "2026-10-27T09:30:00",
        "Hi Lin, thanks for your note. I am planning to take one student this cycle. Could you send a short project summary?"),
    # Omar: auto-reply after the first email.
    msg("m4", "t3", ME, "osaid@example.edu", "Fall 2027 PhD inquiry", "2026-10-14T12:00:00", "Dear Professor Said, ...", ["SENT"]),
    msg("m5", "t3", "Omar Said <osaid@example.edu>", ME, "Automatic reply: Fall 2027 PhD inquiry", "2026-10-15T00:10:00",
        "I am out of the office until October 24 with limited email access."),
    # Ines: first email + one follow-up already sent.
    msg("m6", "t4", ME, "imoreau@example.edu", "Fall 2027 PhD inquiry", "2026-10-09T12:00:00", "Dear Professor Moreau, ...", ["SENT"]),
    msg("m7", "t4", ME, "imoreau@example.edu", "Re: Fall 2027 PhD inquiry", "2026-10-21T12:00:00", "Following up ...", ["SENT"]),
]


class FakeGoogle:
    def __init__(self, mailbox=None):
        self.mailbox = [dict(m) for m in (mailbox or DEFAULT_MAILBOX)]
        self.drafts: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.token_requests: list[dict] = []
        self.revoked = False

    # transport signature: (method, url, headers, body) -> (status, bytes)
    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        u = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(u.query)
        if u.netloc == "oauth2.googleapis.com" and u.path == "/token":
            form = dict(urllib.parse.parse_qsl(body.decode()))
            self.token_requests.append(form)
            if form["grant_type"] == "authorization_code" and form.get("code") != "good-code":
                return 400, json.dumps({"error": "invalid_grant"}).encode()
            return 200, json.dumps({"access_token": f"at-{len(self.token_requests)}", "refresh_token": "rt-1",
                                    "expires_in": 3600, "scope": "gmail.readonly gmail.compose"}).encode()
        if u.path == "/revoke":
            self.revoked = True
            return 200, b"{}"
        if not headers.get("Authorization", "").startswith("Bearer at-"):
            return 401, json.dumps({"error": {"message": "unauthorized"}}).encode()
        path = u.path.replace("/gmail/v1/users/me", "")
        if path == "/profile":
            return 200, json.dumps({"emailAddress": ME}).encode()
        if path == "/messages" and method == "GET":
            ids = [{"id": m["id"], "threadId": m["threadId"]} for m in self._search(q.get("q", [""])[0])]
            return 200, json.dumps({"messages": ids} if ids else {}).encode()
        m = re.fullmatch(r"/messages/(\w+)", path)
        if m:
            found = next((x for x in self.mailbox if x["id"] == m.group(1)), None)
            return (200, json.dumps(self._render(found, full=False)).encode()) if found else (404, b"{}")
        m = re.fullmatch(r"/threads/(\w+)", path)
        if m:
            msgs = [self._render(x, full=True) for x in self.mailbox if x["threadId"] == m.group(1)]
            return 200, json.dumps({"id": m.group(1), "messages": msgs}).encode()
        if path == "/drafts" and method == "POST":
            did = f"d{len(self.drafts) + 1}"
            self.drafts[did] = json.loads(body)
            return 200, json.dumps({"id": did, "message": {"id": f"dm-{did}"}}).encode()
        m = re.fullmatch(r"/drafts/(\w+)", path)
        if m and method == "PUT":
            if m.group(1) not in self.drafts:
                return 404, json.dumps({"error": {"message": "not found"}}).encode()
            self.drafts[m.group(1)] = json.loads(body)
            return 200, json.dumps({"id": m.group(1), "message": {"id": f"dm-{m.group(1)}"}}).encode()
        if "send" in path:
            raise AssertionError("the dashboard must never call a send endpoint")
        return 404, json.dumps({"error": {"message": f"unhandled {method} {path}"}}).encode()

    def _search(self, query: str):
        after = re.search(r"after:(\d+)", query)
        after_ms = int(after.group(1)) * 1000 if after else 0
        out = []
        for x in self.mailbox:
            if int(x["internalDate"]) < after_ms:
                continue
            if "mailer-daemon" in query:
                if "mailer-daemon" in x["from"].lower() and query.split()[-1] in x["body"]:
                    out.append(x)
                continue
            to = re.search(r"to:(\S+)", query)
            frm = re.search(r"from:(\S+)", query)
            if to and to.group(1) in x["to"] and ("in:sent" not in query or "SENT" in x["labelIds"]):
                out.append(x)
            elif frm and not to and frm.group(1) in x["from"]:
                out.append(x)
        return out

    @staticmethod
    def _render(x, full: bool):
        headers = [{"name": "From", "value": x["from"]}, {"name": "To", "value": x["to"]},
                   {"name": "Subject", "value": x["subject"]}, {"name": "Message-ID", "value": x["message_id"]}]
        payload = {"headers": headers, "mimeType": "text/plain"}
        if full:
            payload["body"] = {"data": base64.urlsafe_b64encode(x["body"].encode()).decode()}
        return {"id": x["id"], "threadId": x["threadId"], "internalDate": x["internalDate"],
                "snippet": x["body"][:100], "labelIds": x["labelIds"], "payload": payload}
