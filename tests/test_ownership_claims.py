"""Ownership claims: the staff-gated way back out of the unowned-v1 bucket.

The unowned bucket is permanent on purpose (migration 004, DECISIONS.md section
1), and migration 025 is the one bounded exception. So these tests are mostly
about the property that keeps the exception from reopening the hole: a claim
never takes an image someone already owns, and nothing transfers without a
moderator's decision.
"""

import json

import identity

OTHER = "another-claimant"


def _post(client, path, payload=None):
    return client.post(
        path, data=json.dumps(payload or {}), content_type="application/json"
    )


def _seed(db, char="Rem"):
    """A character with two unowned images (one active, one removed) and one owned."""
    db.ensure_identity("existing-owner")
    db.add_custom_images(char, ["https://cdn/unowned-a.png"], added_by=None)
    db.add_custom_images(char, ["https://cdn/owned.png"], added_by="existing-owner")
    # A second unowned image, removed, so the claim covers both states.
    db.add_custom_images(char, ["https://cdn/unowned-b.png"], added_by=None)
    # `is_moderator=True` is what allows an actorless removal; the cut-over
    # recovery used the same path. It leaves `removed_by` NULL.
    db.remove_custom_images(
        char, ["https://cdn/unowned-b.png"], actor_id=None, is_moderator=True
    )
    return char


def _claim_id(db, char="Rem", status="pending"):
    conn = db.get_connection()
    row = conn.execute(
        "SELECT cl.id FROM ownership_claims cl"
        "  JOIN characters c ON c.id = cl.character_id"
        " WHERE c.name = ? AND cl.status = ? ORDER BY cl.id",
        (char, status),
    ).fetchone()
    return int(row["id"]) if row else None


def _owners(db, char="Rem"):
    conn = db.get_connection()
    return {
        r["url"]: r["added_by"]
        for r in conn.execute(
            "SELECT i.url AS url, i.added_by AS added_by FROM custom_images i"
            "  JOIN characters c ON c.id = i.character_id WHERE c.name = ?",
            (char,),
        )
    }


class TestClaimable:
    def test_counts_unowned_by_state(self, clean_db):
        _seed(clean_db)
        assert clean_db.claimable_image_counts("Rem") == {"active": 1, "removed": 1}

    def test_an_unknown_character_has_nothing(self, clean_db):
        assert clean_db.claimable_image_counts("Nobody") == {"active": 0, "removed": 0}

    def test_the_gallery_reports_what_is_claimable(self, client, clean_db, identity_id):
        _seed(clean_db)
        body = client.get("/api/custom-image/Rem").get_json()
        assert body["claimable"] == {"active": 1, "removed": 1}

    def test_a_fully_owned_character_reports_nothing_claimable(self, client, clean_db, identity_id):
        """The banner must not appear when there is nothing to give back."""
        clean_db.ensure_identity("someone")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"], added_by="someone")
        body = client.get("/api/custom-image/Rem").get_json()
        assert body["claimable"] is None


class TestFiling:
    def test_filing_creates_a_pending_claim(self, client, clean_db, identity_id, make_signed_in):
        _seed(clean_db)
        make_signed_in()
        body = _post(client, "/api/claim-character", {"character_name": "Rem"}).get_json()
        assert body["status"] == "filed"
        assert _claim_id(clean_db) is not None

    def test_filing_twice_is_idempotent(self, client, clean_db, identity_id, make_signed_in):
        """A double click must not be an error, nor a second queue entry."""
        _seed(clean_db)
        make_signed_in()
        first = _post(client, "/api/claim-character", {"character_name": "Rem"}).get_json()
        second = _post(client, "/api/claim-character", {"character_name": "Rem"}).get_json()
        assert second["status"] == "already_pending"
        assert first["claim"]["id"] == second["claim"]["id"]
        conn = clean_db.get_connection()
        assert conn.execute("SELECT COUNT(*) FROM ownership_claims").fetchone()[0] == 1

    def test_signing_in_is_required(self, client, clean_db, identity_id):
        """A request to own things is tied to an account, so a ban can stop abuse."""
        _seed(clean_db)
        r = _post(client, "/api/claim-character", {"character_name": "Rem"})
        assert r.status_code == 403
        assert r.get_json()["code"] == "discord_required"

    def test_nothing_unowned_is_refused(self, client, clean_db, identity_id, make_signed_in):
        """The server agrees with the hidden button rather than trusting the UI."""
        clean_db.ensure_identity("someone")
        clean_db.add_custom_images("Rem", ["https://cdn/a.png"], added_by="someone")
        make_signed_in()
        r = _post(client, "/api/claim-character", {"character_name": "Rem"})
        assert r.status_code == 409

    def test_unknown_character_is_404(self, client, clean_db, identity_id, make_signed_in):
        make_signed_in()
        assert _post(client, "/api/claim-character", {"character_name": "Nobody"}).status_code == 404

    def test_the_gallery_reports_my_claim_state(self, client, clean_db, identity_id, make_signed_in):
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        body = client.get("/api/custom-image/Rem").get_json()
        assert body["myClaim"]["status"] == "pending"


