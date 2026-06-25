#!/usr/bin/env python3
"""Build the ICML 2026 accepted-paper metadata CSV.

Source of truth: the ICML virtual site's public static metadata list
    https://icml.cc/static/virtual/data/icml-2026-orals-posters.json
(the "Download data" payload behind https://icml.cc/Downloads/2026).

Because icml.cc / OpenReview are blocked by the egress policy in some
environments, this script reads a verbatim GitHub mirror of that data:
the consolidated index published by the open-source ICML 2026 browser
project (KimYeongHyeon/ICML_2026_Browser, file docs/site/data/icml2026_index.json),
which is derived 1:1 from the ICML virtual metadata. Field values
(title, authors, abstract, session, decision, openreview id) are
unchanged from the official source.

Output columns are intentionally a superset of what we need downstream:
metadata, session info, and every link we can resolve at this stage.
arXiv / Semantic Scholar / citation columns are left blank here and are
filled by the citation-enrichment step.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

INDEX_URL = (
    "https://raw.githubusercontent.com/KimYeongHyeon/ICML_2026_Browser/"
    "main/docs/site/data/icml2026_index.json"
)


def norm_space(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def parse_ids(raw_id: str) -> Dict[str, str]:
    out = {"openreview_id": "", "icml_id": ""}
    m = re.search(r"openreview:([^;]+)", raw_id or "")
    if m:
        out["openreview_id"] = m.group(1)
    m = re.search(r"icml:([^;]+)", raw_id or "")
    if m:
        out["icml_id"] = m.group(1)
    return out


def first_author(authors: str) -> str:
    if not authors:
        return ""
    return norm_space(authors.split(",")[0])


def join_tags(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(norm_space(v) for v in value if norm_space(v))
    return norm_space(value)


def build_rows(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for r in records:
        if r.get("type") != "paper" or r.get("group") != "Main Conference":
            continue
        ids = parse_ids(r.get("id", ""))
        authors = norm_space(r.get("authors"))
        ptype = norm_space(r.get("presentationType"))
        rows.append(
            {
                "openreview_id": ids["openreview_id"],
                "icml_id": ids["icml_id"],
                "title": norm_space(r.get("title")),
                "authors": authors,
                "first_author": first_author(authors),
                "num_authors": len([a for a in authors.split(",") if a.strip()]) if authors else 0,
                "decision": norm_space(r.get("decision")),
                "presentation_type": ptype,
                "is_oral": "true" if "oral" in ptype.lower() else "false",
                "is_spotlight": "true" if "spotlight" in norm_space(r.get("decision")).lower() else "false",
                "session": norm_space(r.get("session")),
                "room": norm_space(r.get("roomName")),
                "start_time": norm_space(r.get("startTime")),
                "end_time": norm_space(r.get("endTime")),
                "category": norm_space(r.get("category")),
                "area_tags": join_tags(r.get("areaTags")),
                "domain_tags": join_tags(r.get("domainTags")),
                "abstract": norm_space(r.get("abstract")),
                "icml_page_url": norm_space(r.get("pageUrl")),
                "openreview_url": norm_space(r.get("openreviewUrl")),
                "icml_pdf_url": norm_space(r.get("pdfUrl")),  # empty until ICML releases PDFs
                # ---- filled by the citation-enrichment step ----
                "arxiv_id": "",
                "arxiv_abs_url": "",
                "arxiv_pdf_url": "",
                "semanticscholar_paper_id": "",
                "semanticscholar_url": "",
                "semanticscholar_citation_count": "",
                "openalex_id": "",
                "openalex_citation_count": "",
                "citation_count": "",
                "citation_source": "",
                "match_rule": "",
            }
        )
    return rows


FIELDNAMES = [
    "rank",
    "openreview_id",
    "icml_id",
    "title",
    "authors",
    "first_author",
    "num_authors",
    "decision",
    "presentation_type",
    "is_oral",
    "is_spotlight",
    "session",
    "room",
    "start_time",
    "end_time",
    "category",
    "area_tags",
    "domain_tags",
    "abstract",
    "icml_page_url",
    "openreview_url",
    "icml_pdf_url",
    "arxiv_id",
    "arxiv_abs_url",
    "arxiv_pdf_url",
    "semanticscholar_paper_id",
    "semanticscholar_url",
    "semanticscholar_citation_count",
    "openalex_id",
    "openalex_citation_count",
    "citation_count",
    "citation_source",
    "match_rule",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build ICML 2026 metadata CSV from the index JSON")
    ap.add_argument(
        "--index",
        default="icml2026_index.json",
        help="Path to icml2026_index.json (download from INDEX_URL if absent).",
    )
    ap.add_argument("--out", default="outputs/icml2026_accepted.csv")
    args = ap.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        raise FileNotFoundError(
            f"{index_path} not found. Download it from:\n  {INDEX_URL}"
        )

    data = json.loads(index_path.read_text(encoding="utf-8"))
    records = data["records"] if isinstance(data, dict) else data
    rows = build_rows(records)
    rows.sort(key=lambda r: (r["title"].lower()))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for i, row in enumerate(rows, 1):
            row.setdefault("rank", "")
            writer.writerow(row)

    n_oral = sum(1 for r in rows if r["is_oral"] == "true")
    n_spot = sum(1 for r in rows if r["is_spotlight"] == "true")
    print(f"Wrote {len(rows)} ICML 2026 papers to {out_path}")
    print(f"  orals (Oral + Poster): {n_oral} | spotlight decisions: {n_spot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
