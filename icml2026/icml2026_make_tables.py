#!/usr/bin/env python3
"""Render ICML 2026 ranking tables as PNG images (no matplotlib; PIL only).

Produces:
  outputs/icml2026_top20_by_citations.png  -- top 20 papers by Semantic Scholar
      citations, with GitHub stars alongside.
  outputs/icml2026_top20_by_stars.png      -- top 20 papers by GitHub stars,
      with citation counts alongside.

Star counts come from outputs/_live_stars.json (live GitHub API snapshot);
citations from outputs/icml2026_citations.csv; repo links from the stars
cross-check and the author-posts JSON.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
F_REG = f"{FONT_DIR}/DejaVuSans.ttf"
F_BOLD = f"{FONT_DIR}/DejaVuSans-Bold.ttf"

# palette
C_BG = (255, 255, 255)
C_HEADER = (31, 59, 97)        # dark navy
C_HEADER_TXT = (255, 255, 255)
C_ROW_A = (255, 255, 255)
C_ROW_B = (241, 245, 250)
C_TEXT = (24, 28, 34)
C_MUTED = (110, 120, 132)
C_CITE = (176, 48, 48)         # citations accent
C_STAR = (193, 138, 17)        # github stars accent
C_LINE = (214, 221, 230)
C_TITLEBAR = (15, 30, 52)


def load_master() -> Dict[str, Dict[str, str]]:
    """openreview_id -> citation row (rank/title/author/citations/type)."""
    out = {}
    for r in csv.DictReader(Path("outputs/icml2026_citations.csv").open(encoding="utf-8")):
        out[r["openreview_id"]] = r
    return out


_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
          "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ",
          "sigma": "σ", "tau": "τ", "phi": "φ", "psi": "ψ", "omega": "ω"}
_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def clean_title(t: str) -> str:
    import re
    t = t or ""
    for name, ch in _GREEK.items():
        t = re.sub(rf"\\{name}\b", ch, t)
    t = re.sub(r"\^\{?(\d+)\}?", lambda m: m.group(1).translate(_SUP), t)
    t = re.sub(r"_\{?(\d+)\}?", lambda m: m.group(1).translate(_SUB), t)
    t = t.replace("$", "").replace("\\", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", t).strip()


def short_authors(authors: str) -> str:
    first = (authors or "").split(",")[0].strip()
    rest = [a for a in (authors or "").split(",") if a.strip()]
    return f"{first} et al." if len(rest) > 1 else first


def paper_type(r: Dict[str, str]) -> str:
    if r.get("is_oral") == "true":
        return "Oral"
    if r.get("is_spotlight") == "true":
        return "Spotlight"
    return "Poster"


def wrap(draw, text, font, max_w, max_lines=2) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) == max_lines - 1:
                break
    if cur:
        lines.append(cur)
    # ellipsize last line if leftover words remain
    used = sum(len(l.split()) for l in lines)
    if used < len(words) and lines:
        last = lines[-1]
        while draw.textlength(last + " …", font=font) > max_w and last:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last + " …"
    return lines[:max_lines]


def fmt_int(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "—"


def render(rows: List[Dict[str, Any]], columns: List[Dict[str, Any]],
           title: str, subtitle: str, out_path: str) -> None:
    f_title = ImageFont.truetype(F_BOLD, 30)
    f_sub = ImageFont.truetype(F_REG, 17)
    f_head = ImageFont.truetype(F_BOLD, 18)
    f_cell = ImageFont.truetype(F_REG, 18)
    f_cell_b = ImageFont.truetype(F_BOLD, 19)
    f_small = ImageFont.truetype(F_REG, 15)

    pad = 22
    width = sum(c["w"] for c in columns) + pad * 2
    title_h = 92
    head_h = 46
    row_h = 60
    height = title_h + head_h + row_h * len(rows) + pad

    img = Image.new("RGB", (width, height), C_BG)
    d = ImageDraw.Draw(img)

    # title bar
    d.rectangle([0, 0, width, title_h], fill=C_TITLEBAR)
    d.text((pad, 20), title, font=f_title, fill=(255, 255, 255))
    d.text((pad, 60), subtitle, font=f_sub, fill=(173, 196, 224))

    y = title_h
    # header row
    x = pad
    d.rectangle([0, y, width, y + head_h], fill=C_HEADER)
    for c in columns:
        tx = x + 12 if c["align"] == "l" else x + c["w"] - 12
        anchor = "lm" if c["align"] == "l" else "rm"
        d.text((tx, y + head_h // 2), c["head"], font=f_head, fill=C_HEADER_TXT, anchor=anchor)
        x += c["w"]
    y += head_h

    for i, row in enumerate(rows):
        rc = C_ROW_A if i % 2 == 0 else C_ROW_B
        d.rectangle([0, y, width, y + row_h], fill=rc)
        d.line([0, y + row_h, width, y + row_h], fill=C_LINE, width=1)
        x = pad
        for c in columns:
            key = c["key"]
            val = row.get(key, "")
            cx_l = x + 12
            cx_r = x + c["w"] - 12
            cy = y + row_h // 2
            if key == "title":
                lines = wrap(d, val, f_cell, c["w"] - 24, max_lines=2)
                total = len(lines) * 21
                ty = y + (row_h - total) // 2 + 10
                for ln in lines:
                    d.text((cx_l, ty), ln, font=f_cell, fill=C_TEXT, anchor="lm")
                    ty += 21
            elif key == "rank":
                d.text(((x + c["w"] / 2), cy), str(val), font=f_cell_b, fill=C_MUTED, anchor="mm")
            elif key in ("citations", "stars"):
                color = C_CITE if key == "citations" else C_STAR
                d.text((cx_r, cy), fmt_int(val), font=f_cell_b, fill=color, anchor="rm")
            elif key == "author":
                d.text((cx_l, cy), val, font=f_cell, fill=C_TEXT, anchor="lm")
            elif key == "type":
                t = val
                tc = (176, 48, 48) if t == "Oral" else (30, 110, 70) if t == "Spotlight" else C_MUTED
                d.text(((x + c["w"] / 2), cy), t, font=f_small, fill=tc, anchor="mm")
            x += c["w"]
        y += row_h

    img.save(out_path)
    print(f"wrote {out_path}  ({width}x{height})")


def main() -> None:
    master = load_master()
    live = json.loads(Path("outputs/_live_stars.json").read_text())
    posts = json.loads(Path("outputs/icml2026_author_posts.json").read_text())

    # rank -> repo full_name (from posts json) for the cited papers
    oid_repo: Dict[str, str] = {}
    for oid, v in posts.items():
        if v.get("github_repo"):
            oid_repo[oid] = v["github_repo"].rsplit("github.com/", 1)[-1].strip("/")
    import re

    def oid_of(row: Dict[str, str]) -> str:
        if row.get("openreview_id"):
            return row["openreview_id"]
        m = re.search(r"id=([^&\s]+)", row.get("openreview_url", "") or "")
        return m.group(1) if m else ""

    # stars cross-check repos too
    for r in csv.DictReader(Path("outputs/icml2026_top_papers_by_github_stars.csv").open(encoding="utf-8")):
        oid = oid_of(r)
        if oid and r.get("github_repo"):
            oid_repo.setdefault(oid, r["github_repo"].rsplit("github.com/", 1)[-1].strip("/"))

    def stars_for(oid: str) -> Optional[int]:
        full = oid_repo.get(oid)
        return live.get(full) if full else None

    # ---- Top 20 by citations ----
    cited = sorted(master.values(), key=lambda r: int(r["citation_count"]) if r["citation_count"].lstrip("-").isdigit() else -1, reverse=True)[:20]
    rows_cit = []
    for i, r in enumerate(cited, 1):
        rows_cit.append({
            "rank": i, "title": clean_title(r["title"]), "author": short_authors(r["authors"]),
            "citations": r["citation_count"], "stars": stars_for(r["openreview_id"]),
            "type": paper_type(r),
        })
    cols_cit = [
        {"head": "#", "key": "rank", "w": 48, "align": "c"},
        {"head": "Paper", "key": "title", "w": 600, "align": "l"},
        {"head": "First author", "key": "author", "w": 215, "align": "l"},
        {"head": "Citations", "key": "citations", "w": 120, "align": "r"},
        {"head": "GitHub ★", "key": "stars", "w": 120, "align": "r"},
        {"head": "Type", "key": "type", "w": 110, "align": "c"},
    ]
    render(rows_cit, cols_cit,
           "ICML 2026 — Top 20 papers by citations",
           "Citation counts: Semantic Scholar snapshot · GitHub ★: live · ml-papers-atlas",
           "outputs/icml2026_top20_by_citations.png")

    # ---- Top 20 by GitHub stars ----
    star_papers = []
    seen = set()
    for r in csv.DictReader(Path("outputs/icml2026_top_papers_by_github_stars.csv").open(encoding="utf-8")):
        oid = oid_of(r)
        full = oid_repo.get(oid)
        s = live.get(full) if full else None
        if s is None or oid in seen:
            continue
        seen.add(oid)
        m = master.get(oid, {})
        star_papers.append({
            "title": clean_title(r["title"]), "author": short_authors(r.get("authors") or m.get("authors", "")),
            "stars": s, "citations": m.get("citation_count", ""),
            "type": paper_type(m) if m else "Poster", "repo": full,
        })
    star_papers.sort(key=lambda x: x["stars"], reverse=True)
    rows_star = []
    for i, r in enumerate(star_papers[:20], 1):
        rows_star.append({"rank": i, **r})
    cols_star = [
        {"head": "#", "key": "rank", "w": 48, "align": "c"},
        {"head": "Paper", "key": "title", "w": 600, "align": "l"},
        {"head": "First author", "key": "author", "w": 215, "align": "l"},
        {"head": "GitHub ★", "key": "stars", "w": 120, "align": "r"},
        {"head": "Citations", "key": "citations", "w": 120, "align": "r"},
        {"head": "Type", "key": "type", "w": 110, "align": "c"},
    ]
    render(rows_star, cols_star,
           "ICML 2026 — Top 20 papers by GitHub stars",
           "GitHub ★: live snapshot · Citations: Semantic Scholar · ml-papers-atlas",
           "outputs/icml2026_top20_by_stars.png")


if __name__ == "__main__":
    main()
