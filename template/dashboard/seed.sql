-- First-run synthetic rows so the dashboard renders immediately. Safe to delete;
-- real data comes from your harness (sessions) and collect_commits.py (commits).

INSERT INTO sessions (ts, seat, tool, task, ticket, tokens_in, tokens_out, cost_usd, outcome, grounded) VALUES
  ('2026-06-22T09:10:00', 'Developer', 'claude', 'implement login form',   '<TICKET>-101', 18000, 4200, 0.21, 'accepted', 1),
  ('2026-06-22T11:30:00', 'QA',        'claude', 'derive tests from AC',    '<TICKET>-101',  9000, 2600, 0.12, 'accepted', 1),
  ('2026-06-23T14:05:00', 'Product',   'claude', 'slice epic into stories', '<TICKET>-090', 12000, 5100, 0.18, 'reworked', 0),
  ('2026-06-24T10:00:00', 'Architect', 'claude', 'draft ADR-0001',          '<TICKET>-077', 22000, 6300, 0.31, 'accepted', 1),
  ('2026-06-24T16:40:00', 'Developer', 'claude', 'refactor data layer',     '<TICKET>-112', 27000, 8100, 0.39, 'rejected', 0),
  ('2026-06-25T09:20:00', 'EM',        'claude', 'tune CI governance gate',  '<TICKET>-006',  7000, 1900, 0.09, 'accepted', 1);

INSERT INTO commits (sha, ts, author_name, author_email, seat, klass, source, ai_lines, human_lines, insertions, deletions, files_changed, tool, subject, ticket) VALUES
  ('seed0001', '2026-06-22T09:12:00', 'Dev One', 'dev1@example.com', 'Developer', 'ai',    'git-ai',  180, 10, 190,  4, 3, 'claude', 'implement login form',        '<TICKET>-101'),
  ('seed0002', '2026-06-23T14:20:00', 'PO One',  'po1@example.com',  'Product',   'human', 'trailer',   0, 40,  40,  2, 1, NULL,     'refine acceptance criteria',  '<TICKET>-090'),
  ('seed0003', '2026-06-24T16:50:00', 'Dev Two', 'dev2@example.com', 'Developer', 'mixed', 'git-ai',  120, 60, 180, 30, 5, 'claude', 'refactor data layer',         '<TICKET>-112');
