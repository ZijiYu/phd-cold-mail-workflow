#!/usr/bin/env python3
"""Validate an outreach tracker (targets.csv) and list what needs attention.

Usage:
    python scripts/check_tracker.py outreach/fall-2027/targets.csv
    python scripts/check_tracker.py targets.csv --programs programs.csv --today 2026-11-02

Checks status values, required fields per status, ISO dates, duplicates,
stale verification, per-program contact limits, and same-department sends
that are too close together. Prints a summary of counts and due follow-ups.

Exit code: 1 if any errors, else 0. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
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
    errors: list[str] = []
    warnings: list[str] = []

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing_cols:
        print(f"ERROR missing required columns: {', '.join(missing_cols)}")
        return 1

    # Programs
    programs: dict[str, dict[str, str]] = {}
    ppath = Path(args.programs) if args.programs else tpath.with_name("programs.csv")
    if ppath.is_file():
        _, prow = load_csv(ppath)
        programs = {r.get("program_id", ""): r for r in prow if r.get("program_id")}
    elif args.programs:
        warnings.append(f"programs file not found: {ppath}")

    ids = Counter(r["target_id"] for r in rows)
    for tid, n in ids.items():
        if not tid:
            errors.append("a row has an empty target_id")
        elif n > 1:
            errors.append(f"duplicate target_id {tid!r} ({n} rows)")
    emails = Counter(r.get("email", "").lower() for r in rows if r.get("email"))
    for em, n in emails.items():
        if n > 1:
            warnings.append(f"email {em!r} appears in {n} rows")

    due: list[tuple[date, str, str]] = []
    sends_by_dept: dict[tuple[str, str], list[tuple[date, str]]] = defaultdict(list)
    contacts_by_program: Counter[str] = Counter()

    for i, r in enumerate(rows, start=2):  # header is line 1
        tid = r["target_id"] or f"line {i}"
        status = r["status"]
        where = f"{tid}"

        if status not in STATUSES:
            errors.append(f"{where}: unknown status {status!r} (allowed: {', '.join(sorted(STATUSES))})")
            continue

        dates: dict[str, date | None] = {}
        for f in DATE_FIELDS:
            try:
                dates[f] = parse_date(r.get(f, ""))
            except ValueError:
                errors.append(f"{where}: {f} is not an ISO date: {r.get(f)!r}")
                dates[f] = None

        if status in {"approved"} | CONTACTED and not r.get("email"):
            errors.append(f"{where}: status {status} but no verified email")
        if status in CONTACTED and not dates["sent_at"]:
            errors.append(f"{where}: status {status} but sent_at is empty")
        if status in PRE_SEND and dates["sent_at"]:
            errors.append(f"{where}: status {status} but sent_at is set; update the status")
        if status == "closed" and not r.get("close_reason"):
            errors.append(f"{where}: closed without close_reason")
        if status == "blocked" and not r.get("next_action"):
            errors.append(f"{where}: blocked without a reason in next_action")
        if status in {"drafted", "approved"} and "draft_path" in columns and not r.get("draft_path"):
            warnings.append(f"{where}: status {status} but no draft_path")

        if dates["sent_at"] and dates["follow_up_due"] and dates["follow_up_due"] < dates["sent_at"]:
            errors.append(f"{where}: follow_up_due is before sent_at")
        if dates["sent_at"] and dates["sent_at"] > today:
            errors.append(f"{where}: sent_at is in the future")

        fu = r.get("follow_up_count", "")
        if fu:
            try:
                fu_n = int(fu)
                if fu_n > 2:
                    warnings.append(f"{where}: {fu_n} follow-ups sent; normally stop after two messages total")
            except ValueError:
                errors.append(f"{where}: follow_up_count is not an integer: {fu!r}")

        if status in PRE_SEND:
            if not dates["checked_on"]:
                warnings.append(f"{where}: never verified (checked_on empty)")
            elif (today - dates["checked_on"]).days > args.stale_days:
                warnings.append(f"{where}: verification is {(today - dates['checked_on']).days} days old; re-verify before sending")

        if status == "sent" and dates["follow_up_due"] and dates["follow_up_due"] <= today:
            due.append((dates["follow_up_due"], tid, r.get("sent_at", "")))

        pid = r.get("program_id", "")
        if pid:
            if programs and pid not in programs:
                warnings.append(f"{where}: program_id {pid!r} not found in {ppath.name}")
            if status in CONTACTED | {"approved"}:
                contacts_by_program[pid] += 1

        if dates["sent_at"]:
            key = (r["institution"].lower(), r.get("department", "").lower())
            sends_by_dept[key].append((dates["sent_at"], tid))

    for pid, n in contacts_by_program.items():
        limit = programs.get(pid, {}).get("max_contacts", "")
        if limit.isdigit() and n > int(limit):
            warnings.append(f"program {pid}: {n} professors approved/contacted, max_contacts is {limit}")

    gap = timedelta(days=args.min_gap_days)
    for (inst, dept), sends in sends_by_dept.items():
        sends.sort()
        for (d1, t1), (d2, t2) in zip(sends, sends[1:]):
            if d2 - d1 < gap:
                label = f"{inst}/{dept}" if dept else inst
                warnings.append(f"{label}: {t1} and {t2} were sent {(d2 - d1).days} day(s) apart")

    # Report
    counts = Counter(r["status"] for r in rows)
    print(f"Tracker: {tpath}  ({len(rows)} targets, evaluated {today.isoformat()})")
    print("Status counts: " + ", ".join(f"{s}={counts[s]}" for s in sorted(counts)))
    if due:
        print("Follow-ups due:")
        for d, tid, sent in sorted(due):
            print(f"  {tid}: due {d.isoformat()} (sent {sent})")
    else:
        print("Follow-ups due: none")
    for e in errors:
        print(f"ERROR {e}")
    for w in warnings:
        print(f"WARN  {w}")
    if not errors and not warnings:
        print("OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
