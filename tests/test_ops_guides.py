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
OPS = "/docs/tech/ops/"
PRIMERS = {"mlflow", "feast", "kubeflow-pipelines", "bentoml"}
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
        self.assertIn(OPS, tech_links)
        ops_links = {
            urlsplit(urljoin(f"https://johklo.github.io{OPS}", href)).path
            for href in PageLinks(self.page(OPS).read_text(encoding="utf-8")).links
        }
        for category, slugs in GUIDES.items():
            hub = f"{OPS}{category}/"
            self.assertIn(hub, ops_links)
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
            base = f"{OPS}{category}/"
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

    def test_legacy_addresses_redirect_to_the_ops_section(self):
        redirects = {
            "/wiki/llmops/": f"{OPS}llmops/",
            "/docs/llmops/": f"{OPS}llmops/",
            "/docs/tech/llmops/": f"{OPS}llmops/",
            "/docs/tech/llmops/qdrant/": f"{OPS}llmops/qdrant/",
            "/docs/tech/mlops/": f"{OPS}mlops/",
            "/docs/tech/mlops/feast/": f"{OPS}mlops/feast/",
        }
        for alias, target in redirects.items():
            with self.subTest(alias=alias):
                html = self.page(alias).read_text(encoding="utf-8")
                self.assertIn(f"https://johklo.github.io{target}", html)

    def test_tool_primers_are_published_beneath_the_basics_hub(self):
        hub = f"{OPS}mlops/basics/"
        document = PageLinks(self.page(hub).read_text(encoding="utf-8"))
        resolved = {
            urlsplit(urljoin(f"https://johklo.github.io{hub}", href)).path
            for href in document.links
        }
        for slug in sorted(PRIMERS):
            url = f"{hub}{slug}/"
            with self.subTest(primer=slug):
                self.assertIn(url, resolved)
                primer = self.page(url).read_text(encoding="utf-8")
                source = (TECH / "ops" / "mlops" / "basics" / f"{slug}.md").read_text(encoding="utf-8")
                self.assertNotIn("\u00b7", source)
                for href in PageLinks(primer).links:
                    target = urlsplit(urljoin(f"https://johklo.github.io{url}", href))
                    if target.netloc == "johklo.github.io":
                        self.assertTrue(self.page(target.path).is_file(), href)

    def test_python_and_json_examples_parse(self):
        for folder in ("ops/mlops", "ops/llmops", "ops/mlops/basics"):
            for source in (TECH / folder).glob("*.md"):
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
