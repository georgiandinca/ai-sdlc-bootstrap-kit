import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, os
import tempfile, unittest
import export_jira as ej

CFG = {"deployment": "cloud", "project": "PROJ",
       "fields": {"sprint": "customfield_10020", "epic_link": "customfield_10014",
                  "story_points": "customfield_10016"},
       "description_max_chars": 30}

CLOUD_RAW = {
    "key": "PROJ-2",
    "fields": {
        "issuetype": {"name": "Story"}, "summary": "Ingest issues",
        "status": {"name": "To Do"}, "assignee": {"displayName": "Ada"},
        "reporter": {"displayName": "Grace"}, "labels": ["kg", "plat"],
        "priority": {"name": "Medium"}, "resolution": None,
        "created": "2026-07-03T10:00:00.000+0000", "updated": "2026-07-03T11:00:00.000+0000",
        "parent": {"key": "PROJ-1"},
        "customfield_10020": [{"name": "Sprint 1"}],
        "customfield_10016": 3.0,
        "description": {"type": "doc", "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "A long description that exceeds the cap for sure."}]}]},
    }}

DC_RAW = {
    "key": "PROJ-3",
    "fields": {
        "issuetype": {"name": "Bug"}, "summary": "Fix it",
        "status": {"name": "Done"}, "assignee": {"name": "ada"},
        "reporter": {"name": "grace"}, "labels": [],
        "priority": {"name": "High"}, "resolution": {"name": "Fixed"},
        "created": "2026-07-01T09:00:00.000+0000", "updated": "2026-07-02T09:00:00.000+0000",
        "customfield_10016": 5,
        "description": "Plain   wiki   text.",
    }}


class NormalizeTests(unittest.TestCase):
    def test_cloud_issue(self):
        r = ej.normalize_issue(CLOUD_RAW, CFG, "https://x.atlassian.net")
        self.assertEqual(r["key"], "PROJ-2")
        self.assertEqual(r["type"], "Story")
        self.assertEqual(r["assignee"], "Ada")
        self.assertEqual(r["labels"], "kg;plat")
        self.assertEqual(r["sprint"], "Sprint 1")
        self.assertEqual(r["parent"], "PROJ-1")
        self.assertEqual(r["epic"], "PROJ-1")     # falls back to parent
        self.assertEqual(r["story_points"], "3")  # 3.0 -> "3"
        self.assertEqual(r["url"], "https://x.atlassian.net/browse/PROJ-2")
        self.assertEqual(len(r["description"]), 30)  # capped
        self.assertNotIn("\n", r["description"])

    def test_datacenter_issue(self):
        r = ej.normalize_issue(DC_RAW, CFG, "https://jira.co/")
        self.assertEqual(r["type"], "Bug")
        self.assertEqual(r["assignee"], "ada")
        self.assertEqual(r["resolution"], "Fixed")
        self.assertEqual(r["story_points"], "5")
        self.assertEqual(r["description"], "Plain wiki text.")
        self.assertEqual(r["url"], "https://jira.co/browse/PROJ-3")

    def test_adf_multiparagraph_not_run_together(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "First paragraph."}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Second paragraph."}]}]}
        self.assertEqual(ej.adf_to_text(doc), "First paragraph.\nSecond paragraph.")
        self.assertEqual(ej.normalize_description(doc, 500), "First paragraph. Second paragraph.")

    def test_natural_key_sorts_numerically(self):
        self.assertEqual(ej.natural_key("PROJ-2"), ("PROJ", 2))
        self.assertTrue(ej.natural_key("PROJ-2") < ej.natural_key("PROJ-10"))

    def test_write_ledger_is_idempotent(self):
        rows = [ej.normalize_issue(DC_RAW, CFG, "https://jira.co"),
                ej.normalize_issue(CLOUD_RAW, CFG, "https://x.atlassian.net")]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "issues.csv"
            ej.write_ledger(rows, p)
            first = p.read_bytes()
            ej.write_ledger(list(reversed(rows)), p)  # order must not matter
            self.assertEqual(first, p.read_bytes())
            text = first.decode("utf-8")
            self.assertTrue(text.startswith(",".join(ej.COLUMNS)))
            self.assertLess(text.index("PROJ-2"), text.index("PROJ-3"))  # sorted


class AdapterTests(unittest.TestCase):
    def _fake(self, pages):
        it = iter(pages)
        return lambda url: next(it)

    def test_offset_pagination_stops_at_total(self):
        pages = [{"issues": [{"key": "A"}, {"key": "B"}], "total": 3},
                 {"issues": [{"key": "C"}], "total": 3}]
        got = ej.paginate_offset(self._fake(pages), "https://j", "2",
                                 "project=P", ["summary"], page_size=2)
        self.assertEqual([i["key"] for i in got], ["A", "B", "C"])

    def test_cursor_pagination_follows_token(self):
        pages = [{"issues": [{"key": "A"}], "nextPageToken": "t1"},
                 {"issues": [{"key": "B"}], "nextPageToken": None}]
        got = ej.paginate_cursor(self._fake(pages), "https://x", "project=P", ["summary"])
        self.assertEqual([i["key"] for i in got], ["A", "B"])

    def test_cloud_headers_basic(self):
        os.environ["JIRA_EMAIL"] = "a@b.c"
        os.environ["JIRA_API_TOKEN"] = "tok"
        h = ej.cloud_headers()
        self.assertTrue(h["Authorization"].startswith("Basic "))

    def test_datacenter_headers_bearer(self):
        os.environ.pop("JIRA_USER", None)
        os.environ.pop("JIRA_PASSWORD", None)
        os.environ["JIRA_PAT"] = "pat123"
        h = ej.datacenter_headers()
        self.assertEqual(h["Authorization"], "Bearer pat123")

    def test_main_from_json_writes_ledger(self):
        payload = json.dumps({"issues": [CLOUD_RAW]})
        with tempfile.TemporaryDirectory() as d:
            jf = Path(d) / "in.json"
            jf.write_text(payload, encoding="utf-8")
            out = Path(d) / "issues.csv"
            os.environ["JIRA_BASE_URL"] = "https://x.atlassian.net"
            rc = ej.main(["--from-json", str(jf)], config=CFG, ledger=out)
            self.assertEqual(rc, 0)
            self.assertIn("PROJ-2", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
