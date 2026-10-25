import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import unquote, urljoin, urlsplit

from test_ml_platform_series import PageLinks


ROOT = Path(__file__).resolve().parents[1]
TECH = ROOT / "content" / "docs" / "tech"
GUIDES = {
    "mlops": {
        "data-versioning", "mlflow", "tensorboard", "feast", "kubeflow",
        "bentoml", "runtime", "gitops", "monitoring", "evidently",
    },
    "llmops": {
        "ingestion-faiss", "qdrant", "pgvector", "application",
        "conversation-ui", "langfuse", "langsmith", "promptfoo",
        "deepeval", "ragas", "litellm", "vllm", "redis", "guardrails",
        "nemo-guardrails", "opentelemetry", "release", "observatory",
    },
}


@unittest.skipUnless(shutil.which("hugo"), "Hugo is required for publication tests")
class OperationsGuidesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory(prefix=".ops-test-", dir=ROOT)
        cls.addClassCleanup(directory.cleanup)
        cls.output = Path(directory.name) / "site"
        subprocess.run(
            ["hugo", "--environment", "production", "--quiet", "--minify",
             "--destination", str(cls.output)],
            cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8",
        )

    def page(self, url):
        path = self.output / unquote(urlsplit(url).path).lstrip("/")
        return path / "index.html" if path.is_dir() or url.endswith("/") else path

    def test_hubs_and_guides_are_published_and_discoverable(self):
        search = set()
        for path in self.output.glob("*.search-data*.json"):
            search.update(json.loads(path.read_text(encoding="utf-8")))
        sitemap = (self.output / "sitemap.xml").read_text(encoding="utf-8")
        tech_links = PageLinks(self.page("/docs/tech/").read_text(encoding="utf-8")).links
        for category, slugs in GUIDES.items():
            hub = f"/docs/tech/{category}/"
            self.assertIn(hub, tech_links)
            document = PageLinks(self.page(hub).read_text(encoding="utf-8"))
            self.assertGreater(document.mermaid_blocks, 0)
            for url in [hub] + [f"{hub}{slug}/" for slug in sorted(slugs)]:
                with self.subTest(url=url):
                    self.assertTrue(self.page(url).is_file())
                    self.assertIn(url, search)
                    self.assertIn(f"https://johklo.github.io{url}", sitemap)
                    if url != hub:
                        resolved = {
                            urlsplit(urljoin(f"https://johklo.github.io{hub}", href)).path
                            for href in document.links
                        }
                        self.assertIn(url, resolved)

    def test_all_guide_internal_links_and_anchors_resolve(self):
        for category, slugs in GUIDES.items():
            base = f"/docs/tech/{category}/"
            for url in [base] + [f"{base}{slug}/" for slug in sorted(slugs)]:
                for href in PageLinks(self.page(url).read_text(encoding="utf-8")).links:
                    target = urlsplit(urljoin(f"https://johklo.github.io{url}", href))
                    if target.netloc != "johklo.github.io":
                        continue
                    with self.subTest(page=url, href=href):
                        path = self.page(target.path)
                        self.assertTrue(path.is_file(), f"Broken link: {href}")
                        if target.fragment:
                            self.assertIn(
                                unquote(target.fragment),
                                PageLinks(path.read_text(encoding="utf-8")).ids,
                            )

    def test_llmops_legacy_aliases_keep_the_canonical_target(self):
        for alias in ("/wiki/llmops/", "/docs/llmops/"):
            html = self.page(alias).read_text(encoding="utf-8")
            self.assertIn("https://johklo.github.io/docs/tech/llmops/", html)

    def test_python_and_json_examples_parse(self):
        for category in GUIDES:
            for source in (TECH / category).glob("*.md"):
                text = source.read_text(encoding="utf-8")
                for language, code in re.findall(
                    r"^```(python|json)\n(.*?)^```", text, re.M | re.S
                ):
                    with self.subTest(source=source.name, language=language):
                        if language == "python":
                            ast.parse(code, filename=str(source))
                        else:
                            json.loads(code)


if __name__ == "__main__":
    unittest.main()
