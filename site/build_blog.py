# -*- coding: utf-8 -*-
"""Builds the whole site: renders the notebook-derived research posts, any plain-Markdown
posts dropped in blog/posts/, the blog index, and the home page — all from one source of
truth (this file's NOTEBOOK_POSTS list, plus front matter in blog/posts/*.md).

To add a new post, see blog/posts/README.md — in short: drop a .md file in blog/posts/ and
re-run this script. No HTML editing required.

Re-run after editing a notebook, adding/editing a post in blog/posts/, or changing this file:
    py build_blog.py
"""
import html
import json
import re
from datetime import date, datetime
from pathlib import Path

import markdown as md
import yaml

SITE_DIR = Path(__file__).resolve().parent
ROOT = SITE_DIR.parent
BLOG_DIR = SITE_DIR / "blog"
POSTS_DIR = BLOG_DIR / "posts"

MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists"]

# Number of posts shown on the home page before "see all posts" takes over.
HOME_PAGE_POST_LIMIT = 3

# accent keyword (used in front matter / NOTEBOOK_POSTS below) -> CSS variable
ACCENTS = {
    "blue": "var(--bbc-blue)",
    "blue-dark": "var(--bbc-blue-dark)",
    "purple": "var(--bbc-segments)",
    "teal": "var(--bbc-custom)",
}

# series id -> display name, used in the "Part of a series on ..." cross-link line.
# Register a new series here the first time a post uses it.
SERIES_TITLES = {
    "uk-election": "the UK election model",
}

# Non-post projects linked from the home page's "Also here" section.
ALSO_HERE = [
    {
        "href": "app/index.html",
        "title": "UK election map",
        "dek": "An interactive constituency map built alongside the blog posts above &mdash; "
               "every UK general election since 2005, a 2029 prediction, and a custom "
               "what-if predictor.",
    },
    {
        "href": "https://socioeconomichousevaluationweb.uk/",
        "title": "House price predictor",
        "dek": "A live Random Forest model, from the house-price dissertation post, that "
               "estimates a sale price from a property's characteristics and its LSOA's "
               "socioeconomic profile.",
    },
]

NAV = """
<nav class="site-nav">
  <!-- TODO: swap this for your own name -->
  <a class="brand" href="../index.html">MY SITE</a>
  <a class="nav-link {home_active}" href="../index.html">Home</a>
  <a class="nav-link {blog_active}" href="index.html">Blog</a>
  <a class="nav-link app-link" href="../app/index.html">UK Election Map</a>
</nav>
""".strip()

# same nav, but for site/index.html itself, which sits one level up from blog/ pages
NAV_HOME = """
<nav class="site-nav">
  <!-- TODO: swap this for your own name -->
  <a class="brand" href="index.html">MY SITE</a>
  <a class="nav-link active" href="index.html">Home</a>
  <a class="nav-link" href="blog/index.html">Blog</a>
  <a class="nav-link app-link" href="app/index.html">UK Election Map</a>
</nav>
""".strip()

FOOTER = """
<footer class="site-footer">
  <p><a href="../index.html">home</a> &middot; <a href="index.html">blog</a> &middot;
     <a href="../app/index.html">election map</a></p>
</footer>
""".strip()

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
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
  {series_crosslinks}
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


# ----------------------------------------------------------------------------
# Notebook-derived posts (unchanged mechanism: these render live-executed
# research notebooks, not hand-written prose, so they stay data-driven).
# ----------------------------------------------------------------------------

NOTEBOOK_POSTS = [
    {
        "notebook": "clustering/notebooks/sorting_632_seats.ipynb",
        "slug": "sorting-632-seats.html",
        "series_tag": "Part 1 &middot; Clustering",
        "series": "uk-election",
        "series_part": 1,
        "title": "Trying to sort 632 seats into types",
        "dek": "Running the full standard toolkit &mdash; K-means, HAC, DBSCAN and GMM, across "
               "PCA and UMAP, scored on four metrics &mdash; on Britain's constituencies, and "
               "reporting honestly on where it falls short.",
        "description": "A full PCA/UMAP x clustering-algorithm x validation-metric sweep on UK constituency demographics, and what its limits reveal.",
        "accent": "blue",
        "date": "2025-10-01",
        "read_time": "14 min read",
    },
    {
        "notebook": "clustering/notebooks/political_fragmentation_and_latent_groups.ipynb",
        "slug": "political-fragmentation-and-latent-groups.html",
        "series_tag": "Part 2 &middot; Latent groups",
        "series": "uk-election",
        "series_part": 2,
        "title": "One seat, many voters",
        "dek": "Why single-category constituency models are running out of road, and what "
               "unmixing 632 seats&rsquo; census composition into a handful of shared archetypes "
               "gets us instead.",
        "description": "Rebuilding the UK election tribe model on data-derived categories instead of hand-assigned labels, from clustering technique to per-seat formula.",
        "accent": "purple",
        "date": "2026-04-01",
        "read_time": "24 min read",
    },
    {
        "notebook": "notebooks/predicting_house_prices_and_london.ipynb",
        "slug": "predicting-house-prices-and-london.html",
        "series_tag": "Research note",
        "title": "What a house is worth, and why London breaks the curve",
        "dek": "A dissertation project's baseline house-price model finds sensible, well-behaved "
               "relationships everywhere &mdash; until it hits the one UK housing market that "
               "isn't behaving like the rest of the country.",
        "description": "A machine-learning house-price model built from census and deprivation data, and what its errors reveal about London's outlier prices.",
        "accent": "blue-dark",
        "date": "2026-06-01",
        "read_time": "10 min read",
    },
    {
        "notebook": "clustering/notebooks/the_prediction_pipeline.ipynb",
        "slug": "the-prediction-pipeline.html",
        "series_tag": "Part 3 &middot; Prediction",
        "series": "uk-election",
        "series_part": 3,
        "title": "From groups to seats",
        "dek": "Flows, uncertainty, and tactical voting &mdash; opening up the pipeline that turns "
               "any group structure into seat-by-seat forecasts.",
        "description": "How the UK election model projects vote flows, simulates uncertainty, and models tactical voting seat by seat.",
        "accent": "teal",
        "date": "2026-08-01",
        "read_time": "18 min read",
    },
]

