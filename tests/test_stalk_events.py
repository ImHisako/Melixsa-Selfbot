import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from pyrogram import enums, raw, types

from Cogs.core.stalk_tools import StalkMonitor, photo_id


class StalkEventTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.targets = {7}
        self.submit = AsyncMock()
        self.monitor = StalkMonitor(lambda: set(self.targets), self.submit)
        self.addAsyncCleanup(self.monitor.close)

    @staticmethod
    def user(**extra):
        return raw.types.User(**{
            "id": 7, "first_name": "Anna", "last_name": "Rossi", "username": "anna",
            "photo": raw.types.UserProfilePhoto(photo_id=123, dc_id=2),
            "status": raw.types.UserStatusOffline(was_online=1700000000), **extra,
        })

    def records(self):
        return [call.args[1] for call in self.submit.await_args_list]

    async def test_first_profile_is_a_baseline_without_fake_changes(self):
        await self.monitor.observe_user(self.user())
        self.submit.assert_not_awaited()
        self.assertEqual(self.monitor.profiles[7]["name"], "Anna Rossi")

    async def test_name_and_username_changes_keep_before_and_after_without_duplicates(self):
        await self.monitor.observe_user(self.user())
        user = self.user(first_name="Annamaria", username="annamaria")
        await self.monitor.observe_user(user)
        await self.monitor.observe_user(user)
        self.assertEqual([record["event"] for record in self.records()], ["name_changed", "username_changed"])
        self.assertEqual((self.records()[0]["old_value"], self.records()[0]["new_value"]), ("Anna Rossi", "Annamaria Rossi"))
        self.assertEqual((self.records()[1]["old_value"], self.records()[1]["new_value"]), ("anna", "annamaria"))
        self.assertTrue(all(record["chat_id"] is None for record in self.records()))

    async def test_raw_name_update_uses_the_active_primary_username(self):
        await self.monitor.observe_user(self.user())
        update = raw.types.UpdateUserName(user_id=7, first_name="Anna", last_name="Bianchi", usernames=[
            raw.types.Username(username="inactive", active=False),
            raw.types.Username(username="collectible", active=True),
            raw.types.Username(username="newanna", active=True, editable=True),
        ])
        await self.monitor.handle_update(update, {})
        self.assertEqual([record["new_value"] for record in self.records()], ["Anna Bianchi", "newanna"])

    async def test_raw_username_removal_is_logged_as_empty_value(self):
        await self.monitor.observe_user(self.user())
        await self.monitor.handle_update(raw.types.UpdateUserName(user_id=7, first_name="Anna", last_name="Rossi", usernames=[]), {})
        self.assertEqual([record["event"] for record in self.records()], ["username_changed"])
        self.assertEqual(self.records()[0]["new_value"], "")

    async def test_first_raw_name_update_does_not_invent_previous_values(self):
        await self.monitor.handle_update(raw.types.UpdateUserName(user_id=7, first_name="Anna", last_name="Rossi", usernames=[]), {})
        self.submit.assert_not_awaited()
        self.assertEqual(self.monitor.profiles[7]["name"], "Anna Rossi")

    async def test_photo_changes_and_removal_from_updated_user_bundles(self):
        await self.monitor.observe_user(self.user())
        update = raw.types.UpdateUser(user_id=7)
        await self.monitor.handle_update(update, {7: self.user(photo=raw.types.UserProfilePhoto(photo_id=456, dc_id=3))})
        await self.monitor.handle_update(update, {7: self.user(photo=raw.types.UserProfilePhotoEmpty())})
        self.assertEqual([record["event"] for record in self.records()], ["photo_changed", "photo_changed"])
        self.assertEqual([(record["old_value"], record["new_value"]) for record in self.records()], [("123", "456"), ("456", None)])

    async def test_raw_and_high_level_photo_ids_match_despite_file_id_encoding(self):
        photo = raw.types.UserProfilePhoto(photo_id=123, dc_id=2)
        parsed = await types.ChatPhoto._parse(None, photo, 7, 12345)
        self.assertEqual(photo_id(photo), photo_id(parsed))
        await self.monitor.observe_user(self.user())
        await self.monitor.observe_user(types.User(id=7, first_name="Anna", last_name="Rossi", username="anna", photo=parsed, status=enums.UserStatus.OFFLINE))
        self.submit.assert_not_awaited()

    async def test_raw_online_offline_transitions_are_logged_once(self):
        await self.monitor.observe_user(self.user())
        for status in (raw.types.UserStatusOnline(expires=1700001000), raw.types.UserStatusOnline(expires=1700002000),
                       raw.types.UserStatusOffline(was_online=1700001500), raw.types.UserStatusOffline(was_online=1700001600)):
            await self.monitor.handle_update(raw.types.UpdateUserStatus(user_id=7, status=status), {})
        self.assertEqual([record["event"] for record in self.records()], ["online", "offline"])

    async def test_first_explicit_online_update_is_an_observation(self):
        await self.monitor.handle_update(raw.types.UpdateUserStatus(user_id=7, status=raw.types.UserStatusOnline(expires=1700002000)), {})
        self.assertEqual([record["event"] for record in self.records()], ["online"])
        self.assertIsNone(self.records()[0]["old_value"])

    async def test_hidden_or_approximate_status_is_never_inferred_to_be_offline(self):
        await self.monitor.observe_user(self.user(status=raw.types.UserStatusOnline(expires=1700001000)))
        for status in (raw.types.UserStatusRecently(), raw.types.UserStatusLastWeek(), raw.types.UserStatusLastMonth(), raw.types.UserStatusEmpty()):
            await self.monitor.handle_update(raw.types.UpdateUserStatus(user_id=7, status=status), {})
        self.submit.assert_not_awaited()
        self.assertEqual(self.monitor.profiles[7]["status"], "unknown")

    async def test_partial_user_does_not_erase_existing_profile_or_photo(self):
        await self.monitor.observe_user(self.user())
        await self.monitor.handle_update(raw.types.UpdateUser(user_id=7), {7: raw.types.User(id=7, min=True)})
        self.assertEqual(self.monitor.profiles[7]["photo_id"], "123")
        self.assertEqual(self.monitor.profiles[7]["name"], "Anna Rossi")
        self.submit.assert_not_awaited()

    async def test_unmonitored_and_own_users_do_not_generate_events(self):
        self.monitor.own_id = 7
        await self.monitor.handle_update(raw.types.UpdateUserStatus(user_id=8, status=raw.types.UserStatusOnline(expires=1700001000)), {})
        await self.monitor.handle_update(raw.types.UpdateUserStatus(user_id=7, status=raw.types.UserStatusOnline(expires=1700001000)), {})
        self.submit.assert_not_awaited()
        self.assertEqual(self.monitor.profiles, {})

    async def test_stopped_user_is_ignored_and_reenabled_user_gets_a_new_baseline(self):
        await self.monitor.observe_user(self.user())
        self.targets.clear()
        await self.monitor.observe_user(self.user(first_name="New"))
        self.assertEqual(self.monitor.profiles, {})
        self.targets.add(7)
        self.monitor.seed(self.user(first_name="New"))
        await self.monitor.observe_user(self.user(first_name="New"))
        self.submit.assert_not_awaited()

    async def test_periodic_lookup_detects_changes_without_any_open_ui(self):
        client = SimpleNamespace(get_users=AsyncMock(side_effect=[self.user(), self.user(first_name="New")]))
        await self.monitor.refresh(client, 7)
        await self.monitor.refresh(client, 7)
        self.assertEqual([record["event"] for record in self.records()], ["name_changed"])
        self.assertEqual(self.records()[0]["source"], "poll")

    async def test_failed_lookup_preserves_baseline_and_does_not_stop_other_targets(self):
        await self.monitor.observe_user(self.user())
        client = SimpleNamespace(get_users=AsyncMock(side_effect=TimeoutError()))
        await self.monitor.refresh(client, 7)
        self.assertEqual(self.monitor.profiles[7]["name"], "Anna Rossi")
        self.submit.assert_not_awaited()

    async def test_inflight_lookup_cannot_revert_a_newer_pushed_update(self):
        await self.monitor.observe_user(self.user())
        pending = asyncio.Future()
        started = asyncio.Event()

        async def lookup(target):
            started.set()
            return await pending

        task = asyncio.create_task(self.monitor.refresh(SimpleNamespace(get_users=lookup), 7))
        await started.wait()
        await self.monitor.handle_update(raw.types.UpdateUserName(user_id=7, first_name="New", last_name="Rossi", usernames=[raw.types.Username(username="anna", active=True)]), {})
        pending.set_result(self.user())
        await task
        self.assertEqual(self.monitor.profiles[7]["name"], "New Rossi")
        self.assertEqual(len(self.records()), 1)

    async def test_concurrent_duplicate_updates_are_deduplicated(self):
        await self.monitor.observe_user(self.user())
        await asyncio.gather(*(self.monitor.observe_user(self.user(first_name="New")) for _ in range(8)))
        self.assertEqual(len(self.records()), 1)

    async def test_close_cancels_polling_and_pending_network_requests(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def lookup(target):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        self.monitor.start(SimpleNamespace(get_users=lookup))
        await asyncio.wait_for(started.wait(), timeout=1)
        await self.monitor.close()
        self.assertTrue(cancelled.is_set())
        self.assertIsNone(self.monitor.task)
        self.assertEqual(self.monitor.profiles, {})


if __name__ == "__main__":
    unittest.main()
