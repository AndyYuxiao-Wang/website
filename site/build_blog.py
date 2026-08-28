# -*- coding: utf-8 -*-
"""Renders the two research notebooks into blog post HTML pages matching
the election-map app's BBC-studio dark theme, plus a blog index page.

Re-run this after editing either notebook in clustering/notebooks/:
    py build_blog.py
"""
import html
import json
from pathlib import Path

import markdown as md

SITE_DIR = Path(__file__).resolve().parent
ROOT = SITE_DIR.parent
NOTEBOOKS_DIR = ROOT / "clustering" / "notebooks"
BLOG_DIR = SITE_DIR / "blog"

NAV = """
<nav class="site-nav">
  <a class="brand" href="../index.html">ELECTIONS UK</a>
  <a class="nav-link {home_active}" href="../index.html">Home</a>
  <a class="nav-link {blog_active}" href="index.html">Blog</a>
  <a class="nav-link app-link" href="../app/index.html">Open the App</a>
</nav>
""".strip()

FOOTER = """
<footer class="site-footer">
  <p>An independent, data-driven model of British general elections &mdash;
     <a href="../index.html">home</a> &middot; <a href="index.html">blog</a> &middot;
     <a href="../app/index.html">interactive map</a></p>
</footer>
""".strip()

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} &middot; Elections UK</title>
<meta name="description" content="{description}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Roboto+Condensed:wght@400;500;700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../css/site.css">
</head>
<body>
{nav}

<header class="post-header" style="--accent: {accent};">
  <span class="series-tag">{series_tag}</span>
  <h1>{title}</h1>
  <p class="dek">{dek}</p>
  <p class="byline">{byline}</p>
</header>

<article class="post-body" style="--accent: {accent};">
{body}
</article>

<nav class="post-nav">
  <a class="btn btn-ghost" href="{prev_href}">{prev_label}</a>
  <a class="btn btn-ghost" href="{next_href}">{next_label}</a>
</nav>

