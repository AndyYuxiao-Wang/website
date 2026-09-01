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

## Running locally

```
py site/serve.py
```

Then open `http://localhost:8000` (or whatever port it prints).

To rebuild the blog after editing a post:

```
py site/build_blog.py
```

## Other projects

- [UK election model](https://github.com/AndyYuxiao-Wang/uk-election-model) -
  the data pipeline and clustering research behind `site/app/`. That repo owns
  the methodology; this repo's `app/` just displays its pre-generated output.
- [House price predictor](https://socioeconomichousevaluationweb.uk/)
  ([source](https://github.com/AndyYuxiao-Wang/test)) - a separately deployed
  model estimating property value from socioeconomic profile.
