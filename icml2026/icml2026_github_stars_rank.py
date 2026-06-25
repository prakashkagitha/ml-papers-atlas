#!/usr/bin/env python3
"""Rank ICML 2026 papers by GitHub stars (a reachable impact proxy).

Why this exists: in network-restricted environments where citation APIs
(Semantic Scholar / OpenAlex / Crossref) are blocked but the GitHub API is
reachable, GitHub stars on a paper's official code repo are a usable,
quantitative proxy for adoption/impact on recent papers.

Pipeline:
  1. Search GitHub repositories for "ICML 2026" / "ICML2026", sorted by stars.
  2. For each candidate repo, fetch its README via the GitHub API and confirm
     the paper exists in the official ICML 2026 accepted list (outputs/
     icml2026_accepted.csv) by finding an official title verbatim in the README
     (falls back to a small manual alias map for repos renamed post-arXiv).
  3. Extract the arXiv id from the README, dedupe by paper, sort by stars.

Requires a GITHUB_TOKEN env var (any token raises the search rate limit).
This complements icml2026_citations.py; it does NOT replace a true citation
ranking. Stars favor code-shipping papers; theory/no-code papers are missed.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

TOKEN = os.environ.get("GITHUB_TOKEN", "")
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", re.I)


def gh(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}" if TOKEN else "",
            "Accept": "application/vnd.github+json",
            "User-Agent": "icml2026-stars",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def harvest_repos(min_stars: int) -> List[Dict[str, Any]]:
    repos: Dict[str, Dict[str, Any]] = {}
    for q in ["ICML+2026", "ICML2026"]:
        for page in range(1, 6):
            url = (
                f"https://api.github.com/search/repositories?q={q}"
                f"&sort=stars&order=desc&per_page=100&page={page}"
            )
            try:
                data = gh(url)
            except Exception:
                break
            items = data.get("items", [])
            if not items:
                break
            for r in items:
                repos[r["full_name"]] = {
                    "full_name": r["full_name"],
                    "stars": r["stargazers_count"],
                    "desc": r.get("description") or "",
                }
            time.sleep(1.0)
            if len(items) < 100:
                break
    out = [r for r in repos.values() if r["stars"] >= min_stars
           and any(t in r["desc"].lower() for t in ["icml 2026", "icml2026", "icml-2026", "icml'26"])]
    return sorted(out, key=lambda x: -x["stars"])


def load_official(csv_path: Path) -> List[tuple]:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    titles = [(norm(r["title"]), r) for r in rows if len(norm(r["title"])) >= 18]
    titles.sort(key=lambda x: -len(x[0]))  # match longest official title first
    return titles


def readme(full_name: str) -> str:
    try:
        d = gh(f"https://api.github.com/repos/{full_name}/readme")
        return base64.b64decode(d["content"]).decode("utf-8", "ignore")
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accepted", default="outputs/icml2026_accepted.csv")
    ap.add_argument("--out", default="outputs/icml2026_by_github_stars.csv")
    ap.add_argument("--min-stars", type=int, default=15)
    ap.add_argument("--top", type=int, default=120, help="how many top repos to README-verify")
    # repos renamed between arXiv and camera-ready: map repo -> distinctive official-title keyword
    ap.add_argument("--aliases", default="", help="optional JSON file {repo: official_title_substring}")
    args = ap.parse_args()

    official = load_official(Path(args.accepted))
    official_norm = {n: r for n, r in official}
    aliases = json.loads(Path(args.aliases).read_text()) if args.aliases else {}

    repos = harvest_repos(args.min_stars)
    print(f"Harvested {len(repos)} candidate repos (>= {args.min_stars} stars).")

    seen: Dict[str, Dict[str, Any]] = {}
    for repo in repos[: args.top]:
        rm = readme(repo["full_name"])
        nrm = norm(rm)
        m = ARXIV_RE.search(rm)
        arxiv = m.group(1) if m else ""
        match = None
        for n, r in official:                       # README contains the official title verbatim
            if n in nrm:
                match = r
                break
        if not match and repo["full_name"] in aliases:
            match = official_norm.get(norm(aliases[repo["full_name"]]))
        if not match:
            continue
        key = match["openreview_id"]
        cand = {
            "github_stars": repo["stars"],
            "github_repo": f"https://github.com/{repo['full_name']}",
            "title": match["title"],
            "openreview_id": key,
            "presentation_type": match["presentation_type"],
            "decision": match["decision"],
            "first_author": match["first_author"],
            "authors": match["authors"],
            "arxiv_id": arxiv,
            "arxiv_abs_url": f"https://arxiv.org/abs/{arxiv}" if arxiv else "",
            "arxiv_pdf_url": f"https://arxiv.org/pdf/{arxiv}" if arxiv else "",
            "icml_page_url": match["icml_page_url"],
            "openreview_url": match["openreview_url"],
        }
        if key not in seen or cand["github_stars"] > seen[key]["github_stars"]:
            seen[key] = cand
        time.sleep(0.12)

    ranked = sorted(seen.values(), key=lambda x: -x["github_stars"])
    for i, row in enumerate(ranked, 1):
        row["rank"] = i
    cols = ["rank", "github_stars", "title", "presentation_type", "decision",
            "first_author", "authors", "arxiv_id", "arxiv_abs_url", "arxiv_pdf_url",
            "github_repo", "icml_page_url", "openreview_url"]
    with Path(args.out).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(ranked)
    print(f"Wrote {len(ranked)} verified ICML 2026 papers ranked by stars to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
