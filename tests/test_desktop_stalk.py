import asyncio
import base64
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from Cogs.core import runtime
from Cogs.core.instance_tools import InstanceLock
from Cogs.core.stalk_tools import StalkMonitor
from MelixsaUI.backend.bridge import DesktopBridge
from MelixsaUI.backend.stalk import user_id
from MelixsaUI.backend.surveillance import MAX_READ_BYTES


class DesktopStalkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        for name, value in {
            "DATA_DIR": self.root, "LOG_DIR": self.logs, "STATE_FILE": self.root / "state.json",
            "state": runtime.MonitorState(), "state_lock": asyncio.Lock(),
        }.items():
            patcher = patch.object(runtime, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        runtime.state.save()
        monitor = patch.object(runtime, "stalk_monitor", StalkMonitor(lambda: set(runtime.state.stalk), AsyncMock()))
        monitor.start()
        self.addCleanup(monitor.stop)
        self.bridge = DesktopBridge()
        self.addAsyncCleanup(self.bridge.close)
        self.user = SimpleNamespace(id=7, first_name="Anna", last_name="Rossi", username="anna", is_self=False, is_deleted=False)
        self.client = SimpleNamespace(get_users=AsyncMock(return_value=self.user))

    def connect(self):
        self.bridge.connection = "connected"
        self.bridge.client = self.client

    @staticmethod
    def record(message_id, **extra):
        return {"user_id": 7, "chat_id": -100, "chat_name": "Gruppo di prova", "event": "new",
                "message_id": message_id, "date": "2026-10-29T10:00:00+00:00", "name": "Anna Rossi",
                "username": "anna", "text": f"Messaggio {message_id}", **extra}

    def write_log(self, name="stalk_7.txt", records=None):
        path = self.logs / name
        records = records if records is not None else [self.record(1)]
        path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
        return path

    async def test_enable_resolves_username_and_preserves_shared_settings(self):
        self.connect()
        runtime.state.surveillance = {-100}
        runtime.state.prefix = "!"
        result = await self.bridge.dispatch("stalk_set", {"user": "@anna", "enabled": True})
        self.client.get_users.assert_awaited_once_with("@anna")
        saved = runtime.MonitorState.load()
        self.assertEqual(saved.stalk, {7})
        self.assertEqual(saved.surveillance, {-100})
        self.assertEqual(saved.prefix, "!")
        self.assertEqual(result["changed_id"], "7")
        self.assertEqual(result["users"][0]["name"], "Anna Rossi")
        self.assertEqual(result["users"][0]["username"], "anna")
        self.assertTrue(result["users"][0]["enabled"])
        self.assertEqual(self.bridge.snapshot()["stats"]["users"], 1)

    async def test_numeric_ids_are_resolved_as_integers(self):
        self.connect()
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        self.client.get_users.assert_awaited_once_with(7)

    async def wait_for_profiles(self):
        await asyncio.gather(*list(self.bridge.stalk.profile_tasks.values()))

    def add_photo(self):
        self.user.photo = SimpleNamespace(small_file_id="anna-photo")
        self.client.download_media = AsyncMock(return_value=io.BytesIO(b"profile photo"))

    async def test_enable_downloads_photo_and_reuses_cached_profile(self):
        self.connect()
        self.add_photo()
        await self.bridge.dispatch("stalk_set", {"user": "@anna", "enabled": True})
        await self.wait_for_profiles()
        for _ in range(2):
            result = await self.bridge.dispatch("stalk_overview", {})
            self.assertEqual(result["users"][0]["photo"],
                             "data:image/jpeg;base64," + base64.b64encode(b"profile photo").decode("ascii"))
        self.client.get_users.assert_awaited_once_with("@anna")
        self.client.download_media.assert_awaited_once_with("anna-photo", in_memory=True)

    async def test_existing_targets_load_profiles_without_being_enabled_again(self):
        self.connect()
        self.add_photo()
        runtime.state.stalk = {7}
        initial = await self.bridge.dispatch("stalk_overview", {})
        self.assertIsNone(initial["users"][0]["photo"])
        await self.wait_for_profiles()
        result = await self.bridge.dispatch("stalk_overview", {})
        self.assertEqual(result["users"][0]["name"], "Anna Rossi")
        self.assertTrue(result["users"][0]["photo"].startswith("data:image/jpeg;base64,"))
        self.client.get_users.assert_awaited_once_with(7)

    async def test_missing_photo_keeps_profile_and_logs_available(self):
        self.connect()
        self.client.download_media = AsyncMock()
        self.write_log()
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        await self.wait_for_profiles()
        result = await self.bridge.dispatch("stalk_overview", {})
        self.assertIsNone(result["users"][0]["photo"])
        self.assertEqual(result["users"][0]["name"], "Anna Rossi")
        self.assertEqual(len((await self.bridge.dispatch("stalk_logs", {"user_id": "7"}))["records"]), 1)
        self.client.download_media.assert_not_awaited()

    async def test_photo_failure_does_not_break_monitoring_or_retry_every_poll(self):
        self.connect()
        self.add_photo()
        self.client.download_media.side_effect = OSError("Photo unavailable")
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        await self.wait_for_profiles()
        result = await self.bridge.dispatch("stalk_overview", {})
        await self.wait_for_profiles()
        self.assertEqual(runtime.MonitorState.load().stalk, {7})
        self.assertIsNone(result["users"][0]["photo"])
        self.assertEqual(result["users"][0]["name"], "Anna Rossi")
        self.client.download_media.assert_awaited_once()

    async def test_unavailable_existing_user_does_not_break_logs(self):
        self.connect()
        self.write_log()
        self.client.get_users.side_effect = ValueError("Unknown user")
        await self.bridge.dispatch("stalk_overview", {})
        await self.wait_for_profiles()
        result = await self.bridge.dispatch("stalk_overview", {})
        self.assertEqual(result["users"][0]["name"], "Anna Rossi")
        self.assertIsNone(result["users"][0]["photo"])
        self.assertEqual(len((await self.bridge.dispatch("stalk_logs", {"user_id": "7"}))["records"]), 1)
        self.client.get_users.assert_awaited_once_with(7)

    async def test_invalid_or_oversized_downloads_are_not_sent_to_ui(self):
        self.connect()
        self.add_photo()
        for stream in (io.BytesIO(), io.BytesIO(b"x" * 2_000_001), "photo.jpg", None):
            with self.subTest(stream_type=type(stream).__name__):
                self.client.download_media.return_value = stream
                await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
                await self.wait_for_profiles()
                result = await self.bridge.dispatch("stalk_overview", {})
                self.assertIsNone(result["users"][0]["photo"])

    async def test_cached_photo_is_cleared_when_user_removes_it(self):
        self.connect()
        self.add_photo()
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        await self.wait_for_profiles()
        self.user.photo = None
        self.bridge.stalk.profile_refresh_at.clear()
        await self.bridge.dispatch("stalk_overview", {})
        await self.wait_for_profiles()
        result = await self.bridge.dispatch("stalk_overview", {})
        self.assertIsNone(result["users"][0]["photo"])

    async def test_pending_photo_does_not_block_logs_and_disconnect_cancels_it(self):
        self.connect()
        self.add_photo()
        self.write_log()
        started = asyncio.Event()

        async def download(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        self.client.download_media.side_effect = download
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        await asyncio.wait_for(started.wait(), timeout=1)
        result = await asyncio.wait_for(self.bridge.dispatch("stalk_logs", {"user_id": "7"}), timeout=1)
        self.assertEqual(len(result["records"]), 1)
        tasks = list(self.bridge.stalk.profile_tasks.values())
        await self.bridge.disconnect()
        self.assertTrue(all(task.cancelled() for task in tasks))
        self.assertEqual(self.bridge.stalk.profile_tasks, {})

    async def test_offline_overview_reuses_photo_without_telegram_requests(self):
        self.connect()
        self.add_photo()
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        await self.wait_for_profiles()
        await self.bridge.disconnect()
        result = await self.bridge.dispatch("stalk_overview", {})
        self.assertTrue(result["users"][0]["photo"])
        self.client.get_users.assert_awaited_once_with(7)
        self.client.download_media.assert_awaited_once()

    async def test_enable_requires_a_connection(self):
        with self.assertRaises(ValueError):
            await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        self.client.get_users.assert_not_awaited()

    async def test_login_in_progress_blocks_changes(self):
        for connection in ("connecting", "login_phone", "login_code", "login_password"):
            self.bridge.connection = connection
            with self.subTest(connection=connection), self.assertRaises(ValueError):
                await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": False})

    async def test_self_and_deleted_accounts_are_rejected(self):
        self.connect()
        for attribute in ("is_self", "is_deleted"):
            setattr(self.user, attribute, True)
            with self.subTest(attribute=attribute), self.assertRaises(ValueError):
                await self.bridge.dispatch("stalk_set", {"user": "@anna", "enabled": True})
            setattr(self.user, attribute, False)
        self.assertEqual(runtime.MonitorState.load().stalk, set())

    async def test_failed_lookup_does_not_change_persistent_state(self):
        self.connect()
        self.client.get_users.side_effect = ValueError("Unknown user")
        with self.assertRaises(ValueError):
            await self.bridge.dispatch("stalk_set", {"user": "@anna", "enabled": True})
        self.assertEqual(runtime.MonitorState.load().stalk, set())

    async def test_failed_save_rolls_back_live_state(self):
        self.connect()
        with patch.object(runtime.state, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        self.assertEqual(runtime.state.stalk, set())
        self.assertEqual(self.bridge.stalk.metadata, {})

    async def test_lookup_timeout_has_an_actionable_error(self):
        self.connect()
        self.client.get_users.side_effect = asyncio.TimeoutError()
        with self.assertRaisesRegex(ValueError, "Telegram non ha risposto"):
            await self.bridge.dispatch("stalk_set", {"user": "@anna", "enabled": True})
        self.assertEqual(runtime.MonitorState.load().stalk, set())

    async def test_offline_stop_preserves_logs_and_other_state(self):
        runtime.state.stalk = {7, 8}
        runtime.state.surveillance = {-100}
        runtime.state.autoreact = True
        runtime.state.save()
        path = self.write_log()
        original = path.read_bytes()
        result = await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": False})
        saved = runtime.MonitorState.load()
        self.assertEqual(saved.stalk, {8})
        self.assertEqual(saved.surveillance, {-100})
        self.assertTrue(saved.autoreact)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(next(user for user in result["users"] if user["id"] == "7")["enabled"])

    async def test_offline_stop_respects_runtime_lock(self):
        runtime.state.stalk = {7}
        runtime.state.save()
        with InstanceLock(self.root / "runtime.lock"):
            with self.assertRaises(RuntimeError):
                await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": False})
        self.assertEqual(runtime.MonitorState.load().stalk, {7})

    async def test_invalid_ids_and_booleans_do_not_reach_telegram(self):
        self.connect()
        for value in (True, False, 0, -7, "-7", "0", "7.0", "7/../.env", "@bad name", "9223372036854775808"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.bridge.dispatch("stalk_set", {"user": value, "enabled": True})
        for enabled in (1, "on", None):
            with self.subTest(enabled=enabled), self.assertRaises(ValueError):
                await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": enabled})
        self.client.get_users.assert_not_awaited()
        self.assertEqual(user_id("123456789"), 123456789)

    async def test_overview_combines_saved_targets_and_archived_logs(self):
        runtime.state.stalk = {7, 8}
        runtime.state.save()
        current = self.write_log()
        archive = self.write_log("stalk_7.txt.100", [self.record(0)])
        self.write_log("stalk_9.txt", [self.record(1, user_id=9, name="Marco")])
        self.write_log("group_-100.txt")
        result = await self.bridge.dispatch("stalk_overview", {})
        self.assertEqual(result["active_count"], 2)
        self.assertEqual({user["id"] for user in result["users"]}, {"7", "8", "9"})
        user = next(user for user in result["users"] if user["id"] == "7")
        self.assertEqual(user["name"], "Anna Rossi")
        self.assertEqual(user["log_files"], 2)
        self.assertEqual(user["log_bytes"], current.stat().st_size + archive.stat().st_size)
        self.assertIsNotNone(user["last_update"])
        self.client.get_users.assert_not_awaited()

    async def test_commands_and_ui_use_the_same_target_list(self):
        self.connect()
        runtime.state.stalk = {7}
        first = await self.bridge.dispatch("stalk_overview", {})
        self.assertEqual(first["active_count"], 1)
        runtime.state.stalk = {8, 9}
        second = await self.bridge.dispatch("stalk_overview", {})
        self.assertEqual({user["id"] for user in second["users"]}, {"8", "9"})

    async def test_stopped_target_without_logs_stays_visible_this_session(self):
        self.connect()
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        result = await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": False})
        self.assertEqual(result["active_count"], 0)
        self.assertEqual(result["users"][0]["name"], "Anna Rossi")
        self.assertEqual((await self.bridge.dispatch("stalk_logs", {"user_id": "7"}))["records"], [])

    async def test_logs_include_groups_edits_and_rotations_newest_first(self):
        self.write_log("stalk_7.txt.100", [self.record(1)])
        self.write_log("stalk_7.txt.200", [self.record(2, chat_id=-200)])
        self.write_log(records=[self.record(3), self.record(4, event="edited", text="Ciao 🌙\nSeconda riga", edit_date="2026-10-29T10:01:00+00:00")])
        result = await self.bridge.dispatch("stalk_logs", {"user_id": "7"})
        self.assertEqual([record["message_id"] for record in result["records"]], ["4", "3", "2", "1"])
        self.assertEqual(result["records"][0]["event"], "edited")
        self.assertEqual(result["records"][0]["date"], "2026-10-29T10:01:00+00:00")
        self.assertEqual(result["records"][0]["text"], "Ciao 🌙\nSeconda riga")
        self.assertEqual(result["records"][2]["chat_id"], "-200")

    async def test_profile_and_presence_event_types_keep_values_and_no_group(self):
        events = ("name_changed", "username_changed", "photo_changed", "online", "offline")
        self.write_log(records=[self.record(None, event=event, chat_id=None, old_value="prima", new_value=None,
                                            source="poll", text="") for event in events])
        result = await self.bridge.dispatch("stalk_logs", {"user_id": "7"})
        self.assertEqual([record["event"] for record in result["records"]], list(reversed(events)))
        for record in result["records"]:
            self.assertEqual(record["old_value"], "prima")
            self.assertIsNone(record["new_value"])
            self.assertEqual(record["chat_id"], "")
            self.assertEqual(record["message_id"], "")
            self.assertEqual(record["source"], "poll")

    async def test_profile_event_values_are_bounded_and_non_strings_are_ignored(self):
        self.write_log(records=[self.record(None, event="name_changed", chat_id=None, old_value="a" * 1000, new_value={"unexpected": True})])
        result = await self.bridge.dispatch("stalk_logs", {"user_id": "7"})
        self.assertEqual(len(result["records"][0]["old_value"]), 512)
        self.assertIsNone(result["records"][0]["new_value"])

    async def test_runtime_change_invalidates_cached_avatar_before_five_minutes(self):
        self.connect()
        self.add_photo()
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        await self.wait_for_profiles()
        self.user.photo.small_file_id = "new-photo"
        self.client.download_media.return_value = io.BytesIO(b"new image")
        await runtime.stalk_monitor.observe_user(self.user)
        first = await self.bridge.dispatch("stalk_overview", {})
        self.assertIsNone(first["users"][0]["photo"])
        await self.wait_for_profiles()
        result = await self.bridge.dispatch("stalk_overview", {})
        self.assertEqual(result["users"][0]["photo"], "data:image/jpeg;base64," + base64.b64encode(b"new image").decode("ascii"))
        self.assertEqual(self.client.download_media.await_count, 2)

    async def test_failed_avatar_invalidation_keeps_retry_backoff(self):
        self.connect()
        self.add_photo()
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        await self.wait_for_profiles()
        self.user.photo.small_file_id = "new-photo"
        await runtime.stalk_monitor.observe_user(self.user)
        self.client.get_users.side_effect = ValueError("Unavailable profile")
        for _ in range(2):
            await self.bridge.dispatch("stalk_overview", {})
            await self.wait_for_profiles()
        self.assertEqual(self.client.get_users.await_count, 2)

    async def test_failed_new_photo_download_does_not_show_previous_photo(self):
        self.connect()
        self.add_photo()
        await self.bridge.dispatch("stalk_set", {"user": "7", "enabled": True})
        await self.wait_for_profiles()
        self.user.photo.small_file_id = "new-photo"
        await runtime.stalk_monitor.observe_user(self.user)
        self.client.download_media.side_effect = OSError("Download unavailable")
        await self.bridge.dispatch("stalk_overview", {})
        await self.wait_for_profiles()
        result = await self.bridge.dispatch("stalk_overview", {})
        self.assertIsNone(result["users"][0]["photo"])

    async def test_monitor_events_are_written_and_read_through_real_log_pipeline(self):
        writer = runtime.LogWriter(self.logs)
        await writer.start()
        self.addAsyncCleanup(writer.close)
        with patch.object(runtime, "writer", writer):
            runtime.state.stalk = {7}
            runtime.state.save()
            runtime.stalk_monitor.seed(self.user)
            runtime.stalk_monitor.submit = runtime.submit_stalk_event
            await runtime.stalk_monitor.observe(7, {"name": "Anna Bianchi", "username": "newanna", "photo_id": "456", "status": "online"})
            await runtime.stalk_monitor.observe(7, {"status": "offline"})
            await writer.close()
        result = await self.bridge.dispatch("stalk_logs", {"user_id": "7"})
        self.assertEqual([record["event"] for record in result["records"]],
                         ["offline", "online", "photo_changed", "username_changed", "name_changed"])
        self.assertEqual(result["records"][-1]["old_value"], "Anna Rossi")
        self.assertEqual(result["records"][-1]["new_value"], "Anna Bianchi")

    async def test_invalid_and_other_user_records_are_skipped(self):
        path = self.write_log(records=[self.record(1), self.record(2, user_id=8), self.record(3, user_id=True)])
        with path.open("ab") as output:
            output.write(b'{"partial":')
        result = await self.bridge.dispatch("stalk_logs", {"user_id": "7"})
        self.assertEqual([record["message_id"] for record in result["records"]], ["1"])
        self.assertEqual(result["skipped"], 3)

    async def test_record_limit_and_read_budget(self):
        self.write_log(records=[self.record(index) for index in range(150)])
        result = await self.bridge.dispatch("stalk_logs", {"user_id": "7"})
        self.assertEqual(len(result["records"]), 100)
        self.assertEqual(result["records"][0]["message_id"], "149")
        self.assertTrue(result["limited"])
        self.write_log(records=[self.record(1, text="x" * (MAX_READ_BYTES + 1024))])
        oversized = await self.bridge.dispatch("stalk_logs", {"user_id": "7"})
        self.assertEqual(oversized["records"], [])
        self.assertTrue(oversized["limited"])

    async def test_unknown_targets_and_path_traversal_are_rejected(self):
        for target in ("999", "../../.env", "/etc/passwd", -1, False):
            with self.subTest(target=target), self.assertRaises(ValueError):
                await self.bridge.dispatch("stalk_logs", {"user_id": target})


if __name__ == "__main__":
    unittest.main()
