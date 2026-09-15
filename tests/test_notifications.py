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


class TestDismiss:
    def test_a_normal_notification_can_be_dismissed(self, client, clean_db, identity_id):
        clean_db.add_notification(identity_id, "Remove me")
        item = client.get("/api/notifications").get_json()["items"][0]
        assert client.post("/api/notifications/dismiss", json={"id": item["id"]}).status_code == 200
        assert client.get("/api/notifications").get_json()["items"] == []

    def test_dismissing_someone_elses_is_404(self, client, clean_db):
        clean_db.ensure_identity("someone")
        clean_db.add_notification("someone", "Theirs")
        their = clean_db.list_notifications("someone")[0]["id"]
        assert client.post("/api/notifications/dismiss", json={"id": their}).status_code == 404
        assert len(clean_db.list_notifications("someone")) == 1

    def test_a_missing_id_is_400(self, client, clean_db):
        assert client.post("/api/notifications/dismiss", json={}).status_code == 400


class TestPinned:
    def test_a_pin_reaches_an_account_made_later(self, client, clean_db, identity_id, make_moderator):
        make_moderator("owner")
        res = client.post(
            "/api/notifications/broadcast",
            json={"audience": "everyone", "title": "Welcome", "body": "Read me", "pinned": True},
        )
        assert res.status_code == 200

        # An account that did not exist when it was sent still sees it.
        clean_db.ensure_identity("latecomer")
        titles = [n["title"] for n in clean_db.list_notifications("latecomer")]
        assert titles == ["Welcome"]
        assert clean_db.list_notifications("latecomer")[0]["pinned"] is True

    def test_a_moderator_pin_skips_a_later_plain_user(self, client, clean_db, make_moderator):
        make_moderator("owner")
        client.post(
            "/api/notifications/broadcast",
            json={"audience": "moderators", "title": "Staff only", "pinned": True},
        )
        clean_db.ensure_identity("plain")
        assert clean_db.list_notifications("plain") == []
        assert [n["title"] for n in clean_db.list_notifications("plain", is_staff=True)] == [
            "Staff only"
        ]

    def test_a_new_identity_sees_a_pin_as_unread(self, client, clean_db, identity_id, make_moderator):
        make_moderator("owner")
        client.post(
            "/api/notifications/broadcast",
            json={"audience": "everyone", "title": "Notice", "pinned": True},
        )
        # A cookie made after the pin still arrives to it unread.
        clean_db.ensure_identity("latecomer")
        assert clean_db.count_unread_notifications("latecomer") == 1

    def test_reading_clears_a_pin(self, client, clean_db, identity_id, make_moderator):
        make_moderator("owner")
        client.post(
            "/api/notifications/broadcast",
            json={"audience": "everyone", "title": "Notice", "pinned": True},
        )
        assert client.get("/api/notifications").get_json()["unread"] == 1
        client.post("/api/notifications/read")
        assert client.get("/api/notifications").get_json()["unread"] == 0

    def test_a_moderators_pin_is_unread_only_for_staff(self, client, clean_db, make_moderator):
        make_moderator("owner")
        client.post(
            "/api/notifications/broadcast",
            json={"audience": "moderators", "title": "Staff note", "pinned": True},
        )
        clean_db.ensure_identity("plain")
        assert clean_db.count_unread_notifications("plain") == 0
        assert clean_db.count_unread_notifications("plain", is_staff=True) == 1

    def test_a_pin_cannot_be_dismissed(self, client, clean_db, identity_id, make_moderator):
        make_moderator("owner")
        client.post(
            "/api/notifications/broadcast",
            json={"audience": "everyone", "title": "Notice", "pinned": True},
        )
        pin = client.get("/api/notifications").get_json()["items"][0]
        # No normal row here shares the id, so nothing is removed and the pin stays.
        client.post("/api/notifications/dismiss", json={"id": pin["id"]})
        assert [n["title"] for n in clean_db.list_notifications(identity_id)] == ["Notice"]


class TestOwnerDelete:
    def test_deleting_a_broadcast_clears_it_for_everyone(self, client, clean_db, make_moderator):
        make_moderator("owner")
        clean_db.ensure_identity("alice")
        client.post(
            "/api/notifications/broadcast",
            json={"audience": "everyone", "title": "Gone soon"},
        )
        alice_item = clean_db.list_notifications("alice")[0]
        res = client.post(
            "/api/notifications/delete",
            json={"source": "notification", "id": alice_item["id"]},
        )
        assert res.status_code == 200
        assert clean_db.list_notifications("alice") == []

    def test_deleting_a_pin_removes_it_for_everyone(self, client, clean_db, identity_id, make_moderator):
        make_moderator("owner")
        clean_db.ensure_identity("alice")
        client.post(
            "/api/notifications/broadcast",
            json={"audience": "everyone", "title": "Pinned", "pinned": True},
        )
        pin = clean_db.list_notifications("alice")[0]
        res = client.post("/api/notifications/delete", json={"source": "pin", "id": pin["id"]})
        assert res.status_code == 200
        assert clean_db.list_notifications("alice") == []

    def test_only_the_owner_may_delete(self, client, clean_db, identity_id, make_moderator):
        make_moderator("moderator")
        clean_db.add_notification(identity_id, "Mine")
        item = clean_db.list_notifications(identity_id)[0]
        res = client.post(
            "/api/notifications/delete",
            json={"source": "notification", "id": item["id"]},
        )
        assert res.status_code == 403
        assert len(clean_db.list_notifications(identity_id)) == 1

    def test_an_unknown_source_is_400(self, client, clean_db, make_moderator):
        make_moderator("owner")
        assert (
            client.post("/api/notifications/delete", json={"source": "bogus", "id": 1}).status_code
            == 400
        )
