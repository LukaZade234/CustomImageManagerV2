"""Notifications: the app messaging one account, and the owner messaging many.

Two producers share one table and one read surface. A broadcast is fanned out to
a row per recipient, so read state is per row; a mechanical message is always one
row for one person. Nothing here is a queue.
"""

import identity as identity_module


class TestListAndRead:
    def test_empty_to_begin_with(self, client, clean_db, identity_id):
        body = client.get("/api/notifications").get_json()
        assert body == {"items": [], "unread": 0}

    def test_a_message_appears_unread(self, client, clean_db, identity_id):
        clean_db.add_notification(identity_id, "Hello", "A body")
        body = client.get("/api/notifications").get_json()
        assert [item["title"] for item in body["items"]] == ["Hello"]
        assert body["items"][0]["body"] == "A body"
        assert body["unread"] == 1

    def test_reading_clears_the_unread_flag(self, client, clean_db, identity_id):
        clean_db.add_notification(identity_id, "Hello")
        assert client.post("/api/notifications/read").status_code == 200
        assert client.get("/api/notifications").get_json()["unread"] == 0

    def test_they_are_per_identity(self, clean_db, identity_id):
        clean_db.add_notification(identity_id, "For you")
        clean_db.ensure_identity("someone-else")
        assert clean_db.list_notifications("someone-else") == []


class TestBroadcast:
    def _broadcast(self, client, **payload):
        return client.post("/api/notifications/broadcast", json=payload)

    def test_only_the_owner_may_send(self, client, clean_db, identity_id, make_moderator):
        make_moderator("moderator")
        assert self._broadcast(client, audience="everyone", title="Hi").status_code == 403

    def test_a_plain_user_may_not_send(self, client, clean_db):
        assert self._broadcast(client, audience="everyone", title="Hi").status_code == 403

    def test_the_owner_reaches_every_identity(self, client, clean_db, identity_id, make_moderator):
        make_moderator("owner")
        clean_db.ensure_identity("alice")
        clean_db.ensure_identity("bob")
        res = self._broadcast(client, audience="everyone", title="Maintenance", body="Tonight")
        assert res.status_code == 200
        # The caller, alice and bob.
        assert res.get_json()["sent"] == 3
        assert [n["title"] for n in clean_db.list_notifications("alice")] == ["Maintenance"]

    def test_moderators_only_reaches_staff(self, client, clean_db, identity_id, make_moderator):
        make_moderator("owner")
        clean_db.ensure_identity("alice")  # a plain user
        clean_db.ensure_identity("mod")
        clean_db.set_role("mod", "moderator")
        res = self._broadcast(client, audience="moderators", title="Staff note")
        assert res.get_json()["sent"] == 2  # the owner and mod
        assert clean_db.list_notifications("alice") == []
        assert len(clean_db.list_notifications("mod")) == 1

    def test_an_unknown_audience_is_400(self, client, clean_db, make_moderator):
        make_moderator("owner")
        assert self._broadcast(client, audience="nobody", title="x").status_code == 400

    def test_a_missing_title_is_400(self, client, clean_db, make_moderator):
        make_moderator("owner")
        assert self._broadcast(client, audience="everyone", body="no title").status_code == 400


class TestMechanicalOnRoleChange:
    def test_promotion_notifies_the_person(self, client, clean_db, make_moderator):
        make_moderator("owner")
        clean_db.ensure_identity("worker")
        ref = identity_module.public_ref("worker")
        client.post(f"/api/moderation/users/{ref}/role", json={"role": "moderator"})
        items = clean_db.list_notifications("worker")
        assert items and items[0]["title"] == "You are now a moderator"
        assert items[0]["kind"] == "mechanical"

    def test_demotion_notifies_the_person(self, client, clean_db, make_moderator):
        make_moderator("owner")
        clean_db.ensure_identity("worker")
        clean_db.set_role("worker", "moderator")
        ref = identity_module.public_ref("worker")
        client.post(f"/api/moderation/users/{ref}/role", json={"role": "user"})
        items = clean_db.list_notifications("worker")
        assert items and items[0]["title"] == "Your moderator role was removed"
