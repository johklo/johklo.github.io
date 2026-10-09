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

## Editing from the site

- **Edit:** every page has a "GitHub에서 편집하기" link (right column) that opens the file in GitHub's web editor.
- **Create:** every category page (`/docs/<category>/`, `/blog/`) has a "+ 이 카테고리에 새 문서 만들기" link that opens a new file in that folder with front matter prefilled. Rename `new-doc.md` (it becomes the URL) before committing.
- Committing to `master` in the web editor triggers the deploy workflow, and the change is live in about a minute.

## Local preview

```bash
git submodule update --init
hugo server
# then open http://localhost:1313
```
