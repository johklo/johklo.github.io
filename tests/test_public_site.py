import unittest

from tools.check_public_site import unexpected_static_files


class PublicFilesTest(unittest.TestCase):
    def test_allows_public_site_metadata_and_images(self):
        paths = [
            "content/docs/book/article.md",
            "static/robots.txt",
            "static/google0505804a65414d73.html",
            "static/images/.gitkeep",
            "static/images/diagram.svg",
            "static/images/2026/photo.webp",
        ]
        self.assertEqual(unexpected_static_files(paths), [])

    def test_rejects_apps_and_data_even_when_encrypted(self):
        paths = [
            "static/app/index.html",
            "static/app/vault.enc",
            "static/images/data.json",
            "static/images/bundle.js",
            "static/robots.txt.bak",
            "notes/index.html",
            "s/hidden/vault.enc",
        ]
        self.assertEqual(unexpected_static_files(paths), paths)
