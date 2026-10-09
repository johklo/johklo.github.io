# johklo.github.io

Source for <https://johklo.github.io/>, built with Hugo and the [Hextra](https://github.com/imfing/hextra) theme.

## What is here

| Path | Purpose |
| --- | --- |
| `content/_index.md` | Landing page: projects, docs index, Insight posts, repositories. |
| `content/docs/` | Notes in Tech / AI / Business / Book / Insight. Each folder is a sidebar category; its `_index.md` is the category page. |
| `content/about.md` | About page. |
| `static/appraiser-study/`, `static/s/` | Prebuilt static apps, copied to the site as-is. |
| `static/google*.html`, `static/robots.txt` | Search Console verification and crawl policy. |
| `layouts/`, `assets/css/custom.css` | Small theme overrides (section list shortcode, Pretendard font). |
| `themes/hextra` | Hextra theme, pinned as a git submodule. |
| `.github/workflows/hugo.yml` | Builds and deploys to GitHub Pages on every push to `master`. |

Old `/wiki/...`, `/blog/...` and removed-category URLs redirect to their new `/docs/...` pages through each page's `aliases`.

## Editing from the site

Every page has an "✎ 이 문서 수정하기" link at the top that opens it in the in-site editor at `/admin/` ([Sveltia CMS](https://sveltiacms.app/), configured in `static/admin/config.yml`). Category pages also have "+ 이 카테고리에 새 문서 만들기".

- **Sign in:** choose "액세스 토큰으로 로그인" and paste a GitHub fine-grained personal access token limited to this repository with **Contents: Read and write**. The "GitHub으로 로그인" button needs an OAuth server and is not set up.
- **Save:** the editor commits straight to `master`, and the deploy workflow publishes the change in about a minute.
- **Images** uploaded in the editor go to `static/images/`.
- "GitHub에서 수정" next to it opens the same file in GitHub's web editor as a fallback.

## Local preview

```bash
git submodule update --init
hugo server
# then open http://localhost:1313
```
