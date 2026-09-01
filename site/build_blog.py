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

# Non-post projects, listed on the dedicated Projects page and teased on the home page.
PROJECTS = [
    {
        "href": "app/index.html",
        "title": "UK election map",
        "dek": "Originally built to make the research above easier to explore and work with; now that I've finally got around to the frontend, it can pass as an app. Includes every UK general election since 2005, a 2029 prediction, and a "
               "what-if predictor for anyone who fancies rigging an election from the comfort "
               "of their own browser. "
               '<a href="https://github.com/AndyYuxiao-Wang/uk-election-modelling">Model source &rarr;</a>',
    },
    {
        "href": "https://socioeconomichousevaluationweb.uk/",
        "title": "House price predictor",
        "dek": "A model which will happily estimate what a property is worth from its "
               "characteristics and its neighbourhood's socioeconomic profile, and, if it's a "
               "London postcode, quietly disagree with you about it. "
               '<a href="https://github.com/AndyYuxiao-Wang/test">Source &rarr;</a>',
    },
]

NAV = """
<nav class="site-nav">
  <a class="brand" href="../index.html">UniverseWang</a>
  <a class="nav-link {home_active}" href="../index.html">Home</a>
  <a class="nav-link {blog_active}" href="index.html">Blog</a>
  <a class="nav-link projects-link {projects_active}" href="../projects.html">Projects</a>
</nav>
""".strip()

# same nav, but for pages that sit at the site root (index.html, projects.html)
NAV_HOME = """
<nav class="site-nav">
  <a class="brand" href="index.html">UniverseWang</a>
  <a class="nav-link {home_active}" href="index.html">Home</a>
  <a class="nav-link {blog_active}" href="blog/index.html">Blog</a>
  <a class="nav-link projects-link {projects_active}" href="projects.html">Projects</a>
</nav>
""".strip()

