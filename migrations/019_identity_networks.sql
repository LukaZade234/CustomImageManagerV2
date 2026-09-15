-- Network links: which accounts have been seen from the same network.
--
-- Not enforcement. A second Discord account is the one ban evasion the identity
-- anchor cannot catch, and an IP cannot be a sentence -- it is shared by mobile
-- carriers, households and VPN exits, and rotates. So this is a *signal*: a
-- moderator can see that a contributor has been seen from the same network as a
-- restricted account and decide for themselves.
--
-- The IP itself is never stored. What is kept is a keyed hash (blake2b with a
-- server-only key), so a row cannot be turned back into an address, and rows are
-- pruned after a retention window -- the link is intentionally short-lived.

CREATE TABLE identity_networks (
    identity_id TEXT NOT NULL REFERENCES identities (id) ON DELETE CASCADE,
    ip_hash     TEXT NOT NULL,
    first_seen  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_seen   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    hits        INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (identity_id, ip_hash)
);
-- The lookup is "who else has this hash", so the hash is the indexed side.
CREATE INDEX idx_identity_networks_hash ON identity_networks (ip_hash);
CREATE INDEX idx_identity_networks_seen ON identity_networks (last_seen);
