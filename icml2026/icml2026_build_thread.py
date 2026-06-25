#!/usr/bin/env python3
"""Assemble the ICML 2026 "most-cited papers" X/Twitter thread.

Inputs:
  - outputs/icml2026_citations.csv     (citation-sorted, from icml2026_citations.py)
  - outputs/icml2026_top_papers_by_github_stars.csv  (stars cross-check; optional)
  - outputs/icml2026_author_posts.json (author X posts; optional, hand-verified)

Selection rule (from the task): the top 30 by citation count, extended to as
many as 50 as long as each paper ranked 31..50 still has > 25 citations.

Outputs:
  - outputs/icml2026_thread.md   one block per paper: rank, citations, stars,
    1-line blurb, arXiv / code / ICML / OpenReview links, the author X post to
    quote/RT, and the @handles to tag.
  - outputs/icml2026_thread_papers.csv   the selected papers as a flat CSV.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List


def to_int(s: Any) -> int:
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return -1


def one_line_blurb(abstract: str, limit: int = 200) -> str:
    abstract = re.sub(r"\s+", " ", abstract or "").strip()
    if not abstract:
        return ""
    # first sentence, else hard truncate
    m = re.search(r"(.+?[.!?])\s", abstract)
    s = m.group(1) if m and len(m.group(1)) >= 40 else abstract
    if len(s) > limit:
        s = s[: limit - 1].rsplit(" ", 1)[0] + "…"
    return s


def select_papers(rows: List[Dict[str, str]], base: int, extend_to: int, threshold: int) -> List[Dict[str, str]]:
    rows = sorted(rows, key=lambda r: to_int(r.get("citation_count")), reverse=True)
    selected = rows[:base]
    for r in rows[base:extend_to]:
        if to_int(r.get("citation_count")) > threshold:
            selected.append(r)
        else:
            break
    return selected


def load_stars(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if r.get("openreview_id"):
            out[r["openreview_id"]] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--citations", default="outputs/icml2026_citations.csv")
    ap.add_argument("--stars", default="outputs/icml2026_top_papers_by_github_stars.csv")
    ap.add_argument("--posts", default="outputs/icml2026_author_posts.json")
    ap.add_argument("--out-md", default="outputs/icml2026_thread.md")
    ap.add_argument("--out-csv", default="outputs/icml2026_thread_papers.csv")
    ap.add_argument("--base", type=int, default=30)
    ap.add_argument("--extend-to", type=int, default=50)
    ap.add_argument("--threshold", type=int, default=25)
    args = ap.parse_args()

    rows = list(csv.DictReader(Path(args.citations).open(encoding="utf-8")))
    stars = load_stars(Path(args.stars))
    posts = json.loads(Path(args.posts).read_text(encoding="utf-8")) if Path(args.posts).exists() else {}

    selected = select_papers(rows, args.base, args.extend_to, args.threshold)

    # flat CSV of the selected papers
    cols = ["rank", "title", "first_author", "citation_count", "github_stars",
            "arxiv_abs_url", "arxiv_pdf_url", "github_repo", "icml_page_url",
            "openreview_url", "author_post_url", "tag_handles"]
    with Path(args.out_csv).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(selected, 1):
            oid = r.get("openreview_id", "")
            srow = stars.get(oid, {})
            prow = posts.get(oid, {})
            w.writerow({
                "rank": i,
                "title": r.get("title", ""),
                "first_author": r.get("first_author", ""),
                "citation_count": r.get("citation_count", ""),
                "github_stars": srow.get("github_stars", ""),
                "arxiv_abs_url": r.get("arxiv_abs_url", ""),
                "arxiv_pdf_url": r.get("arxiv_pdf_url", ""),
                "github_repo": (prow.get("github_repo") or srow.get("github_repo") or ""),
                "icml_page_url": r.get("icml_page_url", ""),
                "openreview_url": r.get("openreview_url", ""),
                "author_post_url": prow.get("author_post_url", ""),
                "tag_handles": " ".join(prow.get("tag_handles", []) or []),
            })

    # markdown thread
    n = len(selected)
    lines: List[str] = []
    lines.append(f"# ICML 2026 — Top {n} most-cited accepted papers")
    lines.append("")
    lines.append(f"Citation counts via Semantic Scholar (snapshot). Top {args.base} by citations, "
                 f"extended to {n} (papers past #{args.base} kept only if > {args.threshold} citations). "
                 "GitHub stars shown as an adoption cross-check.")
    lines.append("")
    lines.append("> For each paper: the author/lab X post to **quote/RT** is in `author_post_url` "
                 "(blank = not yet verified). Tag the listed handles. Avoid RT-ing paper-sharing "
                 "accounts (@_akhaliq, @HuggingPapers, ...).")
    lines.append("")

    for i, r in enumerate(selected, 1):
        oid = r.get("openreview_id", "")
        srow = stars.get(oid, {})
        prow = posts.get(oid, {})
        cc = r.get("citation_count", "")
        stars_s = srow.get("github_stars", "")
        title = r.get("title", "")
        blurb = one_line_blurb(r.get("abstract", ""))
        meta = f"{cc} citations"
        if stars_s:
            meta += f" · {stars_s}★ GitHub"
        if r.get("is_oral") == "true":
            meta += " · Oral"
        elif r.get("is_spotlight") == "true":
            meta += " · Spotlight"

        links = []
        if r.get("arxiv_abs_url"):
            links.append(f"[arXiv]({r['arxiv_abs_url']})")
        repo = prow.get("github_repo") or srow.get("github_repo") or ""
        if repo:
            links.append(f"[code]({repo})")
        if r.get("icml_page_url"):
            links.append(f"[ICML]({r['icml_page_url']})")
        if r.get("openreview_url"):
            links.append(f"[OpenReview]({r['openreview_url']})")

        lines.append(f"## {i}. {title}")
        lines.append(f"*{r.get('first_author','')} et al. — {meta}*")
        lines.append("")
        if blurb:
            lines.append(blurb)
            lines.append("")
        if links:
            lines.append(" · ".join(links))
            lines.append("")
        post = prow.get("author_post_url", "")
        tag = " ".join(prow.get("tag_handles", []) or [])
        cand_urls = prow.get("candidate_post_urls", []) or []
        cand_handles = prow.get("candidate_handles", []) or []
        lines.append(f"**Author X post:** {post or '_TODO: verify author thread_'}")
        if tag:
            lines.append(f"**Tag:** {tag}")
        if not post and (cand_urls or cand_handles):
            if cand_urls:
                lines.append(f"  - candidate post(s): {', '.join(cand_urls[:3])}")
            if cand_handles:
                lines.append(f"  - candidate handle(s): {', '.join('@'+h for h in cand_handles[:5])}")
        lines.append("")
        lines.append("---")
        lines.append("")

    Path(args.out_md).write_text("\n".join(lines), encoding="utf-8")
    print(f"Selected {n} papers (base {args.base}, extend-to {args.extend_to}, >{args.threshold} cites).")
    print(f"Wrote {args.out_md} and {args.out_csv}.")
    cutoff = to_int(selected[-1].get("citation_count")) if selected else 0
    print(f"Citation range: #{1}={to_int(selected[0].get('citation_count'))} .. #{n}={cutoff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
