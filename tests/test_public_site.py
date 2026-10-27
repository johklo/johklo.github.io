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

    def test_allows_only_the_reviewed_kfp_study_downloads(self):
        prefix = "static/downloads/ml-platform-engineering/kfp-cluster/"
        allowed = [
            prefix + name for name in (
                "Dockerfile", "submit_cluster.py",
                "feature_study.py", "income_study.py",
                "pipeline_study.py", "run_pipeline_study.py",
                "object-store-patch.yaml", "executor-patch.yaml",
            )
        ]
        rejected = [
            prefix + "kubeconfig",
            prefix + "income-study.db",
            prefix + "other.py",
            "static/downloads/other/submit_cluster.py",
        ]
        self.assertEqual(unexpected_static_files(allowed + rejected), rejected)
