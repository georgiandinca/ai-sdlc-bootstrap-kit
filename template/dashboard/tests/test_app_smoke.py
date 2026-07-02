#!/usr/bin/env python3
"""Smoke test for app.py: verifies that a tz-aware commit row does not cause TypeError
in app.main() (regression for the _date_filter tz-naive vs tz-aware comparison bug)."""
import importlib
import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent


def _make_streamlit_stub():
    """Return a minimal streamlit stub that satisfies app.py's import-time needs."""
    st = types.ModuleType("streamlit")

    # cache_data: pass-through decorator (ignores ttl kwarg)
    st.cache_data = lambda *a, **k: (lambda f: f)

    # columns / tabs return lists of MagicMocks so `with` and tuple-unpack work
    def _columns(n, *a, **k):
        return [unittest.mock.MagicMock() for _ in range(n if isinstance(n, int) else len(n))]

    def _tabs(labels):
        return [unittest.mock.MagicMock() for _ in labels]

    st.columns = _columns
    st.tabs = _tabs
    st.sidebar = unittest.mock.MagicMock()

    # All other st.<something>() calls are no-ops
    def _noop(*a, **k):
        return unittest.mock.MagicMock()

    for attr in (
        "set_page_config", "title", "caption", "info", "warning", "metric",
        "subheader", "bar_chart", "line_chart", "dataframe", "date_input",
    ):
        setattr(st, attr, _noop)

    return st


class AppSmokeTest(unittest.TestCase):
    def test_main_runs_with_tz_aware_commit(self):
        """app.main() must not raise TypeError when commits.ts is tz-aware."""
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "u.db"

            # Bootstrap schema (via db module loaded fresh)
            db_spec = importlib.util.spec_from_file_location(
                "dashboard_db_smoke", DASHBOARD_DIR / "db.py"
            )
            db_mod = importlib.util.module_from_spec(db_spec)
            db_spec.loader.exec_module(db_mod)

            conn = db_mod.connect(db_path)
            # Insert a commit row with a tz-aware ISO 8601 timestamp (+03:00)
            conn.execute(
                "INSERT OR REPLACE INTO commits "
                "(sha, ts, author_name, author_email, klass, source, "
                "ai_lines, human_lines, insertions, deletions, files_changed, subject) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "abc123",
                    "2026-06-25T10:00:00+03:00",
                    "Dev",
                    "dev@example.com",
                    "ai-assisted",
                    "trailer",
                    5, 0, 5, 0, 1,
                    "tz-aware commit",
                ),
            )
            conn.commit()
            conn.close()

            # Stub streamlit before importing app
            st_stub = _make_streamlit_stub()
            sys.modules["streamlit"] = st_stub

            # Reload db module inside app's sys.path so it picks up our temp DB
            # Patch db.connect to always use our temp DB
            app_spec = importlib.util.spec_from_file_location(
                "dashboard_app_smoke", DASHBOARD_DIR / "app.py"
            )
            app_mod = importlib.util.module_from_spec(app_spec)
            # We need dbmod inside app to use our db_path
            # Patch it via the module's dbmod attribute after load

            # Insert the stub db module so app's `import db` resolves it
            db_stub = types.ModuleType("db")

            def _connect_stub(*a, **k):
                return db_mod.connect(db_path)

            db_stub.connect = _connect_stub
            # Expose DB_PATH so nothing breaks
            db_stub.DB_PATH = db_path

            old_db = sys.modules.get("db")
            sys.modules["db"] = db_stub
            try:
                app_spec.loader.exec_module(app_mod)
                # main() should run without TypeError
                app_mod.main()
            finally:
                if old_db is None:
                    sys.modules.pop("db", None)
                else:
                    sys.modules["db"] = old_db
                sys.modules.pop("streamlit", None)


if __name__ == "__main__":
    unittest.main()
