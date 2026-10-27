import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import quote, unquote, urljoin, urlsplit

from test_ml_platform_series import PageLinks


ROOT = Path(__file__).resolve().parents[1]
SERIES_URL = "/docs/tech/ops/mlops/labs/"
OVERVIEW_URL = f"{SERIES_URL}mlflow-aml-overview/"
LEGACY_URLS = (
    "/docs/tech/2026-10-21-mlflow-to-azure-machine-learning/",
    "/docs/tech/mlflow-azure-machine-learning/",
)
SOURCE = ROOT / "content" / SERIES_URL.lstrip("/")


@unittest.skipUnless(shutil.which("hugo"), "Hugo is required for publication tests")
class MLflowLearningPublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory(
            prefix=".mlflow-learning-test-", dir=ROOT
        )
        cls.addClassCleanup(directory.cleanup)
        cls.output = Path(directory.name) / "site"
        subprocess.run(
            [
                "hugo", "--environment", "production", "--quiet", "--minify",
                "--destination", str(cls.output),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        cls.urls = [
            f"{SERIES_URL}{quote(path.parent.name, safe='')}/"
            for path in sorted(
                (cls.output / SERIES_URL.lstrip("/")).glob("*/index.html")
            )
            if "http-equiv=refresh" not in path.read_text(encoding="utf-8")
        ]

    def page_path(self, url):
        url_path = unquote(urlsplit(url).path)
        path = self.output / url_path.lstrip("/")
        return path / "index.html" if url_path.endswith("/") else path

    def source_path(self, parsed):
        prefix = "https://github.com/johklo/johklo.github.io/edit/master/"
        links = {link for link in parsed.links if link.startswith(prefix)}
        self.assertEqual(len(links), 1)
        source = ROOT / unquote(next(iter(links))[len(prefix):])
        self.assertTrue(source.is_relative_to(SOURCE))
        self.assertTrue(source.is_file())
        return source

    def test_series_navigation_search_and_legacy_redirect(self):
        self.assertTrue(self.urls, "No learning articles were published")
        category = PageLinks(
            self.page_path(SERIES_URL).read_text(encoding="utf-8")
        )
        weighted = []
        for url in self.urls:
            position = category.links.index(url)
            parsed = PageLinks(
                self.page_path(url).read_text(encoding="utf-8")
            )
            source = self.source_path(parsed).read_text(encoding="utf-8")
            weight = re.search(r"(?m)^weight:\s*([+-]?\d+)\s*$", source)
            if weight and int(weight[1]) != 0:
                weighted.append((position, int(weight[1])))
        weights = [weight for _, weight in sorted(weighted)]
        self.assertEqual(weights, sorted(weights))
        ops = PageLinks(
            self.page_path("/docs/tech/ops/").read_text(encoding="utf-8")
        )
        resolved = {
            urlsplit(urljoin("https://johklo.github.io/docs/tech/ops/", href)).path
            for href in ops.links
        }
        self.assertIn(SERIES_URL, resolved)

        indexes = list(self.output.glob("*.search-data*.json"))
        self.assertTrue(indexes, "Search index was not generated")
        indexed = set()
        for path in indexes:
            data = json.loads(path.read_text(encoding="utf-8"))
            for legacy in LEGACY_URLS:
                self.assertNotIn(legacy, data)
            indexed.update(url for url in data if url.startswith(SERIES_URL))
        self.assertEqual(indexed, {SERIES_URL, *self.urls})

        for legacy in LEGACY_URLS:
            redirect = self.page_path(legacy).read_text(encoding="utf-8")
            self.assertIn("http-equiv=refresh", redirect)
            self.assertIn(f"url=https://johklo.github.io{OVERVIEW_URL}", redirect)

    def test_series_links_and_cms_actions_resolve(self):
        for url in [SERIES_URL, *self.urls]:
            parsed = PageLinks(
                self.page_path(url).read_text(encoding="utf-8")
            )
            with self.subTest(page=url):
                if url == SERIES_URL:
                    self.assertTrue(any(
                        "/file/mlops-labs-index" in link
                        for link in parsed.links
                    ))
                    self.assertTrue(any(
                        "/collection/mlops-labs/new" in link
                        for link in parsed.links
                    ))
                else:
                    source = self.source_path(parsed)
                    filename = quote(
                        source.relative_to(ROOT).as_posix(), safe=""
                    )
                    self.assertTrue(any(
                        f"/collection/mlops-labs/edit/{filename}"
                        in link for link in parsed.links
                    ))

            for href in parsed.links:
                target = urlsplit(
                    urljoin(f"https://johklo.github.io{url}", href)
                )
                if target.netloc != "johklo.github.io":
                    continue
                if not target.path.startswith(SERIES_URL):
                    continue
                with self.subTest(page=url, link=href):
                    path = self.page_path(target.path)
                    self.assertTrue(path.is_file(), f"Broken link: {href}")
                    if target.fragment:
                        ids = PageLinks(
                            path.read_text(encoding="utf-8")
                        ).ids
                        self.assertIn(unquote(target.fragment), ids)
