import asyncio
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


class MonitorRemovalCases:
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        for name, value in {
            "DATA_DIR": self.root, "LOG_DIR": self.logs, "STATE_FILE": self.root / "state.json",
            "state": runtime.MonitorState(), "state_lock": asyncio.Lock(),
            "writer": runtime.LogWriter(self.logs),
            "stalk_monitor": StalkMonitor(lambda: set(runtime.state.stalk), AsyncMock()),
        }.items():
            patcher = patch.object(runtime, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addAsyncCleanup(runtime.writer.close)
        self.bridge = DesktopBridge()
        self.addAsyncCleanup(self.bridge.close)
        self.service = getattr(self.bridge, self.field)
        self.path = self.logs / f"{self.prefix}{self.target}.txt"
        self.params = {self.id_key: str(self.target)}
        runtime.state.stalk = {7, 8}
        runtime.state.surveillance = {-100, -200}
        runtime.state.prefix = "!"
        runtime.state.save()

    async def remove(self):
        return await self.bridge.dispatch(f"{self.field}_remove", self.params)

    def assert_removed(self, result):
        self.assertEqual(result["removed_id"], str(self.target))
        self.assertNotIn(str(self.target), {item["id"] for item in result[self.items_key]})
        self.assertNotIn(self.target, getattr(runtime.MonitorState.load(), self.field))
        self.assertFalse(self.path.exists())

    async def test_offline_removal_deletes_rotations_and_preserves_other_targets_and_settings(self):
        self.path.write_text("current", encoding="utf-8")
        archive = self.path.with_name(self.path.name + ".123")
        archive.write_text("archive", encoding="utf-8")
        other_paths = [self.logs / f"{prefix}{target}.txt" for prefix, target in
                       (("stalk_", 7), ("stalk_", 8), ("group_", -100), ("group_", -200))
                       if (prefix, target) != (self.prefix, self.target)]
        other_paths.append(self.path.with_name(self.path.name + ".bak"))
        for path in other_paths:
            path.write_text("keep", encoding="utf-8")
        self.service.metadata[self.target] = {}
        self.service.log_labels[self.target] = (0, {})
        result = await self.remove()
        self.assert_removed(result)
        self.assertFalse(archive.exists())
        self.assertNotIn(self.target, self.service.metadata)
        self.assertNotIn(self.target, self.service.log_labels)
        self.assertTrue(all(path.read_text(encoding="utf-8") == "keep" for path in other_paths))
        saved = runtime.MonitorState.load()
        self.assertEqual(saved.stalk, {8} if self.field == "stalk" else {7, 8})
        self.assertEqual(saved.surveillance, {-200} if self.field == "surveillance" else {-100, -200})
        self.assertEqual(saved.prefix, "!")
        restarted = DesktopBridge()
        self.addAsyncCleanup(restarted.close)
        overview = await restarted.dispatch(f"{self.field}_overview", {})
        self.assertNotIn(str(self.target), {item["id"] for item in overview[self.items_key]})
        with self.assertRaises(ValueError):
            await self.bridge.dispatch(f"{self.field}_logs", self.params)

    async def test_removal_handles_stopped_archived_and_metadata_only_entries(self):
        getattr(runtime.state, self.field).clear()
        runtime.state.save()
        self.path.write_text("archived entry", encoding="utf-8")
        self.assert_removed(await self.remove())
        self.service.metadata[self.target] = {}
        self.assert_removed(await self.remove())
        self.assertNotIn(self.target, self.service.metadata)

    async def test_recovery_spools_cannot_restore_removed_logs_after_restart(self):
        target_record = {"file": self.path.name, "record": {"text": "remove"}}
        other_record = {"file": "stalk_8.txt", "record": {"text": "keep"}}
        mixed = self.logs / "pending-123.json"
        target_only = self.logs / "pending-456.json"
        mixed.write_text(json.dumps([target_record, other_record]), encoding="utf-8")
        target_only.write_text(json.dumps([target_record]), encoding="utf-8")
        self.assert_removed(await self.remove())
        self.assertFalse(target_only.exists())
        self.assertEqual(json.loads(mixed.read_text(encoding="utf-8")), [other_record])
        await runtime.writer.start()
        await runtime.writer.queue.join()
        await runtime.writer.close()
        self.assertFalse(self.path.exists())
        self.assertTrue((self.logs / "stalk_8.txt").exists())

    async def test_connected_removal_drains_queued_events_before_deleting_files(self):
        self.bridge.connection = "connected"
        self.bridge.client = object()
        await runtime.writer.start()
        await runtime.writer.submit(self.path, {"text": "pending"}, echo=False)
        other = self.logs / "stalk_8.txt"
        await runtime.writer.submit(other, {"text": "keep"}, echo=False)
        self.assert_removed(await self.remove())
        await runtime.writer.close()
        self.assertFalse(self.path.exists())
        self.assertTrue(other.exists())

    async def test_pending_write_timeout_reports_failure_and_preserves_logs_for_retry(self):
        self.path.write_text("keep", encoding="utf-8")
        await runtime.writer.start()
        with patch.object(runtime.writer.queue, "join", AsyncMock(side_effect=asyncio.TimeoutError)):
            with self.assertRaisesRegex(ValueError, "riprova la rimozione"):
                await self.remove()
        self.assertNotIn(self.target, getattr(runtime.MonitorState.load(), self.field))
        self.assertTrue(self.path.exists())
        self.assert_removed(await self.remove())

    async def test_offline_removal_respects_another_runtime_lock(self):
        self.path.write_text("keep", encoding="utf-8")
        with InstanceLock(self.root / "runtime.lock"), self.assertRaises(RuntimeError):
            await self.remove()
        self.assertIn(self.target, getattr(runtime.MonitorState.load(), self.field))
        self.assertEqual(self.path.read_text(encoding="utf-8"), "keep")

    async def test_failed_state_save_preserves_files_and_cached_entry(self):
        self.bridge.connection = "connected"
        self.path.write_text("keep", encoding="utf-8")
        self.service.metadata[self.target] = {}
        with patch.object(runtime.state, "save", side_effect=OSError("disk full")), self.assertRaises(OSError):
            await self.remove()
        self.assertIn(self.target, getattr(runtime.state, self.field))
        self.assertIn(self.target, self.service.metadata)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "keep")

    async def test_delete_failure_leaves_monitoring_stopped_and_allows_retry(self):
        self.path.write_text("keep", encoding="utf-8")
        unlink = Path.unlink

        def fail_target(path, *args, **kwargs):
            if path == self.path:
                raise PermissionError("file locked")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True, side_effect=fail_target), self.assertRaises(PermissionError):
            await self.remove()
        self.assertNotIn(self.target, getattr(runtime.MonitorState.load(), self.field))
        self.assertTrue(self.path.exists())
        self.assert_removed(await self.remove())

    async def test_invalid_ids_and_login_in_progress_do_not_delete_anything(self):
        self.path.write_text("keep", encoding="utf-8")
        for value in (None, True, "../../state.json", "@username", 0, -self.target):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.bridge.dispatch(f"{self.field}_remove", {self.id_key: value})
        for connection in ("connecting", "login_phone", "login_code", "login_password"):
            self.bridge.connection = connection
            with self.subTest(connection=connection), self.assertRaises(ValueError):
                await self.remove()
        self.assertIn(self.target, getattr(runtime.MonitorState.load(), self.field))
        self.assertTrue(self.path.exists())


