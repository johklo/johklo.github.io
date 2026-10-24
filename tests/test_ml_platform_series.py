import json
from html.parser import HTMLParser
from pathlib import Path
import re
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
        self.paragraphs = []
        self.in_paragraph = False
        self.scripts = []
        self.inputs = []
        self.mermaid_blocks = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "mermaid" in attrs.get("class", "").split():
            self.mermaid_blocks += 1
        if tag == "input":
            self.inputs.append(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "img":
            self.images.append(attrs)
        if tag == "figcaption":
            self.in_caption = True
        if tag == "p":
            self.paragraphs.append("")
            self.in_paragraph = True
        if tag == "script":
            self.scripts.append(attrs)

    def handle_endtag(self, tag):
        if tag == "figcaption":
            self.in_caption = False
        if tag == "p":
            self.in_paragraph = False

    def handle_data(self, data):
        if self.in_caption:
            self.captions.append(data)
        if self.in_paragraph:
            self.paragraphs[-1] += data


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
            slug for slug, chapter in cls.articles.items() if chapter <= 5
        }
        cls.hidden = cls.articles.keys() - cls.visible

    def page_path(self, url):
        url_path = unquote(urlsplit(url).path)
        path = self.output / url_path.lstrip("/")
        return path / "index.html" if url_path.endswith("/") else path

    def test_only_overview_and_first_five_chapters_are_published(self):
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

    def test_integrated_labs_are_published_and_linked_from_learning_entries(self):
        url = "/docs/tech/ml-platform-engineering-labs/"
        article = self.page_path(url)
        self.assertTrue(article.is_file(), "Integrated lab guide was not published")
        links = PageLinks(article.read_text(encoding="utf-8")).links
        self.assertIn("https://github.com/johklo/ml-platform-engineering-labs", links)
        for entry in (
            "/", SERIES_URL, f"{SERIES_URL}00-overview/",
            "/docs/tech/mlflow-azure-machine-learning/",
        ):
            with self.subTest(entry=entry):
                entry_links = PageLinks(
                    self.page_path(entry).read_text(encoding="utf-8")
                ).links
                resolved = {
                    urlsplit(urljoin(f"https://johklo.github.io{entry}", href)).path
                    for href in entry_links
                }
                self.assertIn(url, resolved)
        indexes = list(self.output.glob("*.search-data*.json"))
        self.assertTrue(any(
            url in json.loads(path.read_text(encoding="utf-8")) for path in indexes
        ))

    def test_lab_lessons_publish_complete_bodies_directly_under_tech(self):
        sources = sorted((ROOT / "content" / "docs" / "tech").glob("ml-platform-labs-*.md"))
        self.assertEqual(len(sources), 11)
        tech = PageLinks(
            self.page_path("/docs/tech/").read_text(encoding="utf-8")
        ).links
        indexes = list(self.output.glob("*.search-data*.json"))
        indexed = set()
        for path in indexes:
            indexed.update(json.loads(path.read_text(encoding="utf-8")))
        overview_url = "/docs/tech/ml-platform-engineering-labs/"
        for source in sources:
            url = f"/docs/tech/{source.stem}/"
            with self.subTest(lesson=source.stem):
                document = self.page_path(url).read_text(encoding="utf-8")
                self.assertIn(url, tech)
                self.assertIn(url, indexed)
                self.assertIn("실습 저장소", document)
                headings = re.findall(
                    r"(?m)^## (.+)$", source.read_text(encoding="utf-8")
                )
                self.assertTrue(headings)
                for heading in headings:
                    self.assertIn(heading, document)
                self.assertGreater(len(source.read_text(encoding="utf-8")), 1500)
                self.assertIn(
                    f"/collection/tech/edit/", document,
                )
                for href in PageLinks(document).links:
                    target = urlsplit(urljoin(f"https://johklo.github.io{url}", href))
                    if target.netloc == "johklo.github.io" and (
                        target.path.startswith("/docs/tech/ml-platform-labs-")
                        or target.path == overview_url
                    ):
                        self.assertTrue(self.page_path(target.path).is_file(), href)

    def test_book_diagrams_have_sources_and_are_copied_to_the_site(self):
        for slug in self.visible:
            if self.articles[slug] == 0:
                continue
            document = self.page_path(f"{SERIES_URL}{slug}/").read_text(
                encoding="utf-8"
            )
            parsed = PageLinks(document)
            figures = [
                image for image in parsed.images
                if image.get("src", "").startswith("/images/")
            ]
            if self.articles[slug] <= 3:
                self.assertTrue(figures, f"No book diagram in {slug}")
            else:
                self.assertGreater(parsed.mermaid_blocks, 0, f"No diagram in {slug}")
            if figures:
                self.assertTrue(any(
                    "출처: Machine Learning Platform Engineering" in caption
                    for caption in parsed.captions + parsed.paragraphs
                ), f"No book diagram source in {slug}")
            for image in figures:
                with self.subTest(page=slug, image=image["src"]):
                    self.assertTrue(image.get("alt", "").strip())
                    output = self.page_path(image["src"])
                    original = (
                        ROOT / "static"
                        / unquote(urlsplit(image["src"]).path).lstrip("/")
                    )
                    self.assertTrue(output.is_file(), f"Missing published image: {image['src']}")
                    self.assertTrue(original.is_file(), f"Missing source image: {image['src']}")
                    self.assertEqual(output.read_bytes(), original.read_bytes())

    def test_reading_list_preserves_cms_state_without_public_editing_controls(self):
        document = self.page_path("/docs/book/").read_text(encoding="utf-8")
        self.assertNotIn("data-reading-add", document)
        self.assertNotIn("book-title", document)
        for removed in (
            "data-reading-save", "data-reading-reload", "data-reading-token",
            "data-reading-state", "GitHub에 저장", "GitHub 저장 설정", "다시 불러오기",
        ):
            self.assertNotIn(removed, document)
        parsed = PageLinks(document)
        source = (ROOT / "content" / "docs" / "book" / "_index.md").read_text(
            encoding="utf-8"
        )
        metadata, _ = json.JSONDecoder().raw_decode(source)
        checkboxes = [item for item in parsed.inputs if item.get("type") == "checkbox"]
        self.assertEqual(len(checkboxes), len(metadata["reading_list"]))
        for checkbox, book in zip(checkboxes, metadata["reading_list"]):
            self.assertIn("disabled", checkbox)
            self.assertEqual("checked" in checkbox, book["read"])
            self.assertIn(book["title"], document)
        count = sum(book["read"] for book in metadata["reading_list"])
        self.assertIn(f"읽은 책 {count} / {len(checkboxes)}", document)
        modules = [
            script for script in parsed.scripts
            if "reading-list." in script.get("src", "")
        ]
        self.assertEqual(modules, [])