# Every .ipynb referenced above gets its cross-links to the others rewritten to point at the
# rendered .html slug instead, keyed by notebook filename (not full path).
_NOTEBOOK_LINK_TARGETS = {Path(p["notebook"]).name: p["slug"] for p in NOTEBOOK_POSTS}


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
    # skip cell 0: the notebook's own title/dek cell duplicates the post-header
    # template (title, dek, series tag) already rendered above.
    for cell in nb["cells"][1:]:
        if cell["cell_type"] == "markdown":
            parts.append(render_markdown_cell(cell["source"]))
        elif cell["cell_type"] == "code":
            src = "".join(cell["source"]).strip()
            if not src:
                continue
            parts.append(render_code_cell(cell))
    body = "\n\n".join(parts)
    for notebook_name, slug in _NOTEBOOK_LINK_TARGETS.items():
        body = body.replace(notebook_name, slug)
    return body


def load_notebook_post(post):
    nb = json.load(open(ROOT / post["notebook"], encoding="utf-8"))
    return {
        **post,
        "accent": ACCENTS[post["accent"]],
        "body_html": notebook_to_body_html(nb),
    }


# ----------------------------------------------------------------------------
# Plain-Markdown posts: blog/posts/*.md, front matter + Markdown body.
# See blog/posts/README.md for the format.
# ----------------------------------------------------------------------------

WORDS_PER_MINUTE = 200
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n(.*)$", re.DOTALL)


def slugify_filename(path):
    return path.stem + ".html"


def estimate_read_time(body_text):
    word_count = len(re.findall(r"\S+", body_text))
    minutes = max(1, round(word_count / WORDS_PER_MINUTE))
    return f"{minutes} min read"


def load_markdown_post(path):
    raw = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(raw)
    if not match:
        raise ValueError(f"{path.name}: missing '---' front matter block (see blog/posts/README.md)")
    front_matter_text, body_text = match.groups()
    meta = yaml.safe_load(front_matter_text) or {}

    for required in ("title", "date"):
        if required not in meta:
            raise ValueError(f"{path.name}: front matter is missing required field '{required}'")

    post_date = meta["date"]
    if isinstance(post_date, (date, datetime)):
        post_date = post_date.strftime("%Y-%m-%d")

    accent_key = meta.get("accent", "blue")
    if accent_key not in ACCENTS:
        raise ValueError(f"{path.name}: accent '{accent_key}' must be one of {list(ACCENTS)}")

    dek = meta.get("dek", "")
    series = meta.get("series")
    series_part = meta.get("series_part")
    if series:
        series_tag = f"Part {series_part} &middot; {SERIES_TITLES.get(series, series)}"
    else:
        series_tag = "Post"

    return {
        "slug": slugify_filename(path),
        "title": meta["title"],
        "dek": dek,
        "description": meta.get("description", dek),
        "accent": ACCENTS[accent_key],
        "date": post_date,
        "read_time": meta.get("read_time") or estimate_read_time(body_text),
        "series": series,
        "series_part": series_part,
        "series_tag": series_tag,
        "body_html": md.markdown(body_text, extensions=MD_EXTENSIONS),
    }


def load_markdown_posts():
    posts = []
    if not POSTS_DIR.exists():
        return posts
    for path in sorted(POSTS_DIR.glob("*.md")):
        if path.name == "README.md" or path.name.startswith("_"):
            continue
        posts.append(load_markdown_post(path))
    return posts


# ----------------------------------------------------------------------------
# Shared rendering: once every post (notebook- or markdown-sourced) is a plain
# dict with the same keys, they're all rendered the same way.
# ----------------------------------------------------------------------------

def display_date(iso_date):
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%B %Y")


