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
    notes       TEXT, session_id TEXT, model TEXT, cache_read_tokens INTEGER NOT NULL DEFAULT 0
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

-- Consumption + ROI (token-roi theme). spend = money that does not arrive as
-- per-session tokens; seat '(org)' means org-level / unattributable.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id);

CREATE TABLE IF NOT EXISTS spend (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,                 -- anthropic-api | cursor | copilot | claude-max | other
    period_start TEXT NOT NULL,                 -- ISO date, inclusive
    period_end   TEXT NOT NULL,                 -- ISO date, exclusive
    seat         TEXT NOT NULL DEFAULT '(org)',
    cost_eur     REAL NOT NULL,
    granularity  TEXT NOT NULL,                 -- tokens | invoice | flat-rate
    notes        TEXT,
    UNIQUE (source, period_start, seat)
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket              TEXT PRIMARY KEY,
    estimate_human_days REAL,
    actual_human_days   REAL,
    day_rate_eur        REAL,
    evidence_tier       TEXT NOT NULL DEFAULT 'pre-estimate',
                        -- calibration | pre-estimate | velocity | post-hoc
    status              TEXT NOT NULL DEFAULT 'open',
    closed_at           TEXT
);

-- Per-ticket ROI over closed tickets. Session tokens only on the AI side —
-- invoice/flat-rate spend cannot honestly be split per ticket; it joins the
-- ROI at period level (dashboard/roi.py). Actuals < 0.1 day are flagged, not
-- allowed to produce absurd HDE values.
CREATE VIEW IF NOT EXISTS roi_view AS
SELECT
    t.ticket, t.estimate_human_days, t.actual_human_days, t.day_rate_eur,
    t.evidence_tier, t.closed_at,
    COALESCE(s.ai_cost_usd, 0)             AS ai_cost_usd,
    t.actual_human_days * t.day_rate_eur   AS human_cost_eur,
    t.estimate_human_days * t.day_rate_eur AS value_eur,
    CASE WHEN t.actual_human_days >= 0.1
         THEN t.estimate_human_days / t.actual_human_days END AS hde,
    CASE WHEN t.actual_human_days IS NOT NULL AND t.actual_human_days < 0.1
         THEN 1 ELSE 0 END                 AS flagged_low_actual
FROM tickets t
LEFT JOIN (
    SELECT ticket, SUM(cost_usd) AS ai_cost_usd
    FROM sessions WHERE ticket IS NOT NULL GROUP BY ticket
) s ON s.ticket = t.ticket
WHERE t.status = 'closed';
