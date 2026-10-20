import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import quote, unquote, urljoin, urlsplit

from test_ml_platform_series import PageLinks


ROOT = Path(__file__).resolve().parents[1]
SERIES_URL = "/docs/tech/ai-agents-and-applications/"
SOURCE = ROOT / "content" / SERIES_URL.lstrip("/")


@unittest.skipUnless(shutil.which("hugo"), "Hugo is required for publication tests")
class AIAgentsPublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory(
            prefix=".ai-agents-test-", dir=ROOT
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
        cls.articles = sorted(SOURCE.glob("[0-9][0-9]-*.md"))
        cls.urls = [
            f"{SERIES_URL}{article.stem}/" for article in cls.articles
        ]

    def page_path(self, url):
        url_path = unquote(urlsplit(url).path)
        path = self.output / url_path.lstrip("/")
        return path / "index.html" if url_path.endswith("/") else path

    def test_all_chapters_are_published_in_order_and_indexed(self):
        self.assertEqual(
            [int(article.name[:2]) for article in self.articles],
            list(range(15)),
        )
        category = PageLinks(
            self.page_path(SERIES_URL).read_text(encoding="utf-8")
        )
        positions = []
        for url in self.urls:
            with self.subTest(page=url):
                self.assertTrue(self.page_path(url).is_file())
                positions.append(category.links.index(url))
        self.assertEqual(positions, sorted(positions))

        indexes = list(self.output.glob("*.search-data*.json"))
        self.assertTrue(indexes)
        indexed = set()
        for path in indexes:
            data = json.loads(path.read_text(encoding="utf-8"))
            indexed.update(url for url in data if url.startswith(SERIES_URL))
        self.assertEqual(indexed, {SERIES_URL, *self.urls})

        sitemap = (self.output / "sitemap.xml").read_text(encoding="utf-8")
        feed = self.page_path(SERIES_URL + "index.xml").read_text(
            encoding="utf-8"
        )
        for url in self.urls:
            self.assertIn(url, sitemap)
            self.assertIn(url, feed)

        tech = PageLinks(
            self.page_path("/docs/tech/").read_text(encoding="utf-8")
        )
        self.assertIn(SERIES_URL, tech.links)

    def test_series_links_images_and_cms_actions_resolve(self):
        used_images = set()
        for url in [SERIES_URL, *self.urls]:
            document = self.page_path(url).read_text(encoding="utf-8")
            parsed = PageLinks(document)
            if url == SERIES_URL:
                self.assertTrue(any(
                    "/file/ai-agents-and-applications-index" in link
                    for link in parsed.links
                ))
                self.assertTrue(any(
                    "/collection/ai-agents-and-applications/new" in link
                    for link in parsed.links
                ))
            else:
                slug = url.rstrip("/").rsplit("/", 1)[-1]
                filename = quote(
                    f"content/docs/tech/ai-agents-and-applications/{slug}.md",
                    safe="",
                )
                self.assertTrue(any(
                    f"/collection/ai-agents-and-applications/edit/{filename}"
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
                    self.assertTrue(path.is_file())
                    if target.fragment:
                        ids = PageLinks(path.read_text(encoding="utf-8")).ids
                        self.assertIn(unquote(target.fragment), ids)

            for image in parsed.images:
                source = image.get("src", "")
                if not source.startswith(
                    "/images/ai-agents-and-applications/"
                ):
                    continue
                with self.subTest(image=source):
                    self.assertTrue(image.get("alt", "").strip())
                    self.assertIn(
                        "AI Agents and Applications",
                        " ".join(parsed.captions),
                    )
                    original = ROOT / "static" / urlsplit(source).path.lstrip("/")
                    self.assertEqual(
                        self.page_path(source).read_bytes(),
                        original.read_bytes(),
                    )
                    used_images.add(original)

        self.assertEqual(
            used_images,
            set((ROOT / "static" / "images" / "ai-agents-and-applications").glob("*.png")),
        )

    def test_new_book_content_excludes_personalization_and_source_documents(self):
        for article in SOURCE.glob("*.md"):
            text = article.read_text(encoding="utf-8")
            with self.subTest(article=article.name):
                self.assertNotRegex(text, r"(?i)\(for [^)]+\)")
        for path in self.output.rglob("*"):
            self.assertNotIn(path.suffix.lower(), {".pdf", ".epub"})
