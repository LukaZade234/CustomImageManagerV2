-- Accent jobs someone is waiting for go first.
--
-- The rollout's import queued about a thousand characters for the accent worker
-- (those without a gallery, coloured from their main image), and a character a
-- visitor was looking at -- after an upload, or after "Reset to measured" cleared
-- a hand-picked colour -- went to the back of that line, an hour or more away,
-- though recomputing it takes seconds. The gallery endpoint now queues with
-- priority 1 (and raises an existing job to it); bulk work stays at 0.

ALTER TABLE accent_queue ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_accent_queue_due ON accent_queue (priority DESC, next_try_at);
