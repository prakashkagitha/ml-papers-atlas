#!/usr/bin/env python3
"""Best-effort discovery of each top paper's ORIGINAL author/lab X (Twitter) post.

X/Twitter is not crawlable by general search engines, so we cannot reliably
find author threads by web search alone. This script gathers the *machine-
findable* signals and leaves a clearly-marked slot for a human/agent to drop in
the verified author post URL:

  1. The paper's official GitHub repo README (resolved from the GitHub-stars
     cross-check CSV, or via a GitHub code search by title) almost always links
     the authors' announcement thread. We fetch the README and extract every
     x.com / twitter.com URL and @handle, ranked so that *non* paper-sharing
     accounts (not @_akhaliq, @HuggingPapers, @fly51fly, @rryssf_, ...) come first.
  2. The Hugging Face papers page (huggingface.co/papers/<arxiv>) often shows the
     submitting author and links social posts.

Output: outputs/icml2026_author_posts.json — a dict keyed by openreview_id with
{title, arxiv, github_repo, hf_page, candidate_post_urls, candidate_handles,
 author_post_url (BLANK, fill after verifying), tag_handles}.
The thread builder reads this file; `author_post_url` is what gets quoted/RT'd.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Accounts that *share* papers but are not the authors — deprioritize / drop.
SHARING_ACCOUNTS = {
    "_akhaliq", "huggingpapers", "fly51fly", "rryssf_", "papers_anon",
    "arxiv_daily", "arxivsanity", "ak92501", "deeplearningai", "huggingface",
    "gradio", "github", "arxiv", "paperswithcode",
}

X_URL_RE = re.compile(r"https?://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})(?:/status/(\d+))?", re.I)
HANDLE_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{2,15})\b")


def gh(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}" if TOKEN else "",
            "Accept": "application/vnd.github+json",
            "User-Agent": "icml2026-posts",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_readme(full_name: str) -> str:
    try:
        d = gh(f"https://api.github.com/repos/{full_name}/readme")
        return base64.b64decode(d["content"]).decode("utf-8", "ignore")
    except Exception:
        return ""


# repo-name patterns that indicate a paper-aggregator list, not a paper's own repo
AGGREGATOR_RE = re.compile(
    r"awesome|paper[-_]?list|papers|daily|survey|collection|topconf|arxiv|reading|notes|zoo",
    re.I,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _title_tokens(title: str) -> set:
    # distinctive tokens: the method name (first word before ':') + long words
    head = title.split(":")[0]
    toks = set(_TOKEN_RE.findall(head.lower()))
    toks |= {t for t in _TOKEN_RE.findall(title.lower()) if len(t) >= 5}
    stop = {"learning", "model", "models", "language", "large", "towards", "neural",
            "network", "networks", "training", "efficient", "reasoning", "based"}
    return {t for t in toks if t not in stop and len(t) >= 3}


def gh_search_repo(title: str) -> str:
    """Find a paper's OWN code repo (not an aggregator list) by title.

    Accept a hit only if the repo *name* shares a distinctive token with the
    title and the repo name does not look like an awesome-list / paper-dump.
    """
    q = urllib.parse.quote(f'"{title}" in:readme,description')
    try:
        d = gh(f"https://api.github.com/search/repositories?q={q}&sort=stars&per_page=10")
    except Exception:
        return ""
    ttoks = _title_tokens(title)
    for it in d.get("items", []):
        full = it["full_name"]
        name = full.split("/")[-1]
        if AGGREGATOR_RE.search(name):
            continue
        name_toks = set(_TOKEN_RE.findall(name.lower()))
        if ttoks & name_toks:                # repo name echoes the paper/method name
            return full
    return ""


def extract_posts(readme: str) -> Dict[str, List[str]]:
    # Only handles taken from x.com / twitter.com links are real X handles.
    # Bare "@mention" tokens in a GitHub README are GitHub usernames, NOT X
    # handles, so we deliberately do NOT harvest them here.
    urls: List[str] = []
    handles: List[str] = []
    for m in X_URL_RE.finditer(readme):
        handle = m.group(1).lower()
        if m.group(2):  # a full /status/ thread link is a strong author-post signal
            urls.append(m.group(0))
        if handle not in {"intent", "share", "home", "search"}:
            handles.append(m.group(1))

    def rank(h: str) -> int:
        return 1 if h.lower() in SHARING_ACCOUNTS else 0

    seen: set = set()
    handles_ranked = [h for h in sorted(handles, key=rank) if not (h.lower() in seen or seen.add(h.lower()))]
    urls = list(dict.fromkeys(urls))
    return {"urls": urls, "handles": handles_ranked}


def load_stars_map(path: Path) -> Dict[str, Dict[str, str]]:
    """openreview_id -> stars row (has github_repo)."""
    if not path.exists():
        return {}
    out = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if r.get("openreview_id"):
            out[r["openreview_id"]] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", default="outputs/icml2026_top_cited.csv",
                    help="citation-sorted CSV (top slice) to discover posts for")
    ap.add_argument("--stars", default="outputs/icml2026_top_papers_by_github_stars.csv")
    ap.add_argument("--out", default="outputs/icml2026_author_posts.json")
    ap.add_argument("--limit", type=int, default=50, help="how many top papers to process")
    args = ap.parse_args()

    rows = list(csv.DictReader(Path(args.top).open(encoding="utf-8")))[: args.limit]
    stars_map = load_stars_map(Path(args.stars))

    result: Dict[str, Any] = {}
    for r in rows:
        oid = r.get("openreview_id", "")
        arxiv = r.get("arxiv_id", "")
        repo = ""
        srow = stars_map.get(oid)
        if srow and srow.get("github_repo"):
            cand = srow["github_repo"].rsplit("github.com/", 1)[-1]
            if not AGGREGATOR_RE.search(cand.split("/")[-1]):
                repo = cand
        if not repo:
            repo = gh_search_repo(r.get("title", ""))
            time.sleep(2.0)  # GitHub code search is 30/min
        readme = get_readme(repo) if repo else ""
        posts = extract_posts(readme) if readme else {"urls": [], "handles": []}
        result[oid] = {
            "rank": r.get("rank", ""),
            "title": r.get("title", ""),
            "citation_count": r.get("citation_count", ""),
            "arxiv": arxiv,
            "github_repo": f"https://github.com/{repo}" if repo else "",
            "hf_page": f"https://huggingface.co/papers/{arxiv}" if arxiv else "",
            "candidate_post_urls": posts["urls"],
            "candidate_handles": posts["handles"][:8],
            "author_post_url": "",      # FILL after verifying it is the authors', not a sharer
            "tag_handles": [],          # FILL: author/lab handles to @-tag
        }
        print(f"[{r.get('rank','?'):>3}] {r.get('title','')[:48]:48} repo={repo or '-':30} "
              f"x_urls={len(posts['urls'])} handles={posts['handles'][:3]}")
        time.sleep(0.4)

    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(result)} entries to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
