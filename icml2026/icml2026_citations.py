#!/usr/bin/env python3
"""Enrich ICML 2026 papers with citation counts and sort by them.

Matching strategy (mirrors the repo's NeurIPS/COLM approach, with OpenAlex
added as a reachable bulk engine):

  1. OpenAlex title search (`filter=title.search:...`). Accept the candidate if
       - its normalized title equals the query title (exact match), OR
       - the first author of the top result matches the paper's first author.
     From the match we read `cited_by_count`, the OpenAlex id, the DOI, and the
     arXiv id (parsed from the work's locations / ids).
  2. Semantic Scholar enrichment: batch-hydrate every matched paper by arXiv id
     (`ARXIV:<id>`) or DOI (`DOI:<doi>`) via POST /paper/batch to obtain the
     Semantic Scholar `citationCount` and paper URL. This honors the request to
     use Semantic Scholar for citations while staying within its rate limits
     (a handful of batch calls instead of thousands of searches).
  3. Final `citation_count` = Semantic Scholar count when available, else the
     OpenAlex count. `citation_source` records which was used.

Outputs are sorted by `citation_count` descending.

Run this wherever outbound HTTPS to api.openalex.org / api.semanticscholar.org
is allowed (a normal machine, or a GitHub Actions runner). Set OPENALEX_MAILTO
(polite pool) and optionally SEMANTIC_SCHOLAR_API_KEY.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

SESSION = requests.Session()
OPENALEX_ROOT = "https://api.openalex.org"
SS_ROOT = "https://api.semanticscholar.org/graph/v1"
MAILTO = os.environ.get("OPENALEX_MAILTO", "")
SS_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or None
UA = "icml2026-citations/1.0 (research; contact via OPENALEX_MAILTO)"

SS_HEADERS = {"Accept": "application/json", "User-Agent": UA}
if SS_API_KEY:
    SS_HEADERS["x-api-key"] = SS_API_KEY


# --------------------------- normalization helpers ---------------------------

def norm_space(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def norm_title(s: str) -> str:
    # lowercase, drop latex/markup punctuation, collapse spaces
    s = (s or "").lower()
    s = s.replace("$", "").replace("\\", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return norm_space(s)


def norm_person(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z\s.\-']", " ", s)
    return norm_space(s)


def first_author_match(expected: str, candidate: str) -> bool:
    if not expected or not candidate:
        return False
    e, c = norm_person(expected), norm_person(candidate)
    if not e or not c:
        return False
    if c.startswith(e) or e.startswith(c):
        return True
    ep, cp = e.split(), c.split()
    if ep and cp and ep[-1] == cp[-1]:  # same surname
        return cp[0].startswith(ep[0]) or ep[0].startswith(cp[0])
    return False


ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})", re.I)


def extract_arxiv(work: Dict[str, Any]) -> str:
    # check ids, primary_location, and all locations for an arXiv landing page
    blobs: List[str] = []
    ids = work.get("ids") or {}
    for v in ids.values():
        blobs.append(str(v))
    for loc in (work.get("locations") or []):
        if loc:
            blobs.append(str(loc.get("landing_page_url") or ""))
            blobs.append(str(loc.get("pdf_url") or ""))
            src = loc.get("source") or {}
            blobs.append(str(src.get("display_name") or ""))
    for b in blobs:
        m = ARXIV_RE.search(b)
        if m:
            return m.group(1)
    return ""


# ------------------------------ OpenAlex ------------------------------

def openalex_search(title: str, sleep: float) -> List[Dict[str, Any]]:
    params = {
        "filter": f"title.search:{title}",
        "per-page": 5,
        "select": "id,title,publication_year,cited_by_count,authorships,ids,locations,doi",
    }
    if MAILTO:
        params["mailto"] = MAILTO
    for attempt in range(1, 6):
        try:
            r = SESSION.get(f"{OPENALEX_ROOT}/works", params=params,
                            headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 429:
                time.sleep(min(2 ** attempt, 30))
                continue
            r.raise_for_status()
            if sleep:
                time.sleep(sleep)
            return r.json().get("results", [])
        except requests.RequestException:
            time.sleep(min(2 ** attempt, 20))
    return []


def openalex_first_author(work: Dict[str, Any]) -> str:
    for a in work.get("authorships") or []:
        au = a.get("author") or {}
        if au.get("display_name"):
            return au["display_name"]
    return ""


def match_openalex(title: str, first_author: str, sleep: float) -> Optional[Dict[str, Any]]:
    results = openalex_search(title, sleep)
    if not results:
        return None
    qn = norm_title(title)
    # 1) exact normalized-title match anywhere in the top results
    for w in results:
        if norm_title(w.get("title") or "") == qn:
            return {"work": w, "rule": "openalex_title"}
    # 2) first-author match on the top result
    top = results[0]
    if first_author_match(first_author, openalex_first_author(top)):
        return {"work": top, "rule": "openalex_author"}
    return None


# --------------------------- Semantic Scholar batch ---------------------------

def ss_batch(ids: List[str], sleep: float) -> Dict[str, Dict[str, Any]]:
    """Return {requested_id: paper} for the given ARXIV:/DOI: ids."""
    out: Dict[str, Dict[str, Any]] = {}
    fields = "paperId,title,externalIds,url,citationCount,year"
    for i in range(0, len(ids), 400):
        chunk = ids[i : i + 400]
        for attempt in range(1, 6):
            try:
                r = SESSION.post(
                    f"{SS_ROOT}/paper/batch",
                    params={"fields": fields},
                    json={"ids": chunk},
                    headers=SS_HEADERS,
                    timeout=60,
                )
                if r.status_code == 429:
                    time.sleep(min(2 ** attempt, 30))
                    continue
                r.raise_for_status()
                data = r.json()
                for req_id, paper in zip(chunk, data):
                    if paper:
                        out[req_id] = paper
                if sleep:
                    time.sleep(sleep)
                break
            except requests.RequestException:
                time.sleep(min(2 ** attempt, 20))
    return out


# --------------------------- Semantic Scholar search ---------------------------

class RateLimiter:
    """Simple thread-safe min-interval limiter (e.g. 0.1s -> <=10 req/s)."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = max(now, self._next) + self.min_interval


