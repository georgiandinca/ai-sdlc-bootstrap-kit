-- AI-utilization + commit-attribution dashboard schema (board pillar 4/7).
-- Idempotent DDL ONLY — first-run seeds live in seed.sql. SQLite by default;
-- the columns map cleanly to Postgres if you outgrow it.

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,                      -- ISO 8601 timestamp
    seat        TEXT    NOT NULL,                      -- Architect | EM | Product | Developer | QA
    tool        TEXT    NOT NULL DEFAULT 'claude',
    task        TEXT,
    ticket      TEXT,
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL    NOT NULL DEFAULT 0,
    outcome     TEXT    NOT NULL DEFAULT 'unknown',    -- accepted | reworked | rejected | unknown
    grounded    INTEGER NOT NULL DEFAULT 0,
    notes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_ts   ON sessions(ts);
CREATE INDEX IF NOT EXISTS idx_sessions_seat ON sessions(seat);

-- Commit attribution (Phase 3): one row per commit, AI/mixed/human by LOC.
CREATE TABLE IF NOT EXISTS commits (
    sha           TEXT PRIMARY KEY,
    ts            TEXT NOT NULL,                        -- author date, ISO 8601
    author_name   TEXT,
    author_email  TEXT,
    seat          TEXT,                                 -- best-effort; often NULL
    klass         TEXT NOT NULL DEFAULT 'human',        -- human | ai | mixed | ai-assisted
    source        TEXT NOT NULL DEFAULT 'trailer',      -- git-ai | trailer
    ai_lines      INTEGER NOT NULL DEFAULT 0,
    human_lines   INTEGER NOT NULL DEFAULT 0,
    insertions    INTEGER NOT NULL DEFAULT 0,
    deletions     INTEGER NOT NULL DEFAULT 0,
    files_changed INTEGER NOT NULL DEFAULT 0,
    tool          TEXT,                                 -- claude | cursor | copilot | ...
    subject       TEXT,
    ticket        TEXT
);
CREATE INDEX IF NOT EXISTS idx_commits_ts    ON commits(ts);
CREATE INDEX IF NOT EXISTS idx_commits_klass ON commits(klass);
