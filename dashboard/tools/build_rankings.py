"""Rebuild dashboard/app/rankings.json from a CSRankings checkout.

    git clone --depth 1 https://github.com/emeryberger/CSrankings /tmp/csr
    python dashboard/tools/build_rankings.py /tmp/csr

Reproduces csrankings.org's default view for the US: every top-tier venue
(next-tier venues off), the last ten years, a smoothed geometric mean of
adjusted paper counts over the selected areas, rounded to one decimal, and
competition ranking for ties ("1, 2, 2, 4"). Two rankings are written:

  cs  all 27 areas (the csrankings.org front page)
  ai  the AI group only: AI, Vision, ML, NLP, Web+IR
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


def parse_tables(js: str) -> tuple[dict[str, str], set[str]]:
    def block(name: str) -> str:
        m = re.search(rf"CSRankings\.{name}\s*=\s*\{{(.*?)\}};", js, re.S)
        if not m:
            raise SystemExit(f"could not find CSRankings.{name} in csrankings.js")
        return m.group(1)

    parent = dict(re.findall(r"'([\w-]+)'\s*:\s*'([\w-]+)'", block("parentMap")))
    next_tier = set(re.findall(r"'([\w-]+)'\s*:\s*true", block("nextTier")))
    return parent, next_tier


def rank(scores: dict[str, float]) -> dict[str, int]:
    rounded = {k: round(10 * v) / 10 for k, v in scores.items() if v > 1.0}
    out, prev, pos = {}, None, 0
    for i, (k, v) in enumerate(sorted(rounded.items(), key=lambda kv: (-kv[1], kv[0])), start=1):
        if v != prev:
            pos, prev = i, v
        out[k] = pos
    return out


def main(src: Path, dest: Path, end_year: int) -> None:
    js_path = src / "csrankings.js"
    if not js_path.exists():
        js_path = src / "csrankings.ts"
    parent, next_tier = parse_tables(js_path.read_text(encoding="utf-8"))
    parents = sorted(set(parent.values()))
    ai_group = ["ai", "vision", "mlmining", "nlp", "inforet"]
    start_year = end_year - 10

    country = {}
    with open(src / "institutions.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            country[row["institution"]] = row["countryabbrv"]

    counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    with open(src / "generated-author-info.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            venue = row["area"]
            if venue not in parent or venue in next_tier:
                continue
            if country.get(row["dept"]) != "us":
                continue
            if not start_year <= int(row["year"]) <= end_year:
                continue
            counts[row["dept"]][parent[venue]] += float(row["adjustedcount"])

    def geo(areas: list[str]) -> dict[str, float]:
        out = {}
        for dept, by_area in counts.items():
            p = 1.0
            for a in areas:
                p *= by_area.get(a, 0.0) + 1.0
            out[dept] = p ** (1 / len(areas))
        return out

    cs, ai = rank(geo(parents)), rank(geo(ai_group))
    try:
        commit = subprocess.run(["git", "-C", str(src), "log", "-1", "--format=%h %cs"],
                                capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = ""
    data = {
        "source": "CSRankings (csrankings.org), US, top-tier venues",
        "years": f"{start_year}-{end_year}",
        "data_version": commit,
        "built_on": date.today().isoformat(),
        "areas": {"cs": "all areas", "ai": "AI + Vision + ML + NLP + Web/IR"},
        "ranks": {d: {"cs": cs.get(d), "ai": ai.get(d)} for d in sorted(set(cs) | set(ai))},
    }
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=0, sort_keys=False) + "\n", encoding="utf-8")
    top = sorted(cs.items(), key=lambda kv: kv[1])[:8]
    print(f"wrote {dest} ({len(data['ranks'])} US institutions, {start_year}-{end_year}, {commit})")
    print("top:", ", ".join(f"{r}. {d}" for d, r in top))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    here = Path(__file__).resolve().parents[1]
    end = int(sys.argv[2]) if len(sys.argv) > 2 else date.today().year
    main(Path(sys.argv[1]), here / "app" / "rankings.json", end)