FOOTER = """
<footer class="site-footer">
  <p><a href="../index.html">home</a> &middot; <a href="index.html">blog</a> &middot;
     <a href="../projects.html">projects</a></p>
</footer>
""".strip()

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{tab_title}</title>
<meta name="description" content="{dek}">
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
        "notebook": "blog/notebooks/sorting_632_seats.ipynb",
        "slug": "clustering_con.html",
        "tab_title": "clustering_con",
        "series_tag": "Part 1 &middot; Clustering",
        "series": "uk-election",
        "series_part": 1,
        "title": "Do Britain's 632 constituencies fall into clean types?",
        "dek": "I threw the kitchen sink of clustering methods at Britain's constituencies: "
               "K-means, hierarchical clustering, DBSCAN, GMM, run across two "
               "different embeddings and scored four different ways, in the hope that at "
               "least one of them would tell me something definite. None of them quite did, "
               "and this is the post where I admit that in some detail.",
        "description": "An attempt to sort Britain's 632 constituencies into clean, tidy types using every clustering method going, and an honest account of how badly they agreed with each other.",
        "accent": "blue",
        "date": "2025-10-01",
        "read_time": "14 min read",
    },
    {
        "notebook": "blog/notebooks/political_fragmentation_and_latent_groups.ipynb",
        "slug": "nmf_con.html",
        "tab_title": "nmf_con",
        "series_tag": "Part 2 &middot; Latent groups",
        "series": "uk-election",
        "series_part": 2,
        "title": "The trouble with giving a seat one label",
        "dek": "With Uniform National Swing (UNS) as dead as a dodo, every UK election model eventually has to decide what a constituency &lsquo;is,&rsquo; "
               "part 1 found that doing so with a single label was about as "
               "accurate as describing a person by their star sign. Here we "
               "stop doing that, and start letting each of Britain's 632 seats be several "
               "different kinds of place at once.",
        "description": "On why giving a constituency a single political label stopped working, and what happened when I let each of Britain's 632 seats be a mixture of several voter archetypes instead.",
        "accent": "purple",
        "date": "2026-04-01",
        "read_time": "24 min read",
    },
    {
        "notebook": "blog/notebooks/predicting_house_prices_and_london.ipynb",
        "slug": "house_prices.html",
        "tab_title": "house_prices",
        "series_tag": "Research note",
        "title": "A more 'objective' value of a house in the UK (sans London)",
        "dek": "As a country, we do tend to obsess over how downtrodden or genteel a neighbourhood, town or city is. "
               "Here, we try to quantify that obsession, to gauge the value of a house by its objectively measured 'affluence'. "
               "And as per the timeless national joke, London does its own thing ",

        "description": "Five machine-learning models built to price UK houses get steadily better across England as they get smarter, then all hit the same wall in London, the one place that appears to be playing an entirely different game.",
        "accent": "blue-dark",
        "date": "2026-06-01",
        "read_time": "10 min read",
    },
    {
        "notebook": "blog/notebooks/the_prediction_pipeline.ipynb",
        "slug": "prediction.html",
        "tab_title": "prediction",
        "series_tag": "Part 3 &middot; Prediction",
        "series": "uk-election",
        "series_part": 3,
        "title": "How the model predicts a seat",
        "dek": "Here we detail the actual electoral predictor itself: vote flows, simulated  "
               "uncertainty, and a tactical-voting system, all to produce some hopefully-defensible seat-by-seat forecasts ",
        "description": "A stage-by-stage walkthrough of the UK election model's prediction pipeline, from projected vote flows through tactical-voting adjustments to the final seat-by-seat map, including the part that got cut for being too slow.",
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
    nb = json.load(open(SITE_DIR / post["notebook"], encoding="utf-8"))
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
        tab_title=post.get("tab_title", post["title"]),
        description=post["description"],
        nav=NAV.format(home_active="", blog_active="active", projects_active=""),
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
<meta name="description" content="Notes on whatever I'm currently building or thinking about, written with more enthusiasm than the subject strictly warrants.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Roboto+Condensed:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../css/site.css">
</head>
<body>
{NAV.format(home_active="", blog_active="active", projects_active="")}
<header class="page-header">
  <div class="page-header-inner">
    <h1>Blog</h1>
    <p class="lede">Notes on whatever it is I'm making or thinking about.</p>
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
    </li>""" for a in PROJECTS)

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Home</title>
<meta name="description" content="Personal site and blog: notes on whatever I've most recently convinced myself is worth building, from a UK election model to a house-price dissertation with opinions about London.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Roboto+Condensed:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="css/site.css">
</head>
<body>

{NAV_HOME.format(home_active="active", blog_active="", projects_active="")}

<header class="page-header">
  <div class="page-header-inner">
    <h1>Hello. Welcome to my website.</h1>
    <p class="lede">This is where I keep notes on whatever I'm working on - from data and modelling projects to research questions of increasingly questionable academic interest. </p>

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
  <p style="margin-top:16px;"><a href="projects.html">See all projects &rarr;</a></p>
</section>

<footer class="site-footer">
  <p><a href="blog/index.html">blog</a> &middot; <a href="projects.html">projects</a></p>
</footer>

</body>
</html>
"""
    (SITE_DIR / "index.html").write_text(html_out, encoding="utf-8")
    print(f"Wrote {SITE_DIR / 'index.html'}")


def build_projects_page():
    items = "".join(f"""
    <li>
      <a class="post-list-title" href="{p['href']}">{p['title']}</a>
      <p class="post-list-dek">{p['dek']}</p>
    </li>""" for p in PROJECTS)

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Projects</title>
<meta name="description" content="Things I've built alongside the blog: an interactive UK election map, and a live house-price predictor that will tell you, bluntly, what your house is worth.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Roboto+Condensed:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="css/site.css">
</head>
<body>
{NAV_HOME.format(home_active="", blog_active="", projects_active="active")}
<header class="page-header">
  <div class="page-header-inner">
    <h1>Projects</h1>
    <p class="lede">The things I built instead of just writing about them: for anyone who'd rather play around with buttons than read nine sections of
      methodology.</p>
  </div>
</header>

<section class="section">
  <ul class="post-list">{items}
  </ul>
</section>

<footer class="site-footer">
  <p><a href="index.html">home</a> &middot; <a href="blog/index.html">blog</a></p>
</footer>
</body>
</html>
"""
    (SITE_DIR / "projects.html").write_text(html_out, encoding="utf-8")
    print(f"Wrote {SITE_DIR / 'projects.html'}")


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
    build_projects_page()


if __name__ == "__main__":
    main()
