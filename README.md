# johklo.github.io

The landing page for <https://johklo.github.io/>.

It is a single static page that points at the Azure work — led by the
[Azure Product Updates Digest](https://johklo.github.io/azure-updates-digest/).

## What is here

| Path | Purpose |
| --- | --- |
| `index.html` | The landing page. Self-contained: styles are inline, no build step. |
| `.nojekyll` | Serves the files as-is; GitHub Pages skips Jekyll processing. |
| `robots.txt` | Crawl policy. |
| `google*.html` | Google Search Console site-ownership verification. |
| `LICENSE` | MIT. |

## History

This repository previously held a personal Jekyll wiki and blog. That content — and
its full commit history — now lives in a separate private repository, and this
repository was restarted from a single commit so the notes are no longer published
here.

## Local preview

No toolchain is needed:

```bash
python -m http.server 4000
# then open http://localhost:4000
```
