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


def one_line_blurb(abstract: str, min_sentences: int = 2, max_sentences: int = 3,
                   soft_limit: int = 340, hard_limit: int = 520) -> str:
    """A clean 2-3 sentence TL;DR — always ends on a full sentence, never '…'."""
    text = re.sub(r"\s+", " ", abstract or "").strip()
    text = text.replace("$", "")  # drop stray inline-math markers
    if not text:
        return ""
    # split on sentence boundaries, but not on decimals / abbreviations
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(\"“])", text) if s.strip()]
    out: List[str] = []
    total = 0
    for s in sentences:
        if out:
            projected = total + len(s)
            if len(out) >= max_sentences:
                break
            if projected > hard_limit:
                break
            if len(out) >= min_sentences and projected > soft_limit:
                break
        out.append(s)
        total += len(s) + 1
    return " ".join(out).strip()


_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
          "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ",
          "sigma": "σ", "tau": "τ", "phi": "φ", "psi": "ψ", "omega": "ω"}
_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def clean_latex(t: str) -> str:
    t = t or ""
    for name, ch in _GREEK.items():
        t = re.sub(rf"\\{name}\b", ch, t)
    t = re.sub(r"\^\{?(\d+)\}?", lambda m: m.group(1).translate(_SUP), t)
    t = re.sub(r"_\{?(\d+)\}?", lambda m: m.group(1).translate(_SUB), t)
    t = t.replace("$", "").replace("\\", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", t).strip()


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


def star_ranked_oids(posts: Dict[str, Any], stars_csv: Path, live_path: Path, top: int) -> List[str]:
    """openreview_ids of the top-`top` papers by live GitHub stars, ranked over
    the union of author-discovered repos and the ICML-2026 star harvest."""
    live = json.loads(live_path.read_text()) if live_path.exists() else {}
    oid_repo: Dict[str, str] = {}
    for oid, v in posts.items():
        if v.get("github_repo"):
            oid_repo[oid] = v["github_repo"].rsplit("github.com/", 1)[-1].strip("/")
    if stars_csv.exists():
        for r in csv.DictReader(stars_csv.open(encoding="utf-8")):
            oid = r.get("openreview_id") or ""
            if not oid:
                m = re.search(r"id=([^&\s]+)", r.get("openreview_url", "") or "")
                oid = m.group(1) if m else ""
            if oid and r.get("github_repo"):
                oid_repo.setdefault(oid, r["github_repo"].rsplit("github.com/", 1)[-1].strip("/"))
    scored = [(live.get(f) or 0, oid) for oid, f in oid_repo.items() if live.get(f)]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [oid for _, oid in scored[:top]]


def intersperse_stars(selected: List[Dict[str, str]], all_rows: List[Dict[str, str]],
                      star_ids: List[str], head: int) -> List[Dict[str, str]]:
    """Weave the star-ranked papers into the first `head` positions, alternating
    with the citation order. Star papers not already in `selected` are pulled in
    from the full citation rows. The remaining citation order follows unchanged."""
    by_oid = {r["openreview_id"]: r for r in selected}
    full = {r["openreview_id"]: r for r in all_rows}
    for oid in star_ids:                       # ensure star papers are available
        if oid not in by_oid and oid in full:
            by_oid[oid] = full[oid]
    cite_order = list(selected)
    result: List[Dict[str, str]] = []
    used: set = set()
    ci = si = 0
    take_star = False
    while len(result) < head and (ci < len(cite_order) or si < len(star_ids)):
        if take_star:
            while si < len(star_ids) and (star_ids[si] in used or star_ids[si] not in by_oid):
                si += 1
            if si < len(star_ids):
                oid = star_ids[si]; si += 1
                result.append(by_oid[oid]); used.add(oid)
        else:
            while ci < len(cite_order) and cite_order[ci]["openreview_id"] in used:
                ci += 1
            if ci < len(cite_order):
                r = cite_order[ci]; ci += 1
                result.append(r); used.add(r["openreview_id"])
        take_star = not take_star
    # append the rest in citation order, then any leftover star papers
    for r in cite_order:
        if r["openreview_id"] not in used:
            result.append(r); used.add(r["openreview_id"])
    for oid in star_ids:
        if oid not in used and oid in by_oid:
            result.append(by_oid[oid]); used.add(oid)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--citations", default="outputs/icml2026_citations.csv")
    ap.add_argument("--stars", default="outputs/icml2026_top_papers_by_github_stars.csv")
    ap.add_argument("--posts", default="outputs/icml2026_author_posts.json")
    ap.add_argument("--out-md", default="outputs/icml2026_thread.md")
    ap.add_argument("--out-txt", default="outputs/icml2026_thread_plaintext.txt")
    ap.add_argument("--out-csv", default="outputs/icml2026_thread_papers.csv")
    ap.add_argument("--base", type=int, default=30)
    ap.add_argument("--extend-to", type=int, default=50)
    ap.add_argument("--threshold", type=int, default=25)
    ap.add_argument("--live-stars", default="outputs/_live_stars.json")
    ap.add_argument("--star-top", type=int, default=5,
                    help="number of most-starred papers to weave into the head")
    ap.add_argument("--star-into", type=int, default=10,
                    help="weave the most-starred papers into the first N entries")
    args = ap.parse_args()

    rows = list(csv.DictReader(Path(args.citations).open(encoding="utf-8")))
    stars = load_stars(Path(args.stars))
    posts = json.loads(Path(args.posts).read_text(encoding="utf-8")) if Path(args.posts).exists() else {}

    selected = select_papers(rows, args.base, args.extend_to, args.threshold)
    star_ids = star_ranked_oids(posts, Path(args.stars), Path(args.live_stars), args.star_top)
    if args.star_into and star_ids:
        selected = intersperse_stars(selected, rows, star_ids, args.star_into)

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
                "github_stars": (str(prow["github_stars"]) if prow.get("github_stars") is not None
                                 else srow.get("github_stars", "")),
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
    lines.append(f"# ICML 2026 — Top {n} accepted papers by impact")
    lines.append("")
    lines.append(f"Primarily ranked by Semantic Scholar citations (top {args.base} by citations, "
                 f"extended to {n} while > {args.threshold} citations). The **top {args.star_top} "
                 f"papers by GitHub stars** are woven into the first {args.star_into} entries, so the "
                 "head reflects both citation impact and code adoption (several papers top both). "
                 "Each entry shows citation count and live GitHub stars.")
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
        stars_s = (str(prow["github_stars"]) if prow.get("github_stars") is not None
                   else srow.get("github_stars", ""))
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
        def handle_links(hs):
            return " ".join(f"[@{h}](https://x.com/{h})" for h in hs)

        post = prow.get("author_post_url", "")
        tag = prow.get("tag_handles", []) or []
        cand_urls = prow.get("candidate_post_urls", []) or []
        cand_handles = [h for h in (prow.get("candidate_handles", []) or []) if h not in tag]
        if post:
            lines.append(f"**Author X post:** {post}")
            if tag:
                lines.append(f"**Tag:** {handle_links(tag)}")
        else:
            lines.append("**Author X post:** _TODO: verify author thread_")
            if cand_handles:
                lines.append(f"**Author handle(s):** {handle_links(cand_handles[:5])}")
            if cand_urls:
                lines.append(f"  - candidate post(s): {', '.join(cand_urls[:3])}")
        note = prow.get("note") or prow.get("post_note")
        if note:
            lines.append(f"_Note: {note}_")
        lines.append("")
        lines.append("---")
        lines.append("")

    Path(args.out_md).write_text("\n".join(lines), encoding="utf-8")

    # ---- plain-text version (copy-paste straight into X) ----
    tx: List[str] = []
    for r in selected:
        oid = r.get("openreview_id", "")
        srow = stars.get(oid, {})
        prow = posts.get(oid, {})
        cc = r.get("citation_count", "")
        stars_s = (str(prow["github_stars"]) if prow.get("github_stars") is not None
                   else srow.get("github_stars", ""))
        meta = f"{r.get('first_author','')} et al. — {cc} citations"
        if stars_s:
            meta += f" · {stars_s}★ GitHub"
        if r.get("is_oral") == "true":
            meta += " · Oral"
        elif r.get("is_spotlight") == "true":
            meta += " · Spotlight"
        handles = prow.get("tag_handles") or prow.get("candidate_handles") or []
        repo = prow.get("github_repo") or srow.get("github_repo") or ""
        post = prow.get("author_post_url", "")

        tx.append(clean_latex(r.get("title", "")))
        tx.append("")
        tx.append(meta)
        if handles:
            tx.append(" ".join("@" + h for h in handles[:4]))
        tx.append("")
        tx.append(one_line_blurb(r.get("abstract", "")).replace("*", ""))
        tx.append("")
        if r.get("arxiv_abs_url"):
            tx.append(f"arXiv: {r['arxiv_abs_url']}")
        if repo:
            tx.append(f"Code: {repo}")
        tx.append("")
        tx.append(post if post else "[X post link]")
        tx.append("")
        tx.append("----")
        tx.append("")
    Path(args.out_txt).write_text("\n".join(tx), encoding="utf-8")

    print(f"Selected {n} papers (base {args.base}, extend-to {args.extend_to}, >{args.threshold} cites).")
    print(f"Wrote {args.out_md}, {args.out_txt} and {args.out_csv}.")
    cutoff = to_int(selected[-1].get("citation_count")) if selected else 0
    print(f"Citation range: #{1}={to_int(selected[0].get('citation_count'))} .. #{n}={cutoff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
