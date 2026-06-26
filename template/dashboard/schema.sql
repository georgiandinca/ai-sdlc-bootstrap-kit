-- AI-utilization dashboard schema (board pillar 4: "Dashboard utilization (DB + web)").
-- SQLite by default; the columns map cleanly to Postgres if you outgrow it.
-- The dashboard reads this DB; your agents/harness write to it (or import from an
-- export of your AI tool's usage logs).

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,                      -- ISO 8601 timestamp
    seat        TEXT    NOT NULL,                      -- Architect | EM | Product | Developer | QA
    tool        TEXT    NOT NULL DEFAULT 'claude',     -- which AI tool
    task        TEXT,                                  -- short label of the work
    ticket      TEXT,                                  -- linked issue key, if any
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL    NOT NULL DEFAULT 0,
    outcome     TEXT    NOT NULL DEFAULT 'unknown',    -- accepted | reworked | rejected | unknown
    grounded    INTEGER NOT NULL DEFAULT 0,            -- 1 if grounded on the knowledge layer
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_ts   ON sessions(ts);
CREATE INDEX IF NOT EXISTS idx_sessions_seat ON sessions(seat);

-- Seed a few synthetic rows so the dashboard renders on first run.
-- (Safe to delete; real data comes from your harness.)
INSERT INTO sessions (ts, seat, tool, task, ticket, tokens_in, tokens_out, cost_usd, outcome, grounded) VALUES
  ('2026-06-22T09:10:00', 'Developer', 'claude', 'implement login form',   '<TICKET>-101', 18000, 4200, 0.21, 'accepted', 1),
  ('2026-06-22T11:30:00', 'QA',        'claude', 'derive tests from AC',    '<TICKET>-101',  9000, 2600, 0.12, 'accepted', 1),
  ('2026-06-23T14:05:00', 'Product',   'claude', 'slice epic into stories', '<TICKET>-090', 12000, 5100, 0.18, 'reworked', 0),
  ('2026-06-24T10:00:00', 'Architect', 'claude', 'draft ADR-0001',          '<TICKET>-077', 22000, 6300, 0.31, 'accepted', 1),
  ('2026-06-24T16:40:00', 'Developer', 'claude', 'refactor data layer',     '<TICKET>-112', 27000, 8100, 0.39, 'rejected', 0),
  ('2026-06-25T09:20:00', 'EM',        'claude', 'tune CI governance gate',  '<TICKET>-006',  7000, 1900, 0.09, 'accepted', 1);