class TestDecision:
    def test_approval_grants_only_the_unowned_images(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        """The property that matters: a claim never takes what someone owns."""
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        claim_id = _claim_id(clean_db)

        make_moderator()
        r = _post(client, f"/api/moderation/claims/{claim_id}/decide", {"approve": True})
        assert r.status_code == 200
        assert r.get_json()["images_granted"] == 2

        owners = _owners(clean_db)
        assert owners["https://cdn/unowned-a.png"] == identity_id
        assert owners["https://cdn/unowned-b.png"] == identity_id
        assert owners["https://cdn/owned.png"] == "existing-owner"

    def test_a_removed_image_keeps_its_removed_state(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        """A claim returns ownership, not a restored gallery."""
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        make_moderator()
        _post(
            client,
            f"/api/moderation/claims/{_claim_id(clean_db)}/decide",
            {"approve": True},
        )
        conn = clean_db.get_connection()
        row = conn.execute(
            "SELECT state, removed_by FROM custom_images WHERE url = 'https://cdn/unowned-b.png'"
        ).fetchone()
        assert row["state"] == "removed"
        # Nobody was named as the remover, and a claim does not invent one.
        assert row["removed_by"] is None

    def test_nothing_is_left_claimable_after_approval(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        make_moderator()
        _post(client, f"/api/moderation/claims/{_claim_id(clean_db)}/decide", {"approve": True})
        assert clean_db.claimable_image_counts("Rem") == {"active": 0, "removed": 0}
        assert client.get("/api/custom-image/Rem").get_json()["claimable"] is None

    def test_approval_notifies_the_claimant(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        make_moderator()
        _post(client, f"/api/moderation/claims/{_claim_id(clean_db)}/decide", {"approve": True})
        titles = [n["title"] for n in clean_db.list_notifications(identity_id)]
        assert any("approved" in t for t in titles)

    def test_a_rival_claim_is_auto_rejected_and_told(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        """One claimant per character. The loser is told, but not who won."""
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        loser_claim = clean_db.file_ownership_claim("Rem", OTHER)
        assert loser_claim["status"] == "filed"

        make_moderator()
        r = _post(client, f"/api/moderation/claims/{_claim_id(clean_db)}/decide", {"approve": True})
        assert r.get_json()["rivals_rejected"] == 1

        rejected = clean_db.list_ownership_claims("rejected")["items"]
        assert len(rejected) == 1
        assert rejected[0]["claimant"] == "Brisk Greenshank"
        assert "first" in rejected[0]["reason"]
        body = clean_db.list_notifications(OTHER)[0]
        assert "not approved" in body["title"]
        # The winner is never named to the loser.
        assert identity_id not in body["body"]

    def test_rejection_records_the_reason_and_tells_the_claimant(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        make_moderator()
        r = _post(
            client,
            f"/api/moderation/claims/{_claim_id(clean_db)}/decide",
            {"approve": False, "reason": "Please sign in with your old account."},
        )
        assert r.status_code == 200
        assert r.get_json()["approved"] is False
        notif = clean_db.list_notifications(identity_id)[0]
        assert "Please sign in with your old account." in notif["body"]

    def test_a_rejected_user_may_ask_again(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        """A rejection is not a ban; re-requesting is a fresh pending claim."""
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        make_moderator()
        _post(client, f"/api/moderation/claims/{_claim_id(clean_db)}/decide", {"approve": False})

        body = _post(client, "/api/claim-character", {"character_name": "Rem"}).get_json()
        assert body["status"] == "filed"
        assert body["claim"]["id"] != _claim_id(clean_db, "Rem", "rejected")

    def test_a_decided_claim_cannot_be_decided_again(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        make_moderator()
        claim_id = _claim_id(clean_db)
        assert _post(client, f"/api/moderation/claims/{claim_id}/decide", {"approve": True}).status_code == 200
        assert _post(client, f"/api/moderation/claims/{claim_id}/decide", {"approve": True}).status_code == 404

    def test_approve_must_be_a_boolean(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        make_moderator()
        r = _post(client, f"/api/moderation/claims/{_claim_id(clean_db)}/decide", {"approve": "yes"})
        assert r.status_code == 400


class TestModerationQueue:
    def test_the_queue_is_moderator_only(self, client, clean_db, identity_id):
        assert client.get("/api/moderation/claims").status_code == 403

    def test_pending_is_the_default_view(self, client, clean_db, identity_id, make_signed_in, make_moderator):
        _seed(clean_db)
        clean_db.file_ownership_claim("Rem", OTHER)
        make_moderator()
        body = client.get("/api/moderation/claims").get_json()
        assert body["status"] == "pending"
        assert body["total"] == 1
        assert body["items"][0]["character"] == "Rem"

    def test_filtering_by_character(self, client, clean_db, identity_id, make_moderator):
        _seed(clean_db, "Rem")
        _seed(clean_db, "Ram")
        clean_db.file_ownership_claim("Rem", OTHER)
        clean_db.file_ownership_claim("Ram", OTHER)
        make_moderator()
        body = client.get("/api/moderation/claims?char=Ram").get_json()
        assert [i["character"] for i in body["items"]] == ["Ram"]

    def test_filtering_by_user(self, client, clean_db, identity_id, make_moderator):
        _seed(clean_db)
        clean_db.file_ownership_claim("Rem", OTHER)
        clean_db.file_ownership_claim("Rem", identity_id)
        make_moderator()
        ref = identity.public_ref(OTHER)
        body = client.get(f"/api/moderation/claims?user={ref}").get_json()
        assert body["total"] == 1
        assert body["items"][0]["claimant"] == "Brisk Greenshank"
        assert body["items"][0]["user_ref"] == ref

    def test_an_unknown_user_filter_is_404(self, client, clean_db, identity_id, make_moderator):
        make_moderator()
        assert client.get("/api/moderation/claims?user=nope").status_code == 404

    def test_an_unknown_status_is_400(self, client, clean_db, identity_id, make_moderator):
        make_moderator()
        assert client.get("/api/moderation/claims?status=maybe").status_code == 400

    def test_each_item_says_what_an_approval_would_move(self, client, clean_db, identity_id, make_moderator):
        _seed(clean_db)
        clean_db.file_ownership_claim("Rem", OTHER)
        make_moderator()
        item = client.get("/api/moderation/claims").get_json()["items"][0]
        assert item["unowned_total"] == 2
        assert item["unowned_active"] == 1


class TestApproveAll:
    def test_approves_every_pending_claim_for_a_user(self, client, clean_db, identity_id, make_moderator):
        _seed(clean_db, "Rem")
        _seed(clean_db, "Ram")
        clean_db.file_ownership_claim("Rem", OTHER)
        clean_db.file_ownership_claim("Ram", OTHER)
        make_moderator()
        ref = identity.public_ref(OTHER)
        body = _post(client, f"/api/moderation/claims/approve-all/{ref}").get_json()
        assert body["approved_count"] == 2
        assert body["images_granted"] == 4
        assert body["remaining"] == 0
        assert clean_db.claimable_image_counts("Rem") == {"active": 0, "removed": 0}
        assert clean_db.claimable_image_counts("Ram") == {"active": 0, "removed": 0}

    def test_it_stops_at_the_cap_and_reports_what_is_left(self, client, clean_db, identity_id, make_moderator):
        for i in range(clean_db.MAX_BULK_CLAIM_APPROVALS + 3):
            name = f"Char{i}"
            clean_db.add_custom_images(name, [f"https://cdn/{i}.png"], added_by=None)
            clean_db.file_ownership_claim(name, OTHER)
        make_moderator()
        ref = identity.public_ref(OTHER)
        body = _post(client, f"/api/moderation/claims/approve-all/{ref}").get_json()
        assert body["approved_count"] == clean_db.MAX_BULK_CLAIM_APPROVALS
        assert body["remaining"] == 3

    def test_it_is_moderator_only(self, client, clean_db, identity_id):
        ref = identity.public_ref(OTHER)
        assert _post(client, f"/api/moderation/claims/approve-all/{ref}").status_code == 403

    def test_an_unknown_user_is_404(self, client, clean_db, identity_id, make_moderator):
        make_moderator()
        assert _post(client, "/api/moderation/claims/approve-all/nope").status_code == 404


class TestMyClaims:
    def test_lists_this_visitors_claims(self, client, clean_db, identity_id, make_signed_in):
        _seed(clean_db)
        make_signed_in()
        _post(client, "/api/claim-character", {"character_name": "Rem"})
        body = client.get("/api/me/claims").get_json()
        assert [c["character"] for c in body] == ["Rem"]
        assert body[0]["status"] == "pending"