SS_SEARCH_FIELDS = "title,citationCount,year,externalIds,url,authors.name"


def ss_search(title: str, limiter: "RateLimiter") -> List[Dict[str, Any]]:
    """Relevance search for a title; returns up to a few candidate papers."""
    for attempt in range(1, 7):
        limiter.wait()
        try:
            r = SESSION.get(
                f"{SS_ROOT}/paper/search",
                params={"query": title, "limit": 5, "fields": SS_SEARCH_FIELDS},
                headers=SS_HEADERS,
                timeout=40,
            )
            if r.status_code == 429:
                time.sleep(min(2 ** attempt, 20))
                continue
            r.raise_for_status()
            return r.json().get("data", []) or []
        except requests.RequestException:
            time.sleep(min(2 ** attempt, 15))
    return []


def ss_first_author(paper: Dict[str, Any]) -> str:
    for a in paper.get("authors") or []:
        if a.get("name"):
            return a["name"]
    return ""


def match_ss(title: str, first_author: str, limiter: "RateLimiter") -> Optional[Dict[str, Any]]:
    results = ss_search(title, limiter)
    if not results:
        return None
    qn = norm_title(title)
    for p in results:                                  # exact normalized-title match
        if norm_title(p.get("title") or "") == qn:
            return {"paper": p, "rule": "ss_title"}
    top = results[0]                                   # else first-author match on top hit
    if first_author_match(first_author, ss_first_author(top)):
        return {"paper": top, "rule": "ss_author"}
    return None


# ------------------------------ driver ------------------------------

