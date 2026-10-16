import base64
import json
from pathlib import Path
import tempfile
import unittest

from tools.prepare_site_assets import prepare_assets


class SiteAssetsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.source = Path(directory.name) / "source"
        self.destination = Path(directory.name) / "output"
        self.source.mkdir()
        (self.source / "index.html").write_text("<html></html>", encoding="utf-8")
        (self.source / "vault.enc").write_bytes(b"encrypted-test-fixture" * 2)
        (self.source / "vault.meta.json").write_text(json.dumps({
            "algorithm": "AES-256-GCM / PBKDF2-SHA256",
            "iterations": 310000,
            "salt": base64.b64encode(bytes(16)).decode(),
            "iv": base64.b64encode(bytes(12)).decode(),
        }), encoding="utf-8")

    def test_copies_encrypted_bundle_without_modifying_it(self):
        assets = self.source / "assets"
        assets.mkdir()
        (assets / "app.js").write_text("export {};", encoding="utf-8")
        prepare_assets(self.source, self.destination)
        for path in self.source.rglob("*"):
            if path.is_file():
                self.assertEqual(
                    path.read_bytes(),
                    (self.destination / path.relative_to(self.source)).read_bytes(),
                )

    def test_rejects_plaintext_data_before_copying(self):
        for name in ("learning.json", "notes.md", "assets/data.json"):
            with self.subTest(name=name):
                path = self.source / name
                path.parent.mkdir(exist_ok=True)
                path.write_text("private fixture", encoding="utf-8")
                with self.assertRaises(ValueError):
                    prepare_assets(self.source, self.destination)
                self.assertFalse(self.destination.exists())
                path.unlink()

    def test_rejects_missing_encrypted_bundle(self):
        (self.source / "vault.enc").unlink()
        with self.assertRaises(ValueError):
            prepare_assets(self.source, self.destination)
        self.assertFalse(self.destination.exists())

    def test_rejects_invalid_encryption_metadata(self):
        (self.source / "vault.meta.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            prepare_assets(self.source, self.destination)
        self.assertFalse(self.destination.exists())
