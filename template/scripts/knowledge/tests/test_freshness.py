import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shutil, subprocess, tempfile, unittest
import freshness, ingest


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.org",
                    "-c", "commit.gpgsign=false", "-c", "gc.auto=0", *args], cwd=str(cwd), check=True,
                   capture_output=True)


def _project(base: Path) -> dict:
    """A kit repository with one product repository cloned under it and ignored by it."""
    (base / "docs").mkdir()
    (base / "docs/a.md").write_text("# A\n", encoding="utf-8")
    (base / ".gitignore").write_text("product/\n.knowledge/\n", encoding="utf-8")
    _git(base, "init", "-q"); _git(base, "add", "-A"); _git(base, "commit", "-qm", "kit")
    product = base / "product"
    product.mkdir()
    (product / "app.py").write_text("def run(): pass\n", encoding="utf-8")
    _git(product, "init", "-q"); _git(product, "add", "-A"); _git(product, "commit", "-qm", "one")
    return {"namespaces": {
        "docs": {"kind": "docs", "db": ".knowledge/docs.db", "roots": ["docs/"]},
        "product": {"kind": "code", "db": ".knowledge/product.db", "roots": ["product/"]}},
        "overlay": ".knowledge/global.db"}


@unittest.skipUnless(shutil.which("git"), "git not available")
class FreshnessTests(unittest.TestCase):
    def test_unbuilt_then_fresh_after_a_build(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            self.assertEqual(freshness.check(data, base)["state"], "unbuilt")
            ingest.build(data=data, base=base)
            state = freshness.check(data, base)
            self.assertEqual(state["state"], "fresh")
            self.assertEqual(state["changed"], [])
            self.assertEqual(sorted(freshness.heads(data, base)), [".", "product"])

    def test_a_commit_in_the_product_repository_makes_it_stale(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            ingest.build(data=data, base=base)
            (base / "product/app.py").write_text("def run(): return 1\n", encoding="utf-8")
            _git(base / "product", "commit", "-qam", "two")
            state = freshness.check(data, base)
            self.assertEqual(state["state"], "stale")
            self.assertEqual([c["tree"] for c in state["changed"]], ["product"])
            ingest.build(data=data, base=base)
            self.assertEqual(freshness.check(data, base)["state"], "fresh")

    def test_a_commit_in_the_kit_makes_it_stale(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            ingest.build(data=data, base=base)
            (base / "docs/a.md").write_text("# A\n\nmore\n", encoding="utf-8")
            _git(base, "commit", "-qam", "edit")
            self.assertEqual([c["tree"] for c in freshness.check(data, base)["changed"]], ["."])

    def test_an_edit_that_is_not_committed_is_not_seen(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            ingest.build(data=data, base=base)
            (base / "product/app.py").write_text("def run(): return 2\n", encoding="utf-8")
            self.assertEqual(freshness.check(data, base)["state"], "fresh")

    def test_a_namespace_without_sources_is_named(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            data["namespaces"]["absent"] = {"kind": "code", "db": ".knowledge/absent.db",
                                            "roots": ["not-cloned/"]}
            self.assertEqual(freshness.check(data, base)["without_sources"], ["absent"])
            ingest.build(data=data, base=base)
            state = freshness.check(data, base)
            self.assertEqual((state["state"], state["without_sources"]), ("fresh", ["absent"]))

    def test_a_change_to_the_manifest_makes_it_stale(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            ingest.build(data=data, base=base)
            data["namespaces"]["docs"]["roots"].append("more/")
            self.assertEqual([c["tree"] for c in freshness.check(data, base)["changed"]],
                             ["graph-manifest.json"])

    def test_a_missing_namespace_database_reads_as_unbuilt(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            ingest.build(data=data, base=base)
            (base / ".knowledge/product.db").unlink()
            self.assertEqual(freshness.check(data, base)["state"], "unbuilt")

    def test_a_build_that_fails_leaves_no_record(self):
        import ingest_docs
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            ingest.build(data=data, base=base)
            real = ingest_docs.ingest_root

            def broken(*args, **kwargs):
                raise RuntimeError("the reader failed")
            ingest_docs.ingest_root = broken
            try:
                with self.assertRaises(RuntimeError):
                    ingest.build(data=data, base=base)
            finally:
                ingest_docs.ingest_root = real
            self.assertEqual(freshness.check(data, base)["state"], "unbuilt")

    def test_a_broken_record_reads_as_unbuilt(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = Path(d); data = _project(base)
            ingest.build(data=data, base=base)
            (base / ".knowledge" / freshness.STAMP).write_text("not json", encoding="utf-8")
            self.assertEqual(freshness.check(data, base)["state"], "unbuilt")


if __name__ == "__main__":
    unittest.main()