def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser(description="Add citation counts to the ICML 2026 CSV and sort.")
    ap.add_argument("--in", dest="inp", default="outputs/icml2026_accepted.csv")
    ap.add_argument("--out", default="outputs/icml2026_citations.csv")
    ap.add_argument("--top-out", default="outputs/icml2026_top_cited.csv")
    ap.add_argument("--limit", type=int, help="Only process the first N (debug).")
    ap.add_argument("--engine", choices=["ss", "openalex"], default="ss",
                    help="Matching/citation engine. 'ss' = Semantic Scholar search "
                         "(match + citation in one call; needs SEMANTIC_SCHOLAR_API_KEY). "
                         "'openalex' = legacy OpenAlex-first (now budget-gated, ~100 req/day free).")
    ap.add_argument("--openalex-sleep", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=10,
                    help="Concurrent matching requests.")
    ap.add_argument("--ss-rate", type=float, default=9.0,
                    help="Max Semantic Scholar req/s (key tier is 10/s; keep a margin).")
    ap.add_argument("--ss-sleep", type=float, default=1.0)
    ap.add_argument("--top-n", type=int, default=60)
    args = ap.parse_args()

    if args.engine == "ss" and not SS_API_KEY:
        print("WARNING: --engine ss without SEMANTIC_SCHOLAR_API_KEY; the public "
              "pool is heavily rate-limited and will be very slow.", file=sys.stderr)

    rows = load_rows(Path(args.inp))
    if args.limit:
        rows = rows[: args.limit]
    total = len(rows)
    print(f"Matching {total} papers via {args.engine} ({args.workers} workers)...")

    start = time.time()
    lock = threading.Lock()
    done = [0]

    def progress() -> None:
        with lock:
            done[0] += 1
            i = done[0]
            if i % 25 == 0 or i == total:
                el = time.time() - start
                eta = (total - i) / (i / el) if el else 0
                matched = sum(1 for r in rows if r.get("citation_source") in ("semanticscholar", "openalex"))
                sys.stdout.write(f"\r[{args.engine}] {i}/{total} matched={matched} eta={eta:0.0f}s")
                sys.stdout.flush()

    if args.engine == "ss":
        limiter = RateLimiter(1.0 / args.ss_rate if args.ss_rate > 0 else 0.0)

        def process(row: Dict[str, str]) -> None:
            m = match_ss(row.get("title", ""), row.get("first_author", ""), limiter)
            if m:
                p = m["paper"]
                ext = p.get("externalIds") or {}
                arxiv = ext.get("ArXiv") or ""
                row["match_rule"] = m["rule"]
                row["semanticscholar_paper_id"] = p.get("paperId", "") or ""
                row["semanticscholar_url"] = p.get("url", "") or ""
                cc = p.get("citationCount")
                row["semanticscholar_citation_count"] = "" if cc is None else str(cc)
                if arxiv:
                    row["arxiv_id"] = arxiv
                    row["arxiv_abs_url"] = f"https://arxiv.org/abs/{arxiv}"
                    row["arxiv_pdf_url"] = f"https://arxiv.org/pdf/{arxiv}"
                if cc is not None:
                    row["citation_count"] = str(cc)
                    row["citation_source"] = "semanticscholar"
            if not row.get("citation_source"):
                row["citation_count"] = ""
                row["citation_source"] = "none"
            progress()

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(process, rows))
        sys.stdout.write("\n")
    else:
        arxiv_for_ss: List[str] = []
        doi_for_ss: List[str] = []

        def process(row: Dict[str, str]) -> None:
            m = match_openalex(row.get("title", ""), row.get("first_author", ""), args.openalex_sleep)
            if m:
                w = m["work"]
                row["match_rule"] = m["rule"]
                row["openalex_id"] = (w.get("id") or "").rsplit("/", 1)[-1]
                row["openalex_citation_count"] = str(w.get("cited_by_count", ""))
                doi = (w.get("doi") or "").replace("https://doi.org/", "")
                arxiv = extract_arxiv(w)
                with lock:
                    if arxiv:
                        row["arxiv_id"] = arxiv
                        row["arxiv_abs_url"] = f"https://arxiv.org/abs/{arxiv}"
                        row["arxiv_pdf_url"] = f"https://arxiv.org/pdf/{arxiv}"
                        arxiv_for_ss.append(arxiv)
                    elif doi:
                        doi_for_ss.append(doi)
                row["_doi"] = doi
            progress()

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(process, rows))
        sys.stdout.write("\n")

        print(f"Semantic Scholar batch: {len(arxiv_for_ss)} arXiv ids, {len(doi_for_ss)} DOIs...")
        ss_by_arxiv = ss_batch([f"ARXIV:{a}" for a in sorted(set(arxiv_for_ss))], args.ss_sleep)
        ss_by_doi = ss_batch([f"DOI:{d}" for d in sorted(set(doi_for_ss))], args.ss_sleep)

        def ss_lookup(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
            a = row.get("arxiv_id")
            if a and f"ARXIV:{a}" in ss_by_arxiv:
                return ss_by_arxiv[f"ARXIV:{a}"]
            d = row.get("_doi")
            if d and f"DOI:{d}" in ss_by_doi:
                return ss_by_doi[f"DOI:{d}"]
            return None

        for row in rows:
            paper = ss_lookup(row)
            if paper:
                row["semanticscholar_paper_id"] = paper.get("paperId", "") or ""
                row["semanticscholar_url"] = paper.get("url", "") or ""
                cc = paper.get("citationCount")
                row["semanticscholar_citation_count"] = "" if cc is None else str(cc)
            ss_cc = row.get("semanticscholar_citation_count", "")
            oa_cc = row.get("openalex_citation_count", "")
            if ss_cc != "":
                row["citation_count"] = ss_cc
                row["citation_source"] = "semanticscholar"
            elif oa_cc != "":
                row["citation_count"] = oa_cc
                row["citation_source"] = "openalex"
            else:
                row["citation_count"] = ""
                row["citation_source"] = "none"
            row.pop("_doi", None)

    def cc_int(row: Dict[str, str]) -> int:
        try:
            return int(row.get("citation_count") or -1)
        except ValueError:
            return -1

    rows.sort(key=cc_int, reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = str(i)

    fieldnames = list(rows[0].keys())
    with Path(args.out).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    with Path(args.top_out).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows[: args.top_n])

    matched = sum(1 for r in rows if r.get("citation_source") in ("semanticscholar", "openalex"))
    print(f"Done. Matched citations for {matched}/{total}. "
          f"Wrote {args.out} and top-{args.top_n} to {args.top_out}.")
    print("Top 10 preview:")
    for r in rows[:10]:
        print(f"  {r['rank']:>3} [{r['citation_count']:>5} {r['citation_source'][:4]}] {r['title'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