def series_crosslinks_html(post, all_posts):
    series = post.get("series")
    if not series:
        return ""
    members = sorted((p for p in all_posts if p.get("series") == series), key=lambda p: p["series_part"])
    parts = []
    for m in members:
        label = f"Part {m['series_part']}"
        if m["slug"] == post["slug"]:
            parts.append(f'<span class="series-crosslink-current">{label}</span>')
        else:
            parts.append(f'<a href="{m["slug"]}">{label}</a>')
    return (f'<p class="series-crosslinks">Part of a series on {SERIES_TITLES[series]}: '
            + " &middot; ".join(parts) + "</p>")


def build_post(post, prev_post, next_post, all_posts):
    prev_href, prev_label = ("index.html", "&larr; All posts") if prev_post is None else (prev_post["slug"], f"&larr; {prev_post['title']}")
    next_href, next_label = ("index.html", "All posts &rarr;") if next_post is None else (next_post["slug"], f"{next_post['title']} &rarr;")

    html_out = PAGE_TEMPLATE.format(
        title=post["title"],
        description=post["description"],
        nav=NAV.format(home_active="", blog_active="active"),
        accent=post["accent"],
        series_tag=post["series_tag"],
        dek=post["dek"],
        byline=f"{display_date(post['date'])} &middot; {post['read_time']}",
        series_crosslinks=series_crosslinks_html(post, all_posts),
        body=post["body_html"],
        prev_href=prev_href, prev_label=prev_label,
        next_href=next_href, next_label=next_label,
        footer=FOOTER,
    )
    out_path = BLOG_DIR / post["slug"]
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Wrote {out_path}")


def post_list_item_html(p, link_prefix=""):
    return f"""
    <li>
      <a class="post-list-title" href="{link_prefix}{p['slug']}">{p['title']}</a>
      <p class="post-list-dek">{p['dek']}</p>
      <div class="post-list-meta"><span>{display_date(p['date'])}</span><span>{p['series_tag']}</span><span>{p['read_time']}</span></div>
    </li>"""


def build_blog_index(newest_first):
    items = [post_list_item_html(p) for p in newest_first]

    body = f"""
<section class="section">
  <ul class="post-list">{''.join(items)}
  </ul>
</section>
"""
    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blog</title>
<meta name="description" content="Notes on whatever I'm currently building or thinking about.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Roboto+Condensed:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../css/site.css">
</head>
<body>
{NAV.format(home_active="", blog_active="active")}
<header class="page-header">
  <div class="page-header-inner">
    <h1>Blog</h1>
    <p class="lede">Notes on whatever I'm currently building or thinking about &mdash; a UK
      election model, a dissertation project, and whatever comes next.</p>
  </div>
</header>
{body}
{FOOTER}
</body>
</html>
"""
    (BLOG_DIR / "index.html").write_text(html_out, encoding="utf-8")
    print(f"Wrote {BLOG_DIR / 'index.html'}")


def build_home_page(newest_first):
    shown = newest_first[:HOME_PAGE_POST_LIMIT]
    items = [post_list_item_html(p, link_prefix="blog/") for p in shown]

    see_all = ""
    if len(newest_first) > HOME_PAGE_POST_LIMIT:
        see_all = '\n  <p style="margin-top:16px;"><a href="blog/index.html">See all posts &rarr;</a></p>'

    also_here = "".join(f"""
    <li>
      <a class="post-list-title" href="{a['href']}">{a['title']}</a>
      <p class="post-list-dek">{a['dek']}</p>
    </li>""" for a in ALSO_HERE)

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Home</title>
<meta name="description" content="Personal site and blog - notes on whatever I'm currently building, from a UK election model to a house-price dissertation.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Roboto+Condensed:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="css/site.css">
</head>
<body>

{NAV_HOME}

<header class="page-header">
  <div class="page-header-inner">
    <h1>Hi, I'm building things and writing about them</h1>
    <p class="lede">This is where I keep notes on whatever I'm currently working on &mdash; a UK
      general election model, a dissertation project, and whatever comes next.</p>
  </div>
</header>

<section class="section">
  <h2>Latest posts</h2>
  <ul class="post-list">{''.join(items)}
  </ul>{see_all}
</section>

<section class="section">
  <h2>Also here</h2>
  <ul class="post-list">{also_here}
  </ul>
</section>

<footer class="site-footer">
  <p><a href="blog/index.html">blog</a> &middot; <a href="app/index.html">election map</a></p>
</footer>

</body>
</html>
"""
    (SITE_DIR / "index.html").write_text(html_out, encoding="utf-8")
    print(f"Wrote {SITE_DIR / 'index.html'}")


def main():
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    posts = [load_notebook_post(p) for p in NOTEBOOK_POSTS] + load_markdown_posts()
    posts.sort(key=lambda p: p["date"])  # oldest first: canonical reading / prev-next order

    for i, post in enumerate(posts):
        prev_post = posts[i - 1] if i > 0 else None
        next_post = posts[i + 1] if i < len(posts) - 1 else None
        build_post(post, prev_post, next_post, posts)

    newest_first = list(reversed(posts))
    build_blog_index(newest_first)
    build_home_page(newest_first)


if __name__ == "__main__":
    main()