class DesktopStalkRemovalTests(MonitorRemovalCases, unittest.IsolatedAsyncioTestCase):
    field, prefix, target, id_key, items_key = "stalk", "stalk_", 7, "user_id", "users"

    async def test_removal_cancels_pending_profile_download_and_clears_caches(self):
        started = asyncio.Event()

        async def download():
            self.service.profiles[7] = {"name": "Anna"}
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(download())
        self.service.profile_tasks[7] = task
        task.add_done_callback(lambda done: self.service.profile_tasks.pop(7, None))
        self.service.profile_refresh_at[7] = 300
        self.service.profile_requested_photo[7] = "photo"
        runtime.stalk_monitor.profiles[7] = {"name": "Anna"}
        await started.wait()
        self.assert_removed(await self.remove())
        self.assertTrue(task.cancelled())
        for cache in (self.service.profile_tasks, self.service.profiles, self.service.profile_refresh_at,
                      self.service.profile_requested_photo, runtime.stalk_monitor.profiles):
            self.assertNotIn(7, cache)


class DesktopSurveillanceRemovalTests(MonitorRemovalCases, unittest.IsolatedAsyncioTestCase):
    field, prefix, target, id_key, items_key = "surveillance", "group_", -100, "chat_id", "groups"

    async def test_loading_available_chats_does_not_restore_removed_group(self):
        async def dialogs(**kwargs):
            yield SimpleNamespace(chat=SimpleNamespace(id=-100, type=runtime.enums.ChatType.SUPERGROUP,
                                                       title="Gruppo di prova", username="testgroup"))

        await self.remove()
        for bridge in (self.bridge, DesktopBridge()):
            self.addAsyncCleanup(bridge.close)
            bridge.connection = "connected"
            bridge.client = SimpleNamespace(get_dialogs=dialogs)
            chats = await bridge.dispatch("surveillance_chats", {})
            self.assertEqual(chats["chats"][0]["id"], "-100")
            overview = await bridge.dispatch("surveillance_overview", {})
            self.assertNotIn("-100", {group["id"] for group in overview["groups"]})


if __name__ == "__main__":
    unittest.main()
