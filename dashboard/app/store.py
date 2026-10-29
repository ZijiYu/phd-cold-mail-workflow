"""File-backed campaign store.

The dashboard reads and writes the same files the skill produces, so the
agent and the dashboard always see one source of truth:

    <data_dir>/<campaign>/programs.csv
    <data_dir>/<campaign>/targets.csv
    <data_dir>/<campaign>/drafts/*.md

Writes are atomic (temp file + rename) and preserve unknown columns.

The draft and tracker checks are a vendored copy of the skill's
cold-email/scripts/ (see app/checks/), so the dashboard runs on its own;
dashboard/tests/test_checks_in_sync.py fails if the copies drift apart.
"""

from __future__ import annotations

import csv
import io
import os
import re
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import rankings
from .checks import check_draft, check_tracker

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
DEFAULT_TARGET_COLUMNS = [
    "target_id", "program_id", "professor", "institution", "department", "email",
    "homepage_url", "research_anchor", "applicant_anchor", "fit_rationale", "fit_score",
    "fit_components", "recruiting_confirmed", "recruiting_signals", "source_urls",
    "checked_on", "draft_path", "variant", "status", "sent_at", "follow_up_count",
    "last_contact_at", "follow_up_due", "response_summary", "close_reason", "next_action",
]
PROGRAM_COLUMNS = [
    "program_id", "institution", "department", "degree", "admission_model", "deadline", "deadline_tz",
    "can_name_faculty", "cross_dept_advising", "tier", "max_contacts", "source_urls", "checked_on",
]
REPLIED_LIKE = {"replied", "meeting_scheduled", "apply_and_mention", "redirected"}
DEFAULT_FOLLOW_UP_DAYS = 10


class StoreError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- drafts

def parse_draft(text: str) -> dict[str, str]:
    """Split a draft file into header / subject / body / notes.

    Format (see references/campaign.md): optional header lines, a
    "Subject:" line, the body, then a "---" line or "## " heading that
    starts the notes.
    """
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.strip().lower().startswith("subject:")), None)
    if idx is None:
        header, subject, after = [], "", lines
    else:
        header = lines[:idx]
        subject = lines[idx].strip()[len("subject:"):].strip()
        after = lines[idx + 1:]
    end = len(after)
    seen_text = False
    for j, l in enumerate(after):
        s = l.strip()
        if (s == "---" or s.startswith("## ")) and seen_text:
            end = j
            break
        if s:
            seen_text = True
    return {
        "header": "\n".join(header).strip("\n"),
        "subject": subject,
        "body": "\n".join(after[:end]).strip("\n"),
        "notes": "\n".join(after[end:]).strip("\n"),
    }


def compose_draft(header: str, subject: str, body: str, notes: str) -> str:
    parts = []
    if header.strip():
        parts.append(header.rstrip() + "\n")
    parts.append(f"Subject: {subject.strip()}\n")
    parts.append(body.strip("\n") + "\n")
    parts.append("\n" + (notes.strip("\n") if notes.strip() else "---") + "\n")
    return "\n".join(parts)


# ---------------------------------------------------------------- store

