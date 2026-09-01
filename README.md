# UniverseWang

Personal site and blog: a static, hand-written frontend (no framework) covering
data/modelling projects and the writing behind them.

## Structure

- `site/` - the site itself
  - `index.html`, `projects.html` - home and projects pages
  - `blog/` - blog index, posts, and `blog/posts/README.md` for the front-matter
    format used to author new posts
  - `app/` - the UK election map, an interactive constituency-by-constituency
    results viewer (2005-2024 elections plus a 2029 projection and a what-if
    predictor)
  - `css/`, `js/` - shared site styling and scripts
  - `build_blog.py` - builds `blog/` pages from the markdown posts
  - `serve.py` - a small local dev server

## Adding posts

To add a post, put the new post in `blog/notebooks` for a notebook or `blog/posts` for a markdown file.

To rebuild the blog after editing or adding a post:

```
py site/build_blog.py
```
