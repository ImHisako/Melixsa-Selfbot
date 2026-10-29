import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums

from Cogs.core import persistence_tools, runtime


class StateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "state.json"
        self.backup = persistence_tools.backup_path(self.path)
        for name, value in (("STATE_FILE", self.path), ("DATA_DIR", self.path.parent)):
            patcher = patch.object(runtime, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_valid_backups_and_corrupt_main_recovery_preserve_original(self):
        state = runtime.MonitorState(prefix="!", command_users={100})
        state.save()
        state.prefix = ">"
        state.save()
        self.assertEqual(json.loads(self.backup.read_text())["prefix"], "!")
        for bad in ("{", "[]", '{"surveillance": null}', '{"stalk": {"-1": 3}}', '{"surveillance": [true]}'):
            with self.subTest(bad=bad):
                self.path.write_text(bad, encoding="utf-8")
                restored = runtime.MonitorState.load()
                self.assertEqual(restored.prefix, "!")
                self.assertEqual(restored.command_users, {100})
                self.assertIn("backup", restored.load_warning)
                self.assertEqual(self.path.read_text(), bad)
        restored.save()
        self.assertEqual(runtime.MonitorState.load().prefix, "!")
        self.assertTrue(list(self.path.parent.glob("state.json.corrupt-*")))

    def test_missing_main_uses_backup_and_both_invalid_fail_closed(self):
        self.backup.write_text('{"prefix": "!"}', encoding="utf-8")
        self.assertEqual(runtime.MonitorState.load().prefix, "!")
        self.path.write_text("bad", encoding="utf-8")
        self.backup.write_text("bad", encoding="utf-8")
        state = runtime.MonitorState.load()
        self.assertFalse(state.command_users)
        self.assertIn("predefinite", state.load_warning)
        state.save()
        self.assertIsInstance(json.loads(self.backup.read_text()), dict)

    def test_non_utf8_main_is_preserved_when_repaired(self):
        runtime.MonitorState(prefix="!").save()
        self.path.write_bytes(b"\xff\xfe")
        state = runtime.MonitorState.load()
        self.assertEqual(state.prefix, "!")
        state.save()
        preserved = list(self.path.parent.glob("state.json.corrupt-*"))
        self.assertEqual(preserved[0].read_bytes(), b"\xff\xfe")

    def test_failed_replace_preserves_primary_and_removes_temporary_files(self):
        state = runtime.MonitorState(prefix="!")
        state.save()
        old = self.path.read_bytes()
        state.prefix = ">"
        original = Path.replace
        def replace(path, target):
            if target == self.path:
                raise OSError("read only")
            return original(path, target)
        with patch.object(Path, "replace", replace):
            with self.assertRaises(OSError):
                state.save()
        self.assertEqual(self.path.read_bytes(), old)
        self.assertEqual(json.loads(self.backup.read_text())["prefix"], "!")
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_legacy_and_new_settings_survive_restart(self):
        self.path.write_text(json.dumps({"stalk": {"-1": ["10", 20]}, "log_max_bytes": 1, "log_backups": True}), encoding="utf-8")
        state = runtime.MonitorState.load()
        self.assertEqual(state.stalk, {10, 20})
        self.assertEqual(state.log_max_bytes, 10_000_000)
        self.assertEqual(state.log_backups, 5)
        state.error_notify, state.log_retention_days = True, 7
        state.save()
        loaded = runtime.MonitorState.load()
        self.assertTrue(loaded.error_notify)
        self.assertEqual(loaded.log_retention_days, 7)


class TransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_router_settings_rollback_on_failed_save(self):
        state = runtime.MonitorState(surveillance={-1}, stalk={10})
        private = SimpleNamespace(chat=SimpleNamespace(id=1, type=enums.ChatType.PRIVATE))
        group = SimpleNamespace(chat=SimpleNamespace(id=-1, type=enums.ChatType.SUPERGROUP))
        cases = [("prefix", "!", private), ("deleteafter", "0", private),
                 ("timestamp", "off", private), ("minimal-mode", "on", private),
                 ("debug-mode", "on", private), ("surveillance", "", group),
                 ("sustop", "", group), ("stalk", "20", group), ("unstalk", "10", group),
                 ("errornotify", "on", private), ("logconfig", "days 7", private)]
        original = asdict(state)
        with patch.object(runtime, "state", state), patch.object(state, "save", side_effect=OSError("disk full")), \
             patch.object(runtime, "resolve_user", new_callable=AsyncMock, return_value=SimpleNamespace(id=10)), \
             patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            for command, argument, message in cases:
                with self.subTest(command=command):
                    with self.assertRaises(OSError):
                        await runtime.handle_command(None, message, command, argument)
                    self.assertEqual(asdict(state), original)
            with self.assertRaises(OSError):
                await runtime.save_login_reset(100)
            self.assertEqual(state.anti_login_last_reset, 0)
            respond.assert_not_awaited()

    async def test_concurrent_changes_are_serialized(self):
        state = runtime.MonitorState()
        order = []
        async def change(prefix):
            async with runtime.state_transaction():
                order.append(prefix)
                state.prefix = prefix
                await asyncio.sleep(0)
                self.assertEqual(state.prefix, prefix)
        with patch.object(runtime, "state", state), patch.object(state, "save") as save:
            await asyncio.gather(change("!"), change(">"))
            self.assertEqual(order, ["!", ">"])
            self.assertEqual(save.call_count, 2)

    async def test_cancel_during_save_waits_for_disk_and_preserves_committed_value(self):
        import threading
        state = runtime.MonitorState()
        started, release = threading.Event(), threading.Event()
        def save():
            started.set()
            release.wait(2)
        async def change():
            async with runtime.state_transaction():
                state.prefix = "!"
        with patch.object(runtime, "state", state), patch.object(state, "save", side_effect=save):
            task = asyncio.create_task(change())
            await asyncio.to_thread(started.wait, 1)
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(state.prefix, "!")


if __name__ == "__main__":
    unittest.main()
