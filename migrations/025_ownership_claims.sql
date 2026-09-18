-- Ownership claims: a bounded exception to the unowned-v1 rule.
--
-- Images imported from v1 carry `added_by IS NULL`, and the design deliberately
-- makes that permanent: migration 004 warns that ownership must always be
-- recorded, "or those images would fall into the same unowned bucket as the
-- 8,547 migrated from v1 -- permanently, with no way to reclaim them", and
-- `db.remove_custom_images` refuses to let an ordinary user touch a row whose
-- `added_by` is NULL. That rule is what makes griefing the inherited library
-- unimplementable rather than merely discouraged.
--
-- This table is the single, staff-gated way back out. It does not weaken the
-- rule: nothing here transfers ownership. A claim is a *request*, and only a
-- moderator acting on it runs the UPDATE. The transfer itself is still
-- NULL-only (an image someone already owns is never taken), so the worst a
-- malicious claim achieves is a moderator looking at it.
--
-- It is a temporary reconciliation tool for the original userbase -- the people
-- who uploaded these images on v1, before ownership existed, and who should not
-- have to lose them to the migration. There is no expiry: the operator removes
-- the affordance when the userbase has been served, and this table stays as the
-- record of who was given what.
CREATE TABLE ownership_claims (
    id             INTEGER PRIMARY KEY,
    character_id   INTEGER NOT NULL REFERENCES characters (id) ON DELETE CASCADE,
    -- The claimant. `require_signed_in` gates filing, so this is an account, not
    -- a throwaway cookie -- which is also what makes a ban able to stop abuse.
    identity_id    TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    status         TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- Both NULL until a moderator decides. `decided_by` is SET NULL rather than
    -- CASCADE: losing the moderator's identity must not erase the decision.
    decided_at     TEXT,
    decided_by     TEXT REFERENCES identities (id) ON DELETE SET NULL,
    reason         TEXT NOT NULL DEFAULT '',
    -- What the approval actually moved, recorded at decision time. The rows are
    -- mutated in place, so without this there is no way to know afterwards how
    -- much a given decision granted.
    images_granted INTEGER NOT NULL DEFAULT 0
);

-- One *pending* claim per person per character. Scoped to `status = 'pending'`
-- rather than the whole table so a rejection does not bar a later request: the
-- user can ask again, and the new row is a fresh pending claim while the old
-- rejected one survives as history. This is a partial unique index, so it is
-- enforced by SQLite and a double-submit race cannot produce two.
CREATE UNIQUE INDEX idx_claims_one_pending
    ON ownership_claims (character_id, identity_id)
    WHERE status = 'pending';

-- The moderation queue: pending first, newest first.
CREATE INDEX idx_claims_queue ON ownership_claims (status, created_at DESC);

-- "This person's claims", for the character page's own state and for the
-- approve-all-by-user view.
CREATE INDEX idx_claims_identity ON ownership_claims (identity_id, created_at DESC);

-- The two reads behind the claim button: does this character have anything left
-- to claim, and how much. Partial on `added_by IS NULL` because that is the only
-- bucket a claim can touch, and on `purged_at IS NULL` because a purged row has
-- no file to give back. Without this, both are a scan of every image on the
-- character, on every character page view.
CREATE INDEX idx_custom_images_unowned
    ON custom_images (character_id)
    WHERE added_by IS NULL AND purged_at IS NULL;
