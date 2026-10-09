# johklo.github.io

Source for <https://johklo.github.io/>, built with Hugo and the [Hextra](https://github.com/imfing/hextra) theme.

## What is here

| Path | Purpose |
| --- | --- |
| `content/_index.md` | Landing page: projects, docs index, Insight posts, repositories. |
| `content/docs/` | Notes in Tech / AI / Business / Book / Insight. Each folder is a sidebar category; its `_index.md` is the category page. |
| `content/about.md` | About page. |
| `static/notes/`, `static/s/` | Prebuilt static apps, copied to the site as-is. |
| `static/images/` | Images uploaded from the editor. |
| `.pages.yml` | Pages CMS editor configuration. |
| `static/google*.html`, `static/robots.txt` | Search Console verification and crawl policy. |
| `layouts/`, `assets/css/custom.css` | Small theme overrides (section list shortcode, Pretendard font). |
| `themes/hextra` | Hextra theme, pinned as a git submodule. |
| `.github/workflows/hugo.yml` | Builds and deploys to GitHub Pages on every push to `master`. |

Old `/wiki/...`, `/blog/...` and removed-category URLs redirect to their new `/docs/...` pages through each page's `aliases`.

## Editing from the site

Content is edited with [Pages CMS](https://pagescms.org/), configured in `.pages.yml`. It is a visual (WYSIWYG) editor that also takes drag-and-drop images.

- Every page has "✎ 이 문서 수정하기" at the top, which opens that document in Pages CMS. Category pages also have "+ 이 카테고리에 새 문서 만들기".
- **First-time setup:** sign in at <https://app.pagescms.org> with GitHub and install the Pages CMS GitHub App on this repository.
- **Images:** drag or paste them into the editor. They are saved to `static/images/` and served from `/images/...`.
- **Save:** each save commits to `master`, and the deploy workflow publishes it in about a minute.
- "GitHub에서 수정" opens the same file in GitHub's web editor as a fallback.

## Local preview

```bash
git submodule update --init
hugo server
# then open http://localhost:1313
```
