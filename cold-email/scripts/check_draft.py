#!/usr/bin/env python3
"""Deterministic checks for outreach email drafts.

Usage:
    python scripts/check_draft.py drafts/*.md
    python scripts/check_draft.py --type followup drafts/lakeview--whitfield-followup.md
    cat draft.txt | python scripts/check_draft.py -

Draft format: the first line starting with "Subject:" is the subject. The body
runs from the next line until a line that is exactly "---", a markdown heading
("## ..."), or the end of the file. Anything after that (evidence bridge,
sources, notes) is ignored.

Exit code: 1 if any file has errors (or warnings with --strict), else 0.
Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Phrases that read as templated or LLM-generated in academic outreach.
STOCK_PHRASES = [
    "hope this email finds you well",
    "hope this message finds you well",
    "i am writing to express",
    "deeply impressed",
    "deeply passionate",
    "greatly impressed",
    "extremely impressed",
    "truly inspired",
    "i was fascinated",
    "resonates with me",
    "resonated with me",
    "resonate deeply",
    "align perfectly",
    "aligns perfectly",
    "perfectly aligned",
    "perfect fit",
    "great fit for your",
    "ideal candidate",
    "groundbreaking",
    "pioneering work",
    "outstanding work",
    "renowned",
    "world-class",
    "cutting-edge",
    "state-of-the-art",
    "significant improvement",
    "delve",
    "tapestry",
    "i am confident that",
    "it would be an honor",
    "it would be a privilege",
    "i look forward to hearing from you at your earliest convenience",
    "esteemed",
]

GENERIC_SUBJECTS = [
    "prospective phd student",
    "prospective student",
    "phd inquiry",
    "phd application",
    "inquiry",
    "hello",
    "research opportunity",
]

ADMISSION_ASKS = [
    r"consider me for admission",
    r"admit me",
    r"accept me (?:as|into)",
    r"offer me (?:a|an) (?:position|admission)",
]

PLACEHOLDER_PATTERNS = [
    (r"\[[^\]\n]{1,60}\](?!\()", "bracket placeholder"),  # [Name] but not [text](url)
    (r"\{\{[^}]*\}\}", "template variable"),
    (r"<(?:name|professor|university|paper|topic|lab|date|title)[^>\n]*>", "angle-bracket placeholder"),
    (r"\b(?:TODO|TBD|XXX|FIXME)\b", "to-do marker"),
    (r"\?\?\?", "unresolved ???"),
]

LIMITS = {
    "first": (100, 250),
    "followup": (25, 130),
    "thankyou": (40, 180),
    "other": (20, 300),
}


@dataclass
class Report:
    name: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def split_draft(text: str) -> tuple[str | None, str]:
    lines = text.splitlines()
    subject = None
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("subject:"):
            subject = stripped[len("subject:"):].strip()
            start = i + 1
            break
    if start is None:
        start = 0
    body_lines = []
    for line in lines[start:]:
        s = line.strip()
        if s == "---" or s.startswith("## ") or s == "```":
            if body_lines and any(b.strip() for b in body_lines):
                break
            continue  # skip a leading fence/rule
        body_lines.append(line)
    return subject, "\n".join(body_lines).strip()


def check(name: str, text: str, kind: str) -> Report:
    rep = Report(name)
    subject, body = split_draft(text)
    lower_body = body.lower()

    # Subject
    if subject is None:
        rep.errors.append("no 'Subject:' line found")
    elif not subject:
        rep.errors.append("subject is empty")
    else:
        subj_core = re.sub(r"^(re|fwd?):\s*", "", subject.lower()).strip(" -–—:")
        if subj_core in GENERIC_SUBJECTS or len(subj_core.split()) < 3:
            rep.warnings.append(f"subject carries little information: {subject!r}")
        if kind == "first" and not re.search(r"\b(20\d\d|fall|spring|autumn|winter)\b", subject, re.I):
            rep.warnings.append("first-contact subject does not mention the application cycle")

    # Body length
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-.]*", body)
    lo, hi = LIMITS[kind]
    n = len(words)
    if n == 0:
        rep.errors.append("body is empty")
    elif n < lo:
        rep.warnings.append(f"body is short for a {kind} email: {n} words (expected {lo}-{hi})")
    elif n > hi:
        rep.warnings.append(f"body is long for a {kind} email: {n} words (expected {lo}-{hi})")

    # Placeholders (subject + body)
    full = f"{subject or ''}\n{body}"
    for pattern, label in PLACEHOLDER_PATTERNS:
        for m in re.finditer(pattern, full, re.I if "TODO" not in pattern else 0):
            rep.errors.append(f"{label}: {m.group(0)!r}")

    # Greeting
    first_line = next((l.strip() for l in body.splitlines() if l.strip()), "")
    if re.match(r"^(dear|hi|hello)\s+(professor|prof\.?|sir|madam|sir/madam|sir or madam)\s*[,:]?$", first_line, re.I):
        rep.warnings.append(f"greeting has no name: {first_line!r}")

    # Stock phrases
    hits = [p for p in STOCK_PHRASES if p in lower_body]
    if hits:
        rep.warnings.append("stock or inflated phrasing: " + ", ".join(repr(h) for h in hits))

    # Admission asks
    for pattern in ADMISSION_ASKS:
        m = re.search(pattern, lower_body)
        if m:
            rep.warnings.append(f"asks for admission rather than advising availability: {m.group(0)!r}")

    # Punctuation tone
    if body.count("!") >= 2:
        rep.warnings.append(f"{body.count('!')} exclamation marks")

    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="draft files, or - for stdin")
    ap.add_argument("--type", choices=sorted(LIMITS), default="first", help="email type for length limits (default: first)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args(argv)

    failed = False
    for f in args.files:
        if f == "-":
            name, text = "<stdin>", sys.stdin.read()
        else:
            p = Path(f)
            if not p.is_file():
                print(f"{f}: ERROR file not found")
                failed = True
                continue
            name, text = f, p.read_text(encoding="utf-8")
        rep = check(name, text, args.type)
        if not rep.errors and not rep.warnings:
            print(f"{name}: OK")
            continue
        for e in rep.errors:
            print(f"{name}: ERROR {e}")
        for w in rep.warnings:
            print(f"{name}: WARN  {w}")
        if rep.errors or (args.strict and rep.warnings):
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
