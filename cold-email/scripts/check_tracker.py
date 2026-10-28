#!/usr/bin/env python3
"""Validate an outreach tracker (targets.csv) and list what needs attention.

Usage:
    python scripts/check_tracker.py outreach/fall-2027/targets.csv
    python scripts/check_tracker.py targets.csv --programs programs.csv --today 2026-11-02

Checks status values, required fields per status, ISO dates, duplicates,
stale verification, per-program contact limits, and same-department sends
that are too close together. Prints a summary of counts and due follow-ups.

`analyze()` returns the same results as data, for the dashboard.

Exit code: 1 if any errors, else 0. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

STATUSES = {
    "researching",
    "drafted",
    "approved",
    "sent",
    "replied",
    "meeting_scheduled",
    "apply_and_mention",
    "redirected",
    "bounced",
    "blocked",
    "closed",
}
CONTACTED = {"sent", "replied", "meeting_scheduled", "apply_and_mention", "redirected", "bounced"}
PRE_SEND = {"researching", "drafted", "approved"}
DATE_FIELDS = ["checked_on", "sent_at", "last_contact_at", "follow_up_due"]
REQUIRED_COLUMNS = ["target_id", "professor", "institution", "status"]


@dataclass
class Issue:
    level: str  # "error" | "warning"
    message: str
    target_id: str = ""

    def text(self) -> str:
        return f"{self.target_id}: {self.message}" if self.target_id else self.message


@dataclass
class Analysis:
    today: str
    counts: dict[str, int] = field(default_factory=dict)
    due: list[dict[str, str]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    fatal: bool = False

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["error_count"] = len(self.errors)
        d["warning_count"] = len(self.warnings)
        return d


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    return date.fromisoformat(value[:10])


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in reader]
        return [c.strip() for c in (reader.fieldnames or [])], rows


def analyze(
    columns: list[str],
    rows: list[dict[str, str]],
    programs: dict[str, dict[str, str]] | None = None,
    today: date | None = None,
    stale_days: int = 30,
    min_gap_days: int = 3,
    programs_name: str = "programs.csv",
) -> Analysis:
    today = today or date.today()
    programs = programs or {}
    res = Analysis(today=today.isoformat())

    def err(msg: str, tid: str = "") -> None:
        res.issues.append(Issue("error", msg, tid))

    def warn(msg: str, tid: str = "") -> None:
        res.issues.append(Issue("warning", msg, tid))

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing_cols:
        err(f"missing required columns: {', '.join(missing_cols)}")
        res.fatal = True
        return res

    ids = Counter(r.get("target_id", "") for r in rows)
    for tid, n in ids.items():
        if not tid:
            err("a row has an empty target_id")
        elif n > 1:
            err(f"duplicate target_id {tid!r} ({n} rows)")
    emails = Counter(r.get("email", "").lower() for r in rows if r.get("email"))
    for em, n in emails.items():
        if n > 1:
            warn(f"email {em!r} appears in {n} rows")

    sends_by_dept: dict[tuple[str, str], list[tuple[date, str]]] = defaultdict(list)
    contacts_by_program: Counter = Counter()

    for i, r in enumerate(rows, start=2):  # header is line 1
        tid = r.get("target_id") or f"line {i}"
        status = r.get("status", "")

        if status not in STATUSES:
            err(f"unknown status {status!r} (allowed: {', '.join(sorted(STATUSES))})", tid)
            continue

        dates: dict[str, date | None] = {}
        for f in DATE_FIELDS:
            try:
                dates[f] = parse_date(r.get(f, ""))
            except ValueError:
                err(f"{f} is not an ISO date: {r.get(f)!r}", tid)
                dates[f] = None

        if status in {"approved"} | CONTACTED and not r.get("email"):
            err(f"status {status} but no verified email", tid)
        if status in CONTACTED and not dates["sent_at"]:
            err(f"status {status} but sent_at is empty", tid)
        if status in PRE_SEND and dates["sent_at"]:
            err(f"status {status} but sent_at is set; update the status", tid)
        if status == "closed" and not r.get("close_reason"):
            err("closed without close_reason", tid)
        if status == "blocked" and not r.get("next_action"):
            err("blocked without a reason in next_action", tid)
        if status in {"drafted", "approved"} and "draft_path" in columns and not r.get("draft_path"):
            warn(f"status {status} but no draft_path", tid)

        if dates["sent_at"] and dates["follow_up_due"] and dates["follow_up_due"] < dates["sent_at"]:
            err("follow_up_due is before sent_at", tid)
        if dates["sent_at"] and dates["sent_at"] > today:
            err("sent_at is in the future", tid)

        fu = r.get("follow_up_count", "")
        if fu:
            try:
                fu_n = int(fu)
                if fu_n > 2:
                    warn(f"{fu_n} follow-ups sent; normally stop after two messages total", tid)
            except ValueError:
                err(f"follow_up_count is not an integer: {fu!r}", tid)

        if status in PRE_SEND:
            if not dates["checked_on"]:
                warn("never verified (checked_on empty)", tid)
            elif (today - dates["checked_on"]).days > stale_days:
                warn(f"verification is {(today - dates['checked_on']).days} days old; re-verify before sending", tid)

        if status == "sent" and dates["follow_up_due"] and dates["follow_up_due"] <= today:
            res.due.append({"target_id": tid, "due": dates["follow_up_due"].isoformat(), "sent_at": r.get("sent_at", "")})

        pid = r.get("program_id", "")
        if pid:
            if programs and pid not in programs:
                warn(f"program_id {pid!r} not found in {programs_name}", tid)
            if status in CONTACTED | {"approved"}:
                contacts_by_program[pid] += 1

        if dates["sent_at"]:
            key = (r.get("institution", "").lower(), r.get("department", "").lower())
            sends_by_dept[key].append((dates["sent_at"], tid))

    for pid, n in contacts_by_program.items():
        limit = programs.get(pid, {}).get("max_contacts", "")
        if limit.isdigit() and n > int(limit):
            warn(f"program {pid}: {n} professors approved/contacted, max_contacts is {limit}")

    gap = timedelta(days=min_gap_days)
    for (inst, dept), sends in sends_by_dept.items():
        sends.sort()
        for (d1, t1), (d2, t2) in zip(sends, sends[1:]):
            if d2 - d1 < gap:
                label = f"{inst}/{dept}" if dept else inst
                warn(f"{label}: {t1} and {t2} were sent {(d2 - d1).days} day(s) apart")

    res.counts = dict(sorted(Counter(r.get("status", "") for r in rows).items()))
    res.due.sort(key=lambda d: d["due"])
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", help="path to targets.csv")
    ap.add_argument("--programs", help="path to programs.csv (default: programs.csv next to targets, if present)")
    ap.add_argument("--today", help="ISO date to evaluate against (default: today)")
    ap.add_argument("--stale-days", type=int, default=30, help="re-verify unsent targets older than this (default 30)")
    ap.add_argument("--min-gap-days", type=int, default=3, help="min days between sends to one department (default 3)")
    args = ap.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else date.today()
    tpath = Path(args.targets)
    if not tpath.is_file():
        print(f"ERROR targets file not found: {tpath}")
        return 1

    columns, rows = load_csv(tpath)
    programs: dict[str, dict[str, str]] = {}
    pre_issues: list[Issue] = []
    ppath = Path(args.programs) if args.programs else tpath.with_name("programs.csv")
    if ppath.is_file():
        _, prow = load_csv(ppath)
        programs = {r.get("program_id", ""): r for r in prow if r.get("program_id")}
    elif args.programs:
        pre_issues.append(Issue("warning", f"programs file not found: {ppath}"))

    res = analyze(columns, rows, programs, today, args.stale_days, args.min_gap_days, ppath.name)
    res.issues = pre_issues + res.issues
    if res.fatal:
        for e in res.errors:
            print(f"ERROR {e.text()}")
        return 1

    print(f"Tracker: {tpath}  ({len(rows)} targets, evaluated {today.isoformat()})")
    print("Status counts: " + ", ".join(f"{s}={n}" for s, n in res.counts.items()))
    if res.due:
        print("Follow-ups due:")
        for d in res.due:
            print(f"  {d['target_id']}: due {d['due']} (sent {d['sent_at']})")
    else:
        print("Follow-ups due: none")
    for e in res.errors:
        print(f"ERROR {e.text()}")
    for w in res.warnings:
        print(f"WARN  {w.text()}")
    if not res.issues:
        print("OK")
    return 1 if res.errors else 0


if __name__ == "__main__":
    sys.exit(main())
