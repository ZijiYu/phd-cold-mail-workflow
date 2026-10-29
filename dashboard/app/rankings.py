"""School rankings shown next to each school (CSRankings, US).

The numbers live in rankings.json, rebuilt by dashboard/tools/build_rankings.py
from a CSRankings checkout. Institutions are matched by name: CSRankings uses
names such as "Univ. of California - Davis", while targets often say "UC Davis",
so names are normalized and a small alias table covers common short forms.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("rankings.json")

# Short names people actually write -> CSRankings institution name.
ALIASES = {
    "cmu": "Carnegie Mellon University",
    "uiuc": "Univ. of Illinois at Urbana-Champaign",
    "university of illinois urbana champaign": "Univ. of Illinois at Urbana-Champaign",
    "gatech": "Georgia Institute of Technology",
    "georgia tech": "Georgia Institute of Technology",
    "mit": "Massachusetts Inst. of Technology",
    "nyu": "New York University",
    "ut austin": "University of Texas at Austin",
    "ut dallas": "University of Texas at Dallas",
    "utd": "University of Texas at Dallas",
    "tamu": "Texas A&M University",
    "penn state": "Pennsylvania State University",
    "penn state university": "Pennsylvania State University",
    "ohio state": "Ohio State University",
    "the ohio state university": "Ohio State University",
    "osu": "Ohio State University",
    "upenn": "University of Pennsylvania",
    "rit": "Rochester Inst. of Technology",
    "suny buffalo": "University at Buffalo",
    "ub": "University at Buffalo",
    "sunny stony brook": "Stony Brook University",
    "suny stony brook": "Stony Brook University",
    "sbu": "Stony Brook University",
    "cwru": "Case Western Reserve University",
    "bu": "Boston University",
    "neu": "Northeastern University",
    "vt": "Virginia Tech",
    "virginia polytechnic institute and state university": "Virginia Tech",
    "uchicago": "University of Chicago",
    "ucsd": "Univ. of California - San Diego",
    "ucla": "Univ. of California - Los Angeles",
    "uc berkeley": "Univ. of California - Berkeley",
    "rutgers university new brunswick": "Rutgers University",
}
UC_CAMPUSES = ["Berkeley", "Davis", "Irvine", "Los Angeles", "Merced", "Riverside", "San Diego", "Santa Barbara", "Santa Cruz"]


def _norm(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)                      # "UIUC (Urbana)" -> "uiuc"
    s = re.sub(r"\buniv\b\.?", "university", s)
    s = re.sub(r"\binst\b\.?", "institute", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\b(the|at|of)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _table() -> tuple[dict, dict]:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}
    ranks = data.get("ranks", {})
    index = {_norm(k): k for k in ranks}
    for short, full in ALIASES.items():
        if full in ranks:
            index[_norm(short)] = full
    for campus in UC_CAMPUSES:
        full = f"Univ. of California - {campus}"
        if full in ranks:
            index[_norm(f"UC {campus}")] = full
            index[_norm(f"University of California {campus}")] = full
    meta = {k: v for k, v in data.items() if k != "ranks"}
    meta["ranks"] = ranks
    return index, meta


def meta() -> dict:
    _, m = _table()
    return {k: v for k, v in m.items() if k != "ranks"}


def lookup(institution: str) -> dict | None:
    """{"name", "cs", "ai"} for an institution, or None if it isn't ranked."""
    index, m = _table()
    if not institution or not index:
        return None
    full = index.get(_norm(institution))
    if not full:
        return None
    r = m["ranks"][full]
    return {"name": full, "cs": r.get("cs"), "ai": r.get("ai")}
