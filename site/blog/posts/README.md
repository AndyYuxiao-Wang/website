# Writing a new post

Drop a new `.md` file in this folder and run `py build_blog.py` from `site/` — that's it (the
build script needs the `markdown` and `pyyaml` packages: `py -m pip install markdown pyyaml`
if a fresh machine doesn't have them already). The
file name becomes the post's URL (`my-post.md` -> `my-post.html`), so name it what you want the
link to be.

This `README.md` file itself is ignored by the build script, and so is anything starting with
an underscore (`_draft.md`) — use that prefix to keep a post out of the site while you're still
writing it.

## Format

Every post is plain Markdown with a short header block (called "front matter") at the top,
between two `---` lines:

```
---
title: "One seat, many voters"
date: 2026-09-15
dek: "A one-sentence subtitle, shown under the title and in the post list."
description: "A one-sentence summary for search engines and link previews."
accent: blue
---

Start writing here. This is normal Markdown: **bold**, *italic*, [links](https://example.com),
bullet lists, and:

## Headings

use two hashes for a section heading (the title above already gives you the page's H1, so
start your own headings at `##`).

## Code and tables

\`\`\`python
print("fenced code blocks work as you'd expect")
\`\`\`

| Column | Value |
|---|---|
| Like this | 42 |
```

### Front matter fields

- `title` (required) — the post's headline.
- `date` (required) — `YYYY-MM-DD`. Controls where the post lands in the chronological
  list and its prev/next neighbours. Doesn't need to be today; back- or post-date it as you like.
- `dek` (optional) — a one-sentence subtitle under the title and in listings. Leave it out and
  the post just won't show one.
- `description` (optional) — meta description text (search engines, link previews). Falls back
  to `dek` if omitted.
- `accent` (optional) — one of `blue`, `purple`, `teal`, `blue-dark`. Just picks which of the
  site's existing accent colours this post uses. Defaults to `blue`.
- `read_time` (optional) — e.g. `"8 min read"`. If you leave it out, it's estimated
  automatically from the word count.
- `series` / `series_part` (optional) — only set these if the post is one part of a numbered
  series (like the UK election posts are). `series` is a short id shared by every part (e.g.
  `uk-election`); `series_part` is that post's number in the series. Register the series name
  in `SERIES_TITLES` at the top of `build_blog.py` the first time you use a new one.

That's the whole format — no other file needs editing. The homepage and the blog index page
are both regenerated automatically from whatever posts exist when you run `py build_blog.py`.
