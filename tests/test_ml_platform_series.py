import json
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import unquote, urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SERIES_URL = "/docs/tech/machine-learning-platform-engineering/"
SOURCE = ROOT / "content" / SERIES_URL.lstrip("/")


class PageLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.ids = set()
        self.images = []
        self.captions = []
        self.in_caption = False
        self.in_reading_state = False
        self.reading_state = ""
        self.scripts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "img":
            self.images.append(attrs)
        if tag == "figcaption":
            self.in_caption = True
        if tag == "script":
            self.scripts.append(attrs)
            self.in_reading_state = "data-reading-state" in attrs

    def handle_endtag(self, tag):
        if tag == "figcaption":
            self.in_caption = False
        if tag == "script":
            self.in_reading_state = False

    def handle_data(self, data):
        if self.in_caption:
            self.captions.append(data)
        if self.in_reading_state:
            self.reading_state += data


@unittest.skipUnless(shutil.which("hugo"), "Hugo is required for publication tests")
class MLPlatformPublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory(
            prefix=".ml-platform-test-", dir=ROOT
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
        cls.articles = {
            path.stem: int(path.name[:2])
            for path in SOURCE.glob("[0-9][0-9]-*.md")
        }
        cls.visible = {
            slug for slug, chapter in cls.articles.items() if chapter <= 3
        }
        cls.hidden = cls.articles.keys() - cls.visible

    def page_path(self, url):
        relative = unquote(url).lstrip("/")
        path = self.output / relative
        return path / "index.html" if url.endswith("/") else path

    def test_only_overview_and_first_three_chapters_are_published(self):
        self.assertEqual(set(self.articles.values()), set(range(14)))
        for slug in self.articles:
            with self.subTest(slug=slug):
                self.assertEqual(
                    self.page_path(f"{SERIES_URL}{slug}/").exists(),
                    slug in self.visible,
                )

        category = self.page_path(SERIES_URL).read_text(encoding="utf-8")
        links = PageLinks(category).links
        for slug in self.visible:
            self.assertIn(f"{SERIES_URL}{slug}/", links)

        for path in self.output.rglob("*"):
            if path.suffix not in {".html", ".xml", ".json"}:
                continue
            text = path.read_text(encoding="utf-8")
            for slug in self.hidden:
                self.assertNotIn(
                    f"{SERIES_URL}{slug}/", text,
                    f"Unpublished chapter exposed in {path.relative_to(self.output)}",
                )

        indexes = list(self.output.glob("*.search-data*.json"))
        self.assertTrue(indexes, "Search index was not generated")
        indexed = set()
        for path in indexes:
            data = json.loads(path.read_text(encoding="utf-8"))
            indexed.update(url for url in data if url.startswith(SERIES_URL))
        self.assertEqual(
            indexed,
            {SERIES_URL} | {
                f"{SERIES_URL}{slug}/" for slug in self.visible
            },
        )

    def test_published_series_links_and_section_anchors_resolve(self):
        pages = [SERIES_URL] + [
            f"{SERIES_URL}{slug}/" for slug in sorted(self.visible)
        ]
        for url in pages:
            document = self.page_path(url).read_text(encoding="utf-8")
            for href in PageLinks(document).links:
                target = urlsplit(urljoin(f"https://johklo.github.io{url}", href))
                if target.netloc != "johklo.github.io":
                    continue
                if not target.path.startswith(SERIES_URL):
                    continue
                with self.subTest(page=url, link=href):
                    path = self.page_path(target.path)
                    self.assertTrue(path.is_file(), f"Broken link: {href}")
                    if target.fragment:
                        ids = PageLinks(path.read_text(encoding="utf-8")).ids
                        self.assertIn(unquote(target.fragment), ids)

    def test_book_diagrams_have_sources_and_are_copied_to_the_site(self):
        used = set()
        for slug in self.visible:
            if self.articles[slug] == 0:
                continue
            document = self.page_path(f"{SERIES_URL}{slug}/").read_text(
                encoding="utf-8"
            )
            parsed = PageLinks(document)
            figures = [
                image for image in parsed.images
                if image.get("src", "").startswith(
                    "/images/ml-platform-engineering/"
                )
            ]
            self.assertTrue(figures, f"No book diagram in {slug}")
            self.assertTrue(any(
                "Machine Learning Platform Engineering" in caption
                for caption in parsed.captions
            ))
            for image in figures:
                with self.subTest(page=slug, image=image["src"]):
                    self.assertTrue(image.get("alt", "").strip())
                    output = self.page_path(image["src"])
                    original = ROOT / "static" / image["src"].lstrip("/")
                    self.assertEqual(output.read_bytes(), original.read_bytes())
                    used.add(original)
        self.assertEqual(
            used,
            set((ROOT / "static" / "images" / "ml-platform-engineering").glob("*.png")),
        )

    def test_reading_module_embeds_usable_state_and_publishes_its_script(self):
        document = self.page_path("/docs/book/").read_text(encoding="utf-8")
        parsed = PageLinks(document)
        source = (ROOT / "content" / "docs" / "book" / "_index.md").read_text(
            encoding="utf-8"
        )
        metadata, _ = json.JSONDecoder().raw_decode(source)
        self.assertEqual(
            json.loads(parsed.reading_state), metadata["reading_list"]
        )
        modules = [
            script for script in parsed.scripts
            if "reading-list." in script.get("src", "")
        ]
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0]["type"], "module")
        self.assertTrue(self.page_path(modules[0]["src"]).is_file())