class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self._lock = threading.RLock()

    # campaigns ------------------------------------------------------
    def campaigns(self) -> list[dict]:
        out = []
        if not self.data_dir.is_dir():
            return out
        for d in sorted(self.data_dir.iterdir()):
            if d.is_dir() and (d / "targets.csv").is_file() and SAFE_ID.match(d.name):
                _, rows = check_tracker.load_csv(d / "targets.csv")
                out.append({"id": d.name, "targets": len(rows), "has_programs": (d / "programs.csv").is_file()})
        return out

    def create_campaign(self, campaign: str) -> dict:
        """Create an empty campaign folder with header-only CSVs."""
        if not SAFE_ID.match(campaign or ""):
            raise StoreError("申请季名称只能包含字母、数字、'.'、'_'、'-'，例如 fall-2027")
        with self._lock:
            d = (self.data_dir / campaign).resolve()
            if d.parent != self.data_dir:
                raise StoreError("invalid campaign id")
            if (d / "targets.csv").exists():
                raise StoreError(f"申请季 {campaign} 已经存在", 409)
            (d / "drafts").mkdir(parents=True, exist_ok=True)
            _atomic_write(d / "targets.csv", ",".join(DEFAULT_TARGET_COLUMNS) + "\n")
            if not (d / "programs.csv").exists():
                _atomic_write(d / "programs.csv", ",".join(PROGRAM_COLUMNS) + "\n")
        return {"id": campaign, "targets": 0, "has_programs": True}

    def campaign_dir(self, campaign: str) -> Path:
        if not SAFE_ID.match(campaign or ""):
            raise StoreError("invalid campaign id", 400)
        d = (self.data_dir / campaign).resolve()
        if d.parent != self.data_dir or not (d / "targets.csv").is_file():
            raise StoreError(f"campaign {campaign!r} not found", 404)
        return d

    # programs -------------------------------------------------------
    def programs(self, campaign: str) -> list[dict[str, str]]:
        p = self.campaign_dir(campaign) / "programs.csv"
        if not p.is_file():
            return []
        return check_tracker.load_csv(p)[1]

    # targets --------------------------------------------------------
    def _load_targets(self, campaign: str) -> tuple[list[str], list[dict[str, str]]]:
        return check_tracker.load_csv(self.campaign_dir(campaign) / "targets.csv")

    def _save_targets(self, campaign: str, columns: list[str], rows: list[dict[str, str]]) -> None:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
        _atomic_write(self.campaign_dir(campaign) / "targets.csv", buf.getvalue())

    def targets(self, campaign: str, status: str = "", program_id: str = "", q: str = "") -> list[dict[str, str]]:
        _, rows = self._load_targets(campaign)
        if status:
            wanted = set(status.split(","))
            rows = [r for r in rows if r.get("status") in wanted]
        if program_id:
            rows = [r for r in rows if r.get("program_id") == program_id]
        if q:
            ql = q.lower()
            rows = [r for r in rows if any(ql in (r.get(k) or "").lower() for k in ("professor", "institution", "department", "research_anchor", "email"))]
        return rows

    def target(self, campaign: str, target_id: str) -> dict[str, str]:
        _, rows = self._load_targets(campaign)
        for r in rows:
            if r.get("target_id") == target_id:
                return r
        raise StoreError(f"target {target_id!r} not found", 404)

    def create_target(self, campaign: str, fields: dict[str, str]) -> dict[str, str]:
        with self._lock:
            columns, rows = self._load_targets(campaign)
            tid = (fields.get("target_id") or "").strip()
            if not SAFE_ID.match(tid):
                raise StoreError("target_id must be a slug of letters, digits, '.', '_' or '-'")
            if any(r.get("target_id") == tid for r in rows):
                raise StoreError(f"target {tid!r} already exists", 409)
            for req in ("professor", "institution"):
                if not (fields.get(req) or "").strip():
                    raise StoreError(f"{req} is required")
            row = {k: str(v).strip() for k, v in fields.items() if v is not None}
            row.setdefault("status", "researching")
            self._validate_status_change({}, row)
            columns = self._merge_columns(columns, row)
            rows.append(row)
            self._save_targets(campaign, columns, rows)
            return row

    def update_target(self, campaign: str, target_id: str, fields: dict[str, str], today: date | None = None) -> dict[str, str]:
        if "target_id" in fields and fields["target_id"] != target_id:
            raise StoreError("target_id cannot be changed")
        with self._lock:
            columns, rows = self._load_targets(campaign)
            row = next((r for r in rows if r.get("target_id") == target_id), None)
            if row is None:
                raise StoreError(f"target {target_id!r} not found", 404)
            new = dict(row)
            new.update({k: ("" if v is None else str(v).strip()) for k, v in fields.items()})
            self._apply_defaults(row, new, today or date.today())
            self._validate_status_change(row, new)
            row.clear()
            row.update(new)
            columns = self._merge_columns(columns, new)
            self._save_targets(campaign, columns, rows)
            return row

    @staticmethod
    def _merge_columns(columns: list[str], row: dict[str, str]) -> list[str]:
        if not columns:
            columns = list(DEFAULT_TARGET_COLUMNS)
        extra = [k for k in row if k not in columns]
        return columns + extra

    @staticmethod
    def _apply_defaults(old: dict[str, str], new: dict[str, str], today: date) -> None:
        """Fill the bookkeeping fields a status change implies, if the caller left them blank."""
        if new.get("status") == "sent" and old.get("status") != "sent":
            if not new.get("sent_at"):
                new["sent_at"] = today.isoformat()
            if not new.get("last_contact_at"):
                new["last_contact_at"] = new["sent_at"]
            if not new.get("follow_up_count"):
                new["follow_up_count"] = "0"
            if not new.get("follow_up_due"):
                sent = date.fromisoformat(new["sent_at"][:10])
                new["follow_up_due"] = (sent + timedelta(days=DEFAULT_FOLLOW_UP_DAYS)).isoformat()

    @staticmethod
    def _validate_status_change(old: dict[str, str], new: dict[str, str]) -> None:
        status = new.get("status", "")
        if status not in check_tracker.STATUSES:
            raise StoreError(f"unknown status {status!r}")
        if status == "closed" and not new.get("close_reason"):
            raise StoreError("close_reason is required to close a target")
        if status == "blocked" and not new.get("next_action"):
            raise StoreError("next_action (the blocking reason) is required for blocked")
        if status in {"approved"} | check_tracker.CONTACTED and not new.get("email"):
            raise StoreError(f"a verified email is required for status {status}")
        for f in check_tracker.DATE_FIELDS:
            try:
                check_tracker.parse_date(new.get(f, ""))
            except ValueError:
                raise StoreError(f"{f} must be an ISO date (YYYY-MM-DD)")

    # analysis -------------------------------------------------------
    def summary(self, campaign: str, today: date | None = None) -> dict:
        columns, rows = self._load_targets(campaign)
        programs = {p["program_id"]: p for p in self.programs(campaign) if p.get("program_id")}
        res = check_tracker.analyze(columns, rows, programs, today or date.today())
        sent_like = [r for r in rows if r.get("status") in check_tracker.CONTACTED or r.get("status") == "closed" and r.get("sent_at")]
        replied = [r for r in rows if r.get("status") in REPLIED_LIKE or (r.get("status") == "closed" and r.get("response_summary"))]

        schools: dict[str, dict] = {}
        for r in rows:
            inst = r.get("institution") or "(unknown)"
            s = schools.setdefault(inst, {"institution": inst, "programs": set(), "total": 0, "contacted": 0, "replied": 0})
            s["total"] += 1
            if r.get("program_id"):
                s["programs"].add(r["program_id"])
            if r.get("sent_at"):
                s["contacted"] += 1
            if r.get("status") in REPLIED_LIKE:
                s["replied"] += 1
        school_list = []
        for s in schools.values():
            progs = [programs.get(p, {"program_id": p}) for p in sorted(s["programs"])]
            deadlines = sorted(p.get("deadline", "") for p in progs if p.get("deadline"))
            tiers = sorted({p.get("tier", "") for p in progs if p.get("tier")})
            school_list.append({**s, "programs": [p.get("program_id") for p in progs], "deadline": deadlines[0] if deadlines else "",
                                "tiers": tiers, "rank": rankings.lookup(s["institution"])})
        # earliest deadline first; without deadlines, schools with replies come first
        school_list.sort(key=lambda s: (s["deadline"] or "9999", -s["replied"], s["institution"]))

        out = res.to_dict()
        out.update({
            "campaign": campaign,
            "total": len(rows),
            "contacted": len(sent_like),
            "replied": len(replied),
            "reply_rate": round(len(replied) / len(sent_like), 3) if sent_like else None,
            "schools": school_list,
            "rankings": rankings.meta(),
            "programs": list(programs.values()),
        })
        return out

    def issues_for(self, campaign: str, target_id: str) -> list[dict]:
        s = self.summary(campaign)
        return [i for i in s["issues"] if i["target_id"] == target_id]

    # drafts ---------------------------------------------------------
    def _drafts_dir(self, campaign: str) -> Path:
        return self.campaign_dir(campaign) / "drafts"

    def _draft_stem(self, row: dict[str, str]) -> str:
        if row.get("draft_path"):
            return Path(row["draft_path"]).stem
        return row["target_id"]

    def _draft_paths(self, campaign: str, target_id: str) -> dict[str, tuple[Path, bool]]:
        """name -> (path, is_primary). Primary is the row's draft_path; the
        rest are files in drafts/ named <stem>--<kind>-<n>.md."""
        row = self.target(campaign, target_id)
        ddir = self._drafts_dir(campaign)
        found: dict[str, tuple[Path, bool]] = {}
        if row.get("draft_path"):
            p = self._resolve_in_campaign(campaign, row["draft_path"])
            if p.is_file():
                found[p.name] = (p, True)
        stem = self._draft_stem(row)
        if ddir.is_dir():
            for p in sorted(ddir.glob("*.md")):
                if p.name not in found and (p.stem == stem or p.stem.startswith(stem + "--")):
                    found[p.name] = (p, False)
        return found

    def drafts(self, campaign: str, target_id: str) -> list[dict]:
        out = []
        for name, (_, primary) in self._draft_paths(campaign, target_id).items():
            kind = "followup" if "--followup" in name else ("reply" if "--reply" in name else "first")
            out.append({"name": name, "kind": kind, "primary": primary})
        return out

    def _resolve_in_campaign(self, campaign: str, rel: str) -> Path:
        base = self.campaign_dir(campaign)
        p = (base / rel).resolve()
        if base not in p.parents:
            raise StoreError("draft path escapes the campaign folder", 400)
        return p

    def _draft_file(self, campaign: str, target_id: str, name: str) -> Path:
        paths = self._draft_paths(campaign, target_id)
        if name not in paths:
            raise StoreError(f"draft {name!r} not found for {target_id}", 404)
        return paths[name][0]

    def read_draft(self, campaign: str, target_id: str, name: str) -> dict[str, str]:
        p = self._draft_file(campaign, target_id, name)
        parsed = parse_draft(p.read_text(encoding="utf-8"))
        parsed["name"] = name
        parsed["modified_at"] = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        return parsed

    def write_draft(self, campaign: str, target_id: str, name: str, subject: str, body: str) -> dict[str, str]:
        with self._lock:
            p = self._draft_file(campaign, target_id, name)
            cur = parse_draft(p.read_text(encoding="utf-8"))
            _atomic_write(p, compose_draft(cur["header"], subject, body, cur["notes"]))
            return self.read_draft(campaign, target_id, name)

    def create_draft(self, campaign: str, target_id: str, kind: str = "first") -> dict[str, str]:
        if kind not in {"first", "followup", "reply"}:
            raise StoreError("kind must be first, followup, or reply")
        with self._lock:
            row = self.target(campaign, target_id)
            existing = self.drafts(campaign, target_id)
            ddir = self._drafts_dir(campaign)
            stem = self._draft_stem(row)
            first = next((d for d in existing if d["kind"] == "first"), None)
            if kind == "first":
                if first:
                    raise StoreError("a first-contact draft already exists", 409)
                name = f"{stem}.md"
                subject = ""
            else:
                n = 1 + sum(1 for d in existing if d["kind"] == kind)
                name = f"{stem}--{kind}-{n}.md"
                base_subject = self.read_draft(campaign, target_id, first["name"])["subject"] if first else ""
                subject = f"Re: {base_subject}" if base_subject and not base_subject.lower().startswith("re:") else base_subject
            header = f"<!-- target: {row['target_id']} | to: {row.get('email', '')} | kind: {kind} -->"
            _atomic_write(ddir / name, compose_draft(header, subject, "", "---\n## Notes\n"))
            if kind == "first" and not row.get("draft_path"):
                self.update_target(campaign, target_id, {"draft_path": f"drafts/{name}"})
            return self.read_draft(campaign, target_id, name)

    def approval_blockers(self, campaign: str, target_id: str) -> list[str]:
        """Reasons the first-contact draft cannot be marked approved yet."""
        first = next((d for d in self.drafts(campaign, target_id) if d["kind"] == "first"), None)
        if first is None:
            return ["还没有首封草稿"]
        res = self.check_draft(campaign, target_id, first["name"])
        return res["errors"]

    def check_draft(self, campaign: str, target_id: str, name: str, kind: str | None = None) -> dict:
        d = self.read_draft(campaign, target_id, name)
        if kind is None:
            kind = {"followup": "followup", "reply": "other"}.get(next(x["kind"] for x in self.drafts(campaign, target_id) if x["name"] == name), "first")
        text = f"Subject: {d['subject']}\n{d['body']}\n"
        rep = check_draft.check(name, text, kind)
        words = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-.]*", d["body"]))
        return {"kind": kind, "errors": rep.errors, "warnings": rep.warnings, "words": words}
