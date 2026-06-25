# ICML 2026 — papers → arXiv → citations

A small, reproducible pipeline that builds the ICML 2026 accepted-paper list,
matches each paper to Semantic Scholar (citation count + arXiv id), cross-checks
adoption via GitHub stars, and assembles a citation-sorted "most-cited papers"
X/Twitter thread.

## Outputs (`outputs/`)

| File | What |
|------|------|
| `icml2026_accepted.csv` | all **6,343** main-conference papers: title, authors, decision, presentation type, session/room/time, category, abstract, ICML + OpenReview URLs |
| `icml2026_citations.csv` | every paper enriched with Semantic Scholar `citation_count`, arXiv id/links, paperId, match rule — sorted by citations |
| `icml2026_top_cited.csv` | top-60 slice of the above |
| `icml2026_top_papers_by_github_stars.csv` | adoption cross-check: 101 papers ranked by their code repo's GitHub stars |
| `icml2026_author_posts.json` | best-effort author/lab X post per top-50 paper (own-repo README scrape) |
| `icml2026_thread.md` | thread-ready markdown: top-30 (extended to 50 while > 25 citations), one block per paper, each with citations, GitHub stars, links, and the author X post |
| `icml2026_thread_plaintext.txt` | plain-text version of the thread, formatted to copy-paste straight into X posts |
| `icml2026_thread_papers.csv` | the selected thread papers as a flat CSV |
| `icml2026_top20_by_citations.png` | table image: top 20 by citations, with GitHub stars |
| `icml2026_top20_by_stars.png` | table image: top 20 by GitHub stars, with citations |

## Rankings

**Top 20 by citations** (citations = Semantic Scholar snapshot; ★ = live GitHub):

![Top 20 by citations](outputs/icml2026_top20_by_citations.png)

**Top 20 by GitHub stars** (an adoption proxy that surfaces hot, code-shipping papers a citation count misses):

![Top 20 by GitHub stars](outputs/icml2026_top20_by_stars.png)

## Pipeline

```bash
pip install -r requirements.txt

# 1) accepted-paper metadata (downloads the ICML 2026 virtual-site index mirror)
python icml2026_build_metadata.py --out outputs/icml2026_accepted.csv

# 2) citations + arXiv ids via Semantic Scholar (needs a key; see below)
export SEMANTIC_SCHOLAR_API_KEY=...        # https://www.semanticscholar.org/product/api
python icml2026_citations.py --engine ss --workers 10

# 3) adoption cross-check (needs a GitHub token)
export GITHUB_TOKEN=...
python icml2026_github_stars_rank.py

# 4) best-effort author X-post discovery for the top 50
python icml2026_find_author_posts.py --limit 50

# 5) assemble the thread (top-30, extend to 50 while > 25 citations)
python icml2026_build_thread.py

# 6) render the ranking table images (PNG; pulls live GitHub stars)
python icml2026_make_tables.py
```

## Data sources & caveats

- **Accepted papers** come from the ICML 2026 virtual-site metadata
  (`icml.cc/static/virtual/data/icml-2026-orals-posters.json`), read via a verbatim
  GitHub mirror. 6,343 unique main-conference papers (6,184 Poster, 159 Oral+Poster;
  536 spotlight decisions).
- **Citations** are from the **Semantic Scholar Graph API**. The `ss` engine does
  a title search per paper (match + citation count + arXiv id in one call). A key is
  strongly recommended — the public pool is heavily rate-limited; even with a key the
  search endpoint runs at ~1 req/s, so a full run takes ~1–2 h. ~66% of papers match;
  the rest are too new to be indexed (almost all have 0 citations).
- **OpenAlex is no longer used as the bulk engine** — as of mid-2026 it moved to a
  metered model (~100 free requests/day), which is impractical at 6k papers. The
  legacy `--engine openalex` path is kept for reference only.
- **Citation counts are a snapshot** and skew toward papers that were on arXiv early.
  Most ICML 2026 papers had near-zero citations at snapshot time.
- **Author X posts:** X/Twitter is not crawlable by general web search, so author
  threads are discovered only where a paper's **own** code-repo README links one.
  Everything else is left blank with candidate handles for manual verification.
  Paper-sharing accounts (@_akhaliq, @HuggingPapers, …) are filtered out.
