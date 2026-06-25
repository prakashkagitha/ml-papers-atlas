# ml-papers-atlas

Mapping machine-learning **conference papers** (ICML, NeurIPS, ICLR, and more) to
**arXiv**, **citation counts**, and **author / lab connections** — and the
insights that fall out of connecting them (most-cited papers, adoption via
GitHub stars, trend lines, author graphs).

Each conference lives in its own folder with the same shape: a small, reproducible
pipeline plus checked-in `outputs/` CSVs so the data is shareable immediately.

## Venues

| Folder | Venue | Papers | Highlights |
|--------|-------|-------:|------------|
| [`icml2026/`](icml2026/) | ICML 2026 | 6,343 | accepted-paper metadata · Semantic Scholar citations · GitHub-stars cross-check · top-cited X-thread |

(NeurIPS 2025 / ICLR pipelines to be migrated in under the same layout.)

## Conventions

Inside each `<venue>/` folder:

- `*_build_metadata.py` / export script — accepted-paper list from the official source.
- `*_citations.py` — match each paper to Semantic Scholar (title search; arXiv id
  + citation count in one call) and sort by citations.
- `*_github_stars_rank.py` — adoption cross-check: rank papers by their code repo's stars.
- `*_find_author_posts.py` — best-effort discovery of the authors' announcement
  thread on X (from the repo README / HF page).
- `*_build_thread.py` — assemble a citation-sorted CSV + a thread-ready markdown.
- `outputs/` — checked-in CSV/MD artifacts, ready to share or verify.

## Data sources

- **Accepted papers:** the conference's official virtual-site metadata.
- **Citations + arXiv ids:** [Semantic Scholar Graph API](https://www.semanticscholar.org/product/api)
  (an API key is recommended; the public pool is heavily rate-limited).
- **Adoption proxy:** the GitHub API (stars on the paper's official code repo).

> Note on OpenAlex: as of mid-2026 OpenAlex moved to a metered model (~100 free
> requests/day), so it is no longer practical as the bulk citation engine here.
> Semantic Scholar is the primary source.

## License

MIT (see `LICENSE`).
