#!/usr/bin/env python3
"""Generate the ml-papers-atlas top-level README as an ICML 2026 insights blog.

Reuses the thread's selection + interspersing so the README's ranked list
matches outputs/icml2026_thread.md exactly. Produces a README with a table of
contents, the two ranking images, collapsible per-paper sections (clickable
links + author X posts), methodology, and a corpus/download section.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from icml2026_build_thread import (
    one_line_blurb, clean_latex, select_papers, star_ranked_oids,
    intersperse_stars, to_int, load_stars,
)

CIT = "outputs/icml2026_citations.csv"
STARS = "outputs/icml2026_top_papers_by_github_stars.csv"
POSTS = "outputs/icml2026_author_posts.json"
LIVE = "outputs/_live_stars.json"
REPO = "https://github.com/prakashkagitha/ml-papers-atlas"
BLOB = REPO + "/blob/main/icml2026"            # adjust to default branch on merge
FLAT = "https://flatgithub.com/prakashkagitha/ml-papers-atlas?filename=icml2026/outputs"


def fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "—"


def paper_entry(i: int, r: Dict[str, str], posts: Dict[str, Any], stars_csv: Dict[str, Any]) -> List[str]:
    oid = r.get("openreview_id", "")
    p = posts.get(oid, {})
    s = stars_csv.get(oid, {})
    title = clean_latex(r.get("title", ""))
    url = r.get("arxiv_abs_url") or r.get("icml_page_url") or r.get("openreview_url") or ""
    cc = r.get("citation_count", "")
    stars = p.get("github_stars")
    if stars is None and s.get("github_stars"):
        stars = s["github_stars"]
    repo = p.get("github_repo") or s.get("github_repo") or ""
    post = p.get("author_post_url", "")
    handles = p.get("tag_handles") or p.get("candidate_handles") or []

    badge = f"**{fmt(cc)}** citations"
    if stars:
        badge += f" · **{fmt(stars)}**★"
    if r.get("is_oral") == "true":
        badge += " · Oral"
    elif r.get("is_spotlight") == "true":
        badge += " · Spotlight"

    head = f"**{i}. [{title}]({url})**" if url else f"**{i}. {title}**"
    out = [f"{head}  ", f"{r.get('first_author','')} et al. · {badge}  "]
    blurb = one_line_blurb(r.get("abstract", "")).replace("*", "")
    if blurb:
        out.append(f"{blurb}  ")
    links = []
    if r.get("arxiv_abs_url"):
        links.append(f"[arXiv]({r['arxiv_abs_url']})")
    if repo:
        links.append(f"[code]({repo})")
    if r.get("icml_page_url"):
        links.append(f"[ICML]({r['icml_page_url']})")
    if post:
        links.append(f"[X post]({post})")
    if handles:
        links.append("tag " + " ".join(f"[@{h}](https://x.com/{h})" for h in handles[:3]))
    if links:
        out.append(" · ".join(links))
    out.append("")
    return out


def section(rows, posts, stars_csv, lo, hi, summary, open_=False) -> List[str]:
    op = " open" if open_ else ""
    block = [f"<details{op}>", f"<summary><b>{summary}</b></summary>", ""]
    for i, r in enumerate(rows, 1):
        if lo <= i <= hi:
            block += paper_entry(i, r, posts, stars_csv)
    block += ["</details>", ""]
    return block


def main() -> int:
    rows = list(csv.DictReader(Path(CIT).open(encoding="utf-8")))
    posts = json.loads(Path(POSTS).read_text(encoding="utf-8"))
    stars_csv = load_stars(Path(STARS))

    excluded = {oid for oid, v in posts.items() if v.get("exclude")}
    rows = [r for r in rows if r.get("openreview_id") not in excluded]

    selected = select_papers(rows, 30, 50, 25)
    star_ids = star_ranked_oids(posts, Path(STARS), Path(LIVE), 5)
    selected = intersperse_stars(selected, rows, star_ids, 10)

    # headline stats
    cc_ints = [to_int(r.get("citation_count")) for r in rows]
    matched = sum(1 for r in rows if r.get("citation_source") == "semanticscholar")
    n_total = 6343
    n_gt0 = sum(1 for c in cc_ints if c > 0)
    n_gt25 = sum(1 for c in cc_ints if c > 25)
    n_gt100 = sum(1 for c in cc_ints if c > 100)
    top = selected[0]

    L: List[str] = []
    L.append("# ICML 2026 — Most-Cited & Most-Adopted Papers")
    L.append("")
    L.append("> An open, reproducible look at which **ICML 2026** papers are landing — by "
             "academic **citations** (Semantic Scholar) and by code **adoption** (GitHub stars). "
             "Part of [**ml-papers-atlas**](" + REPO + "): mapping ML-conference papers to arXiv, "
             "citations, and author/lab connections.")
    L.append("")
    L.append(f"**{n_total:,}** accepted main-conference papers · **{matched:,}** matched to Semantic "
             f"Scholar · **{n_gt0:,}** with ≥1 citation · **{n_gt25:,}** with >25 · **{n_gt100:,}** with >100. "
             "Citation counts are a snapshot and skew toward papers that hit arXiv early; most ICML 2026 "
             "papers had near-zero citations at snapshot time. Star counts are a live GitHub snapshot.")
    L.append("")
    L.append("## Contents")
    L.append("")
    L.append("- [📈 Top 20 by citations](#-top-20-by-citations)")
    L.append("- [⭐ Top 20 by GitHub stars](#-top-20-by-github-stars)")
    L.append("- [📋 The ranked list — top 50 papers](#-the-ranked-list--top-50-papers)")
    L.append("- [🔬 Methodology & caveats](#-methodology--caveats)")
    L.append("- [📦 Full corpus & downloads](#-full-corpus--downloads)")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 📈 Top 20 by citations")
    L.append("")
    L.append("![Top 20 by citations](icml2026/outputs/icml2026_top20_by_citations.png)")
    L.append("")
    L.append("## ⭐ Top 20 by GitHub stars")
    L.append("")
    L.append("An adoption proxy that surfaces hot, code-shipping papers a citation count misses "
             "(the two lists barely overlap — citation leaders are established benchmarks/methods; "
             "star leaders are recent code-heavy releases).")
    L.append("")
    L.append("![Top 20 by GitHub stars](icml2026/outputs/icml2026_top20_by_stars.png)")
    L.append("")
    L.append("## 📋 The ranked list — top 50 papers")
    L.append("")
    L.append(f"Primarily ranked by citations (top 30, extended to 50 while > 25 citations); the "
             f"**top 5 by GitHub stars are woven into the first 10**, so the head reflects both "
             f"impact and adoption. Each entry links arXiv · code · ICML · the author's X post, and "
             f"lists the X handle(s) to tag. Same data as the "
             f"[copy-paste thread](icml2026/outputs/icml2026_thread_plaintext.txt).")
    L.append("")
    L += section(selected, posts, stars_csv, 1, 10, "#1–#10 — headline papers (citations × stars)", open_=True)
    L += section(selected, posts, stars_csv, 11, 25, "#11–#25 — click to expand")
    L += section(selected, posts, stars_csv, 26, 50, "#26–#50 — click to expand")
    L.append("---")
    L.append("")
    L.append("## 🔬 Methodology & caveats")
    L.append("")
    L.append("<details>")
    L.append("<summary><b>How this was built (and what to trust)</b></summary>")
    L.append("")
    L.append("- **Papers:** the ICML 2026 virtual-site metadata (6,343 unique main-conference "
             "papers; 6,184 Poster + 159 Oral; 536 spotlights).")
    L.append("- **Citations + arXiv ids:** [Semantic Scholar Graph API](https://www.semanticscholar.org/product/api), "
             "one title search per paper (match + citation + arXiv id). ~66% match; the rest are too "
             "new to be indexed (≈0 citations). OpenAlex is no longer practical as a bulk engine "
             "(metered at ~100 requests/day as of mid-2026).")
    L.append("- **GitHub stars:** live GitHub API snapshot for each paper's official repo, found via "
             "title search + an *\"ICML 2026\"* repo harvest. Aggregator/awesome-list repos are filtered out.")
    L.append("- **Author X posts:** discovered per paper (repo READMEs + targeted search) and "
             "hand-verified; only `x.com` handles are used (never GitHub usernames). Paper-sharing "
             "accounts (@_akhaliq, @HuggingPapers, …) are excluded.")
    L.append("- **Caveats:** citation counts are a snapshot; star coverage is limited to papers whose "
             "repo we could resolve; a few author posts are best-effort (marked as candidate handles).")
    L.append("")
    L.append("</details>")
    L.append("")
    L.append("## 📦 Full corpus & downloads")
    L.append("")
    L.append("Everything is in [`icml2026/outputs/`](icml2026/outputs/). GitHub renders CSVs as a "
             "sortable, searchable table — click to browse, hit **Raw** to download, or open in a "
             "spreadsheet viewer.")
    L.append("")
    L.append("| File | Rows | What |")
    L.append("|------|-----:|------|")
    L.append(f"| [icml2026_accepted.csv](icml2026/outputs/icml2026_accepted.csv) "
             f"([view]({FLAT}/icml2026_accepted.csv)) | {n_total:,} | every accepted paper + metadata |")
    L.append(f"| [icml2026_citations.csv](icml2026/outputs/icml2026_citations.csv) "
             f"([view]({FLAT}/icml2026_citations.csv)) | {n_total:,} | + Semantic Scholar citations, arXiv ids, sorted |")
    L.append(f"| [icml2026_top_papers_by_github_stars.csv](icml2026/outputs/icml2026_top_papers_by_github_stars.csv) "
             f"([view]({FLAT}/icml2026_top_papers_by_github_stars.csv)) | 101 | GitHub-stars cross-check |")
    L.append(f"| [icml2026_thread.md](icml2026/outputs/icml2026_thread.md) · "
             f"[.txt](icml2026/outputs/icml2026_thread_plaintext.txt) | 50 | the thread (markdown + X copy-paste) |")
    L.append("")
    L.append("Reproduce end-to-end from [`icml2026/`](icml2026/) — see its "
             "[README](icml2026/README.md) for the pipeline.")
    L.append("")
    L.append("---")
    L.append(f"*Snapshot generated from the ICML 2026 corpus. Top paper: **{clean_latex(top['title'])}** "
             f"({fmt(top['citation_count'])} citations). Built with "
             f"[Claude Code](https://claude.com/claude-code).*")
    L.append("")

    Path("outputs/_repo_readme.md").write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote outputs/_repo_readme.md ({len(L)} lines, {len(selected)} papers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
