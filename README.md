# johklo.github.io

Source for <https://johklo.github.io/>, built with Hugo and the [Hextra](https://github.com/imfing/hextra) theme.

## What is here

| Path | Purpose |
| --- | --- |
| `content/_index.md` | Landing page: projects, docs index, recent posts, repositories. |
| `content/docs/` | Notes. Each folder is a sidebar category; its `_index.md` is the category page. |
| `content/blog/` | Blog posts. |
| `content/about.md` | About page. |
| `static/appraiser-study/`, `static/s/` | Prebuilt static apps, copied to the site as-is. |
| `static/google*.html`, `static/robots.txt` | Search Console verification and crawl policy. |
| `layouts/`, `assets/css/custom.css` | Small theme overrides (section list shortcode, Pretendard font). |
| `themes/hextra` | Hextra theme, pinned as a git submodule. |
| `.github/workflows/hugo.yml` | Builds and deploys to GitHub Pages on every push to `master`. |

Old `/wiki/...` URLs redirect to their new `/docs/...` or `/blog/...` pages through each page's `aliases`.

## Local preview

```bash
git submodule update --init
hugo server
# then open http://localhost:1313
```
