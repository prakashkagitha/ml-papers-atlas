#!/usr/bin/env python3
"""Render ICML 2026 ranking tables as high-resolution PNG images (PIL only).

Two independent lists with identical columns (# · Paper · First author ·
Citations · GitHub ★ · Type); one sorted by citations, one by GitHub stars:

  outputs/icml2026_top20_by_citations.png
  outputs/icml2026_top20_by_stars.png

Star counts come from outputs/_live_stars.json (live GitHub snapshot);
citations from outputs/icml2026_citations.csv.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

# ----- fonts (Inter: modern, screen-optimized) -----
_INT = "/usr/share/fonts/opentype/inter"
F_REGULAR = f"{_INT}/Inter-Regular.otf"
F_MEDIUM = f"{_INT}/Inter-Medium.otf"
F_SEMIBOLD = f"{_INT}/Inter-SemiBold.otf"
F_BOLD = f"{_INT}/Inter-Bold.otf"
F_XBOLD = f"{_INT}/Inter-ExtraBold.otf"

# ----- supersample for crisp, high-resolution output -----
SCALE = 3

# ----- palette -----
C_PAGE = (248, 250, 252)
C_TITLEBAR = (17, 28, 46)
C_TITLE = (255, 255, 255)
C_SUBTITLE = (151, 178, 214)
C_HEADER = (37, 55, 86)
C_HEADER_TXT = (226, 234, 245)
C_ROW_A = (255, 255, 255)
C_ROW_B = (243, 246, 250)
C_TEXT = (23, 30, 41)
C_MUTED = (118, 128, 142)
C_RANK = (158, 167, 180)
C_CITE = (197, 51, 51)
C_STAR = (191, 132, 17)
C_LINE = (224, 230, 238)
BADGE = {  # (bg, text)
    "Oral": ((253, 232, 232), (181, 45, 45)),
    "Spotlight": ((228, 244, 234), (28, 112, 70)),
    "Poster": ((236, 240, 245), (112, 122, 136)),
}


def S(x: float) -> int:
    return int(round(x * SCALE))


def font(path: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, S(size))


# ----- data helpers -----
def load_master() -> Dict[str, Dict[str, str]]:
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
    t = t or ""
    for name, ch in _GREEK.items():
        t = re.sub(rf"\\{name}\b", ch, t)
    t = re.sub(r"\^\{?(\d+)\}?", lambda m: m.group(1).translate(_SUP), t)
    t = re.sub(r"_\{?(\d+)\}?", lambda m: m.group(1).translate(_SUB), t)
    t = t.replace("$", "").replace("\\", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", t).strip()


def short_authors(authors: str) -> str:
    parts = [a.strip() for a in (authors or "").split(",") if a.strip()]
    if not parts:
        return ""
    return f"{parts[0]} et al." if len(parts) > 1 else parts[0]


def paper_type(r: Dict[str, str]) -> str:
    if r.get("is_oral") == "true":
        return "Oral"
    if r.get("is_spotlight") == "true":
        return "Spotlight"
    return "Poster"


def fmt_int(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "—"


def wrap_lines(draw, text, fnt, max_w, max_lines) -> List[str]:
    """Greedily fill each line; only ellipsize if it truly overflows max_lines."""
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and draw.textlength(trial, font=fnt) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    last = kept[-1]
    while draw.textlength(last + "…", font=fnt) > max_w and " " in last:
        last = last.rsplit(" ", 1)[0]
    kept[-1] = last + "…"
    return kept


# ----- rendering -----
def render(rows, columns, title, subtitle, sort_key, out_path) -> None:
    f_title = font(F_XBOLD, 26)
    f_sub = font(F_REGULAR, 13.5)
    f_head = font(F_SEMIBOLD, 13.5)
    f_rank = font(F_BOLD, 15)
    f_paper = font(F_SEMIBOLD, 14.5)
    f_auth = font(F_REGULAR, 13.5)
    f_num = font(F_BOLD, 15.5)
    f_badge = font(F_MEDIUM, 11.5)

    margin = 26
    width = S(margin) * 2 + sum(S(c["w"]) for c in columns)
    title_h = S(78)
    head_h = S(40)
    row_h = S(62)
    height = title_h + head_h + row_h * len(rows) + S(margin)

    img = Image.new("RGB", (width, height), C_PAGE)
    d = ImageDraw.Draw(img)

    # title bar
    d.rectangle([0, 0, width, title_h], fill=C_TITLEBAR)
    d.text((S(margin), S(18)), title, font=f_title, fill=C_TITLE)
    d.text((S(margin), S(52)), subtitle, font=f_sub, fill=C_SUBTITLE)

    # header
    x0 = S(margin)
    y = title_h
    d.rectangle([0, y, width, y + head_h], fill=C_HEADER)
    x = x0
    for c in columns:
        cw = S(c["w"])
        if c["align"] == "l":
            d.text((x + S(14), y + head_h / 2), c["head"], font=f_head,
                   fill=C_HEADER_TXT, anchor="lm")
        elif c["align"] == "r":
            d.text((x + cw - S(14), y + head_h / 2), c["head"], font=f_head,
                   fill=C_HEADER_TXT, anchor="rm")
        else:
            d.text((x + cw / 2, y + head_h / 2), c["head"], font=f_head,
                   fill=C_HEADER_TXT, anchor="mm")
        x += cw
    y += head_h

    for i, row in enumerate(rows):
        d.rectangle([0, y, width, y + row_h], fill=C_ROW_A if i % 2 == 0 else C_ROW_B)
        d.line([0, y + row_h, width, y + row_h], fill=C_LINE, width=max(1, S(0.4)))
        x = x0
        cy = y + row_h / 2
        for c in columns:
            cw = S(c["w"])
            key = c["key"]
            val = row.get(key, "")
            if key == "rank":
                d.text((x + cw / 2, cy), str(val), font=f_rank, fill=C_RANK, anchor="mm")
            elif key == "title":
                lines = wrap_lines(d, val, f_paper, cw - S(28), max_lines=2)
                lh = S(19)
                ty = cy - (len(lines) - 1) * lh / 2
                for ln in lines:
                    d.text((x + S(14), ty), ln, font=f_paper, fill=C_TEXT, anchor="lm")
                    ty += lh
            elif key == "author":
                a = wrap_lines(d, val, f_auth, cw - S(20), max_lines=2)
                lh = S(18)
                ty = cy - (len(a) - 1) * lh / 2
                for ln in a:
                    d.text((x + S(8), ty), ln, font=f_auth, fill=C_MUTED, anchor="lm")
                    ty += lh
            elif key in ("citations", "stars"):
                col = C_CITE if key == "citations" else C_STAR
                bold = f_num
                d.text((x + cw - S(16), cy), fmt_int(val), font=bold, fill=col, anchor="rm")
            elif key == "type":
                bg, fg = BADGE.get(val, BADGE["Poster"])
                tw = d.textlength(val, font=f_badge)
                bw, bh = tw + S(18), S(22)
                bx0 = x + cw / 2 - bw / 2
                by0 = cy - bh / 2
                d.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh], radius=S(11), fill=bg)
                d.text((x + cw / 2, cy), val, font=f_badge, fill=fg, anchor="mm")
            x += cw
        y += row_h

    img.save(out_path)
    print(f"wrote {out_path}  ({width}x{height})")


# identical columns for both tables
COLUMNS = [
    {"head": "#", "key": "rank", "w": 46, "align": "c"},
    {"head": "Paper", "key": "title", "w": 560, "align": "l"},
    {"head": "First author", "key": "author", "w": 196, "align": "l"},
    {"head": "Citations", "key": "citations", "w": 110, "align": "r"},
    {"head": "GitHub ★", "key": "stars", "w": 110, "align": "r"},
    {"head": "Type", "key": "type", "w": 104, "align": "c"},
]


def oid_of(row: Dict[str, str]) -> str:
    if row.get("openreview_id"):
        return row["openreview_id"]
    m = re.search(r"id=([^&\s]+)", row.get("openreview_url", "") or "")
    return m.group(1) if m else ""


def main() -> None:
    master = load_master()
    live = json.loads(Path("outputs/_live_stars.json").read_text())
    posts = json.loads(Path("outputs/icml2026_author_posts.json").read_text())

    oid_repo: Dict[str, str] = {}
    for oid, v in posts.items():
        if v.get("github_repo"):
            oid_repo[oid] = v["github_repo"].rsplit("github.com/", 1)[-1].strip("/")
    for r in csv.DictReader(Path("outputs/icml2026_top_papers_by_github_stars.csv").open(encoding="utf-8")):
        oid = oid_of(r)
        if oid and r.get("github_repo"):
            oid_repo.setdefault(oid, r["github_repo"].rsplit("github.com/", 1)[-1].strip("/"))

    def stars_for(oid: str) -> Optional[int]:
        full = oid_repo.get(oid)
        return live.get(full) if full else None

    def row_of(rank, m, stars):
        return {"rank": rank, "title": clean_title(m["title"]),
                "author": short_authors(m["authors"]),
                "citations": m["citation_count"], "stars": stars, "type": paper_type(m)}

    # ----- list A: top 20 by citations -----
    cited = sorted(master.values(),
                   key=lambda r: int(r["citation_count"]) if r["citation_count"].lstrip("-").isdigit() else -1,
                   reverse=True)[:20]
    rows_cit = [row_of(i, r, stars_for(r["openreview_id"])) for i, r in enumerate(cited, 1)]
    render(rows_cit, COLUMNS,
           "ICML 2026  ·  Top 20 papers by citations",
           "Citations: Semantic Scholar snapshot   ·   GitHub ★: live   ·   github.com/prakashkagitha/ml-papers-atlas",
           "citations", "outputs/icml2026_top20_by_citations.png")

    # ----- list B: top 20 by GitHub stars (independent list) -----
    # Rank over EVERY paper for which we have a repo + live star count — the
    # union of the "ICML 2026" keyword harvest and the per-paper repos found
    # during citation/author-post discovery. (The keyword harvest alone misses
    # repos whose description never mentions "ICML 2026", e.g. tau2-bench,
    # RoboTwin, SimpleMem.)
    star_rows = []
    for oid, full in oid_repo.items():
        s = live.get(full)
        if s is None or oid not in master:
            continue
        star_rows.append((s, master[oid]))
    star_rows.sort(key=lambda t: t[0], reverse=True)
    rows_star = [row_of(i, m, s) for i, (s, m) in enumerate(star_rows[:20], 1)]
    render(rows_star, COLUMNS,
           "ICML 2026  ·  Top 20 papers by GitHub stars",
           "GitHub ★: live snapshot   ·   Citations: Semantic Scholar   ·   github.com/prakashkagitha/ml-papers-atlas",
           "stars", "outputs/icml2026_top20_by_stars.png")


if __name__ == "__main__":
    main()
