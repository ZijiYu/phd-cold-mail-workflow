"""School rankings shown next to each school: U.S. News Best Computer Science
Schools (graduate), read from rankings.json.

U.S. News names look like "University of California--Davis" or
"Stony Brook University--SUNY", while targets usually say "UC Davis" or
"Stony Brook University", so names are normalized and a small alias table
covers common short forms. To cover a new school, add it to rankings.json
under its U.S. News name (and an alias here if people write it differently).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("rankings.json")

# Short names people write -> U.S. News name.
ALIASES = {
    "cmu": "Carnegie Mellon University",
    "mit": "Massachusetts Institute of Technology",
    "uiuc": "University of Illinois--Urbana-Champaign",
    "university of illinois urbana champaign": "University of Illinois--Urbana-Champaign",
    "gatech": "Georgia Institute of Technology",
    "georgia tech": "Georgia Institute of Technology",
    "nyu": "New York University",
    "ut austin": "University of Texas--Austin",
    "ut dallas": "University of Texas--Dallas",
    "utd": "University of Texas--Dallas",
    "ut arlington": "University of Texas--Arlington",
    "tamu": "Texas A&M University--College Station",
    "penn state": "Pennsylvania State University--University Park",
    "penn state university": "Pennsylvania State University--University Park",
    "ohio state": "Ohio State University",
    "the ohio state university": "Ohio State University",
    "osu": "Ohio State University",
    "upenn": "University of Pennsylvania",
    "rit": "Rochester Institute of Technology",
    "rutgers": "Rutgers University--New Brunswick",
    "rutgers university": "Rutgers University--New Brunswick",
    "suny buffalo": "University at Buffalo--SUNY",
    "ub": "University at Buffalo--SUNY",
    "suny stony brook": "Stony Brook University--SUNY",
    "sbu": "Stony Brook University--SUNY",
    "cwru": "Case Western Reserve University",
    "bu": "Boston University",
    "neu": "Northeastern University",
    "vt": "Virginia Tech",
    "virginia polytechnic institute and state university": "Virginia Tech",
    "uchicago": "University of Chicago",
    "uic": "University of Illinois Chicago",
    "usc": "University of Southern California",
    "umd": "University of Maryland--College Park",
    "uw": "University of Washington",
    "caltech": "California Institute of Technology",
}
UC_CAMPUSES = ["Berkeley", "Davis", "Irvine", "Los Angeles", "Merced", "Riverside", "San Diego", "Santa Barbara", "Santa Cruz"]


def _norm(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)                      # "UIUC (Urbana)" -> "uiuc"
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\b(the|at|of)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _load() -> tuple[dict, dict, dict]:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}, {}
    ranks: dict = data.get("ranks", {})
    index = {_norm(k): k for k in ranks}
    # "Stony Brook University--SUNY" is also findable as "Stony Brook University",
    # when that short form names only one ranked school.
    bases = Counter(_norm(k.split("--")[0]) for k in ranks if "--" in k)
    for k in ranks:
        if "--" in k:
            b = _norm(k.split("--")[0])
            if bases[b] == 1:
                index.setdefault(b, k)
    for short, full in ALIASES.items():
        if full in ranks:
            index[_norm(short)] = full
    for campus in UC_CAMPUSES:
        full = f"University of California--{campus}"
        if full in ranks:
            index[_norm(f"UC {campus}")] = full
    return index, ranks, {k: v for k, v in data.items() if k != "ranks"}


def meta() -> dict:
    return dict(_load()[2])


def lookup(institution: str) -> dict | None:
    """{"name": U.S. News name, "rank": int} for an institution, or None if not in the table."""
    index, ranks, _ = _load()
    if not institution or not index:
        return None
    full = index.get(_norm(institution))
    return {"name": full, "rank": ranks[full]} if full else None