{footer}
</body>
</html>
"""

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]


def render_markdown_cell(source_lines):
    text = "".join(source_lines)
    return md.markdown(text, extensions=MD_EXTENSIONS)


def render_code_cell(cell):
    source = html.escape("".join(cell["source"]))
    parts = [f'<div class="nb-code"><pre><code>{source}</code></pre></div>']
    for out in cell.get("outputs", []):
        if out.get("output_type") == "stream":
            text = html.escape("".join(out.get("text", [])))
            if text.strip():
                parts.append(f'<div class="nb-output"><div class="nb-output-label">Output</div><pre>{text}</pre></div>')
        elif out.get("output_type") == "execute_result":
            data = out.get("data", {})
            if "text/html" in data:
                raw_html = "".join(data["text/html"])
                parts.append(f'<div class="nb-output"><div class="nb-output-label">Output</div>{raw_html}</div>')
            elif "text/plain" in data:
                text = html.escape("".join(data["text/plain"]))
                parts.append(f'<div class="nb-output"><div class="nb-output-label">Output</div><pre>{text}</pre></div>')
    return "\n".join(parts)


def notebook_to_body_html(nb):
    parts = []
    # skip cell 0: the notebook's own title/dek cell duplicates the
    # post-header template (title, dek, series tag) already rendered above.
    for cell in nb["cells"][1:]:
        if cell["cell_type"] == "markdown":
            parts.append(render_markdown_cell(cell["source"]))
        elif cell["cell_type"] == "code":
            src = "".join(cell["source"]).strip()
            if not src:
                continue
            parts.append(render_code_cell(cell))
    return "\n\n".join(parts)


def fix_internal_links(body_html):
    # notebook cross-links point at the sibling .ipynb file; point them at
    # the rendered blog post instead.
    body_html = body_html.replace(
        "political_fragmentation_and_latent_groups.ipynb",
        "political-fragmentation-and-latent-groups.html",
    )
    body_html = body_html.replace(
        "the_prediction_pipeline.ipynb",
        "the-prediction-pipeline.html",
    )
    return body_html


POSTS = [
    {
        "notebook": "political_fragmentation_and_latent_groups.ipynb",
        "slug": "political-fragmentation-and-latent-groups.html",
        "series_tag": "Part 1 &middot; Methodology",
        "title": "One seat, many voters",
        "dek": "Why single-category constituency models are running out of road, and what "
               "unmixing 632 seats&rsquo; census composition into shared latent groups gets us instead.",
        "description": "Rebuilding the UK election tribe model on data-derived latent groups instead of hand-assigned labels.",
        "accent": "var(--bbc-segments)",
        "date": "2026",
        "read_time": "22 min read",
    },
    {
        "notebook": "the_prediction_pipeline.ipynb",
        "slug": "the-prediction-pipeline.html",
        "series_tag": "Part 2 &middot; Prediction",
        "title": "From groups to seats",
        "dek": "Flows, uncertainty, and tactical voting &mdash; opening up the pipeline that turns "
               "any group structure into seat-by-seat forecasts.",
        "description": "How the UK election model projects vote flows, simulates uncertainty, and models tactical voting seat by seat.",
        "accent": "var(--bbc-custom)",
        "date": "2026",
        "read_time": "18 min read",
    },
]


def build_post(post, prev_post, next_post):
    nb = json.load(open(NOTEBOOKS_DIR / post["notebook"], encoding="utf-8"))
    body = notebook_to_body_html(nb)
    body = fix_internal_links(body)

    prev_href, prev_label = ("index.html", "&larr; All posts") if prev_post is None else (prev_post["slug"], f"&larr; {prev_post['title']}")
    next_href, next_label = ("index.html", "All posts &rarr;") if next_post is None else (next_post["slug"], f"{next_post['title']} &rarr;")

    html_out = PAGE_TEMPLATE.format(
        title=post["title"],
        description=post["description"],
        nav=NAV.format(home_active="", blog_active="active"),
        accent=post["accent"],
        series_tag=post["series_tag"],
        dek=post["dek"],
        byline=f"{post['date']} &middot; {post['read_time']}",
        body=body,
        prev_href=prev_href, prev_label=prev_label,
        next_href=next_href, next_label=next_label,
        footer=FOOTER,
    )
    out_path = BLOG_DIR / post["slug"]
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Wrote {out_path}")


def build_blog_index():
    cards = []
    for p in POSTS:
        cards.append(f"""
        <a class="card {'accent-segments' if 'segments' in p['accent'] else 'accent-custom'}" href="{p['slug']}">
          <div class="card-tag">{p['series_tag']}</div>
          <h3>{p['title']}</h3>
          <p>{p['dek']}</p>
          <div class="card-meta"><span>{p['date']}</span><span>{p['read_time']}</span></div>
        </a>""")

    body = f"""
<div class="section">
  <div class="section-head">
    <div class="eyebrow">Research notes</div>
    <h2>Rebuilding the tribe model</h2>
  </div>
  <div class="card-grid">{''.join(cards)}</div>
</div>
"""
    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blog &middot; Elections UK</title>
<meta name="description" content="Research notes on rebuilding a UK general election forecasting model with data-driven latent voter groups.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Roboto+Condensed:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../css/site.css">
</head>
<body>
{NAV.format(home_active="", blog_active="active")}
<header class="hero" style="padding-bottom:40px;">
  <div class="kicker">Blog</div>
  <h1>Research notes</h1>
  <p class="lede">Two long-form write-ups on reverse-engineering the hand-built tribe model with
  clustering, matrix factorization, and the prediction pipeline that turns it into a forecast.</p>
</header>
{body}
{FOOTER}
</body>
</html>
"""
    (BLOG_DIR / "index.html").write_text(html_out, encoding="utf-8")
    print(f"Wrote {BLOG_DIR / 'index.html'}")


def main():
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    build_post(POSTS[0], None, POSTS[1])
    build_post(POSTS[1], POSTS[0], None)
    build_blog_index()


if __name__ == "__main__":
    main()
