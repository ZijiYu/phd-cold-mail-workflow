"""Gmail sync: find sends and replies for tracked professors and propose
status changes. Nothing is applied automatically - the user confirms each
suggestion (references/campaign.md: "propose the status change")."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .gmail import AUTO_REPLY, BOUNCE_SENDERS, GmailClient, GmailError, _write_private, epoch
from .store import Store, StoreError, check_tracker

PRE_SEND = check_tracker.PRE_SEND
CONTACTED = check_tracker.CONTACTED


class GmailState:
    """Per-campaign sync results and Gmail draft ids, kept outside the repo."""

    def __init__(self, state_dir: Path):
        self.path = Path(state_dir) / "gmail_state.json"
        self._lock = threading.RLock()

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, campaign: str, target_id: str) -> dict:
        return self._load().get(campaign, {}).get(target_id, {})

    def campaign(self, campaign: str) -> dict:
        return self._load().get(campaign, {})

    def update(self, campaign: str, target_id: str, **fields) -> dict:
        with self._lock:
            data = self._load()
            rec = data.setdefault(campaign, {}).setdefault(target_id, {})
            for k, v in fields.items():
                if isinstance(v, dict) and isinstance(rec.get(k), dict):
                    rec[k].update(v)
                else:
                    rec[k] = v
            _write_private(self.path, data)
            return rec


def _suggest(row: dict, outgoing: list[dict], incoming: list[dict], bounces: list[dict], today: date) -> dict | None:
    status = row.get("status", "")
    out_sorted = sorted(outgoing, key=lambda m: m["timestamp"])

    if status in PRE_SEND and out_sorted:
        first, last = out_sorted[0], out_sorted[-1]
        sent = first["date"]
        return {
            "kind": "sent",
            "reason": f"Gmail 已发件中有 {len(out_sorted)} 封发给该教授的邮件，最早一封在 {sent}",
            "fields": {
                "status": "sent",
                "sent_at": sent,
                "last_contact_at": last["date"],
                "follow_up_count": str(len(out_sorted) - 1),
                "follow_up_due": (date.fromisoformat(last["date"]) + timedelta(days=10)).isoformat(),
            },
        }

    sent_at = row.get("sent_at", "")
    if not sent_at:
        return None
    since = epoch(sent_at)

    if status == "sent":
        if any(b["timestamp"] >= since for b in bounces):
            return {"kind": "bounced", "reason": "收到退信（mailer-daemon），请先核实邮箱地址", "fields": {"status": "bounced"}}
        new_in = [m for m in incoming if m["timestamp"] >= since]
        real = [m for m in new_in if not AUTO_REPLY.search(m["subject"] + " " + m["snippet"])]
        if real:
            m = real[0]
            return {
                "kind": "replied",
                "reason": f"{m['date']} 收到回信：{m['subject']}",
                "fields": {"status": "replied", "response_summary": m["snippet"][:160]},
            }
        if new_in:
            m = new_in[0]
            due = max(row.get("follow_up_due") or "", (date.fromisoformat(m["date"]) + timedelta(days=7)).isoformat())
            return {
                "kind": "auto_reply",
                "reason": f"{m['date']} 收到自动回复；跟进日期请按对方返回日期调整（默认顺延到 {due}）",
                "fields": {"follow_up_due": due, "response_summary": f"auto-reply {m['date']}: {m['snippet'][:100]}"},
            }
        later = [m for m in out_sorted if m["timestamp"] >= since]
        try:
            count = int(row.get("follow_up_count") or 0)
        except ValueError:
            count = 0
        if len(later) - 1 > count:
            last = later[-1]
            return {
                "kind": "followed_up",
                # Two messages total is the normal stopping point, so no further follow-up is scheduled.
                "reason": f"Gmail 显示你已经跟进了 {len(later) - 1} 次，最近一次在 {last['date']}",
                "fields": {
                    "follow_up_count": str(len(later) - 1),
                    "last_contact_at": last["date"],
                    "follow_up_due": "",
                },
            }
        return None

    if status in CONTACTED:
        last_contact = row.get("last_contact_at") or sent_at
        newer = [m for m in incoming if m["timestamp"] > epoch(last_contact) + 86399]
        if newer:
            m = newer[0]
            return {"kind": "new_message", "reason": f"{m['date']} 有新来信：{m['subject']}", "fields": {"response_summary": m["snippet"][:160]}}
    return None


def sync_campaign(store: Store, client: GmailClient, state: GmailState, campaign: str,
                  target_ids: list[str] | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    rows = store.targets(campaign)
    if target_ids:
        rows = [r for r in rows if r["target_id"] in set(target_ids)]
    results, errors = [], []
    for row in rows:
        email = row.get("email", "").strip()
        if not email or row.get("status") in {"closed", "blocked"}:
            continue
        try:
            outgoing = client.search(f"to:{email} in:sent", 10)
            q_in = f"from:{email}"
            if row.get("sent_at"):
                q_in += f" after:{epoch(row['sent_at']) - 86400}"
            incoming = client.search(q_in, 10)
            bounces = client.search(f"from:(mailer-daemon OR postmaster) {email}", 3) if (outgoing or row.get("sent_at")) else []
        except GmailError as e:
            if e.status in (400, 401, 409):
                raise
            errors.append({"target_id": row["target_id"], "error": str(e)})
            continue
        bounces = [b for b in bounces if BOUNCE_SENDERS.search(b["from"])]
        suggestion = _suggest(row, outgoing, incoming, bounces, today)
        rec = state.update(
            campaign, row["target_id"],
            checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            outgoing=outgoing[:5],
            incoming=incoming[:5],
            suggestion=suggestion,
        )
        results.append({"target_id": row["target_id"], "suggestion": rec["suggestion"],
                        "incoming": len(incoming), "outgoing": len(outgoing)})
    return {"checked": len(results), "suggestions": [r for r in results if r["suggestion"]],
            "results": results, "errors": errors}


def push_draft(store: Store, client: GmailClient, state: GmailState, campaign: str, target_id: str, name: str) -> dict:
    row = store.target(campaign, target_id)
    if not row.get("email"):
        raise StoreError("该教授还没有核实过的邮箱地址", 409)
    if not client.status()["can_draft"]:
        raise GmailError("当前授权没有“管理草稿”权限。请重新连接 Gmail，并勾选两项权限。", 409, "missing_scope")
    info = next((d for d in store.drafts(campaign, target_id) if d["name"] == name), None)
    if info is None:
        raise StoreError(f"draft {name!r} not found", 404)
    kind = info["kind"]
    status = row.get("status", "")
    if kind == "first" and status != "approved":
        raise StoreError("首封邮件需要先确认定稿（状态改为 approved）才能推送到 Gmail 草稿箱", 409)
    if kind != "first" and status not in CONTACTED:
        raise StoreError("跟进或回复草稿只能在首封邮件发出后推送", 409)

    check = store.check_draft(campaign, target_id, name)
    if check["errors"]:
        raise StoreError("草稿里还有未解决的问题：" + "；".join(check["errors"]), 422)
    d = store.read_draft(campaign, target_id, name)

    thread_id = in_reply_to = ""
    synced = state.get(campaign, target_id)
    pool = synced.get("incoming", []) if kind == "reply" else synced.get("outgoing", [])
    if kind != "first" and pool:
        latest = max(pool, key=lambda m: m["timestamp"])
        thread_id, in_reply_to = latest.get("thread_id", ""), latest.get("message_id_header", "")

    existing = (synced.get("drafts") or {}).get(name, {}).get("draft_id", "")
    res = client.save_draft(row["email"], d["subject"], d["body"], existing, thread_id, in_reply_to)
    state.update(campaign, target_id, drafts={name: {"draft_id": res["draft_id"],
                                                      "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}})
    res.update({
        "threaded": bool(thread_id),
        "warnings": check["warnings"],
        "gmail_url": "https://mail.google.com/mail/u/0/#drafts",
        "note": "草稿已存入 Gmail 草稿箱；请在 Gmail 里检查后手动发送，发送后在面板里同步或标记为已发送。",
    })
    if kind != "first" and not thread_id:
        res["note"] += " 没有找到之前的邮件线程（先点一次“同步 Gmail”），这封草稿不会挂在原线程下。"
    return res
