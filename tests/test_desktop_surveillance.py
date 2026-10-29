import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums

from Cogs.core import runtime
from Cogs.core.instance_tools import InstanceLock
from MelixsaUI.backend.bridge import DesktopBridge
from MelixsaUI.backend.surveillance import MAX_READ_BYTES, group_id


class DesktopSurveillanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        for name, value in {
            "DATA_DIR": self.root, "LOG_DIR": self.logs,
            "STATE_FILE": self.root / "state.json", "state": runtime.MonitorState(),
            "state_lock": asyncio.Lock(),
        }.items():
            patcher = patch.object(runtime, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        runtime.state.save()
        self.bridge = DesktopBridge()
        self.addAsyncCleanup(self.bridge.close)
        self.chat = SimpleNamespace(id=-100, type=enums.ChatType.SUPERGROUP, title="Gruppo di prova", username="testgroup")
        self.client = SimpleNamespace(
            get_chat=AsyncMock(return_value=self.chat),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status=enums.ChatMemberStatus.MEMBER)),
        )

    def connect(self):
        self.bridge.connection = "connected"
        self.bridge.client = self.client

    def write_log(self, name="group_-100.txt", records=None):
        records = records if records is not None else [self.record(1)]
        path = self.logs / name
        path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
        return path

    @staticmethod
    def record(message_id, **extra):
        return {"chat_id": -100, "chat_name": "Gruppo di prova", "event": "new", "message_id": message_id,
                "date": "2026-10-29T10:00:00+00:00", "name": "Anna", "username": "anna", "text": f"Messaggio {message_id}", **extra}

    async def test_enable_resolves_username_and_uses_shared_persistent_state(self):
        self.connect()
        runtime.state.prefix = "!"
        runtime.state.stalk = {7}
        result = await self.bridge.dispatch("surveillance_set", {"chat": "@testgroup", "enabled": True})
        self.client.get_chat.assert_awaited_once_with("@testgroup")
        self.client.get_chat_member.assert_awaited_once_with(-100, "me")
        self.assertEqual(runtime.state.surveillance, {-100})
        saved = runtime.MonitorState.load()
        self.assertEqual(saved.surveillance, {-100})
        self.assertEqual(saved.prefix, "!")
        self.assertEqual(saved.stalk, {7})
        self.assertEqual(result["changed_id"], "-100")
        self.assertTrue(result["groups"][0]["enabled"])

    async def test_enable_rejects_private_chats_and_channels(self):
        self.connect()
        for kind in (enums.ChatType.PRIVATE, enums.ChatType.CHANNEL):
            self.chat.type = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                await self.bridge.dispatch("surveillance_set", {"chat": "-100", "enabled": True})
        self.assertEqual(runtime.state.surveillance, set())
        self.client.get_chat_member.assert_not_awaited()

    async def test_enable_rejects_groups_the_account_has_left(self):
        self.connect()
        for status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.RESTRICTED):
            self.client.get_chat_member.return_value = SimpleNamespace(status=status, is_member=False)
            with self.subTest(status=status), self.assertRaises(ValueError):
                await self.bridge.dispatch("surveillance_set", {"chat": "-100", "enabled": True})
        self.assertEqual(runtime.MonitorState.load().surveillance, set())

    async def test_enable_requires_a_live_connection(self):
        with self.assertRaises(ValueError):
            await self.bridge.dispatch("surveillance_set", {"chat": "-100", "enabled": True})
        self.client.get_chat.assert_not_awaited()

    async def test_failed_save_rolls_back_monitoring(self):
        self.connect()
        with patch.object(runtime.state, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await self.bridge.dispatch("surveillance_set", {"chat": "-100", "enabled": True})
        self.assertEqual(runtime.state.surveillance, set())

    async def test_stop_offline_preserves_logs_and_other_preferences(self):
        runtime.state.surveillance = {-100, -200}
        runtime.state.autoreact = True
        runtime.state.save()
        path = self.write_log()
        original = path.read_bytes()
        result = await self.bridge.dispatch("surveillance_set", {"chat": "-100", "enabled": False})
        self.assertEqual(runtime.MonitorState.load().surveillance, {-200})
        self.assertTrue(runtime.MonitorState.load().autoreact)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(next(group for group in result["groups"] if group["id"] == "-100")["enabled"])

    async def test_offline_stop_respects_the_other_runtime_lock(self):
        runtime.state.surveillance = {-100}
        runtime.state.save()
        with InstanceLock(self.root / "runtime.lock"):
            with self.assertRaises(RuntimeError):
                await self.bridge.dispatch("surveillance_set", {"chat": "-100", "enabled": False})
        self.assertEqual(runtime.MonitorState.load().surveillance, {-100})

    async def test_boolean_and_group_id_validation(self):
        self.connect()
        for params in ({"chat": "-100", "enabled": 1}, {"chat": "-100", "enabled": "on"},
                       {"chat": "../state.json", "enabled": False}, {"chat": True, "enabled": False},
                       {"chat": "100", "enabled": False}, {"chat": "-9223372036854775809", "enabled": False}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                await self.bridge.dispatch("surveillance_set", params)
        self.assertEqual(group_id("-1001234567890"), -1001234567890)

    async def test_overview_includes_active_and_archived_groups_with_names(self):
        runtime.state.surveillance = {-100, -200}
        runtime.state.save()
        current = self.write_log()
        archive = self.write_log("group_-100.txt.123", [self.record(0)])
        self.write_log("stalk_7.txt")
        result = await self.bridge.dispatch("surveillance_overview", {})
        self.assertEqual(result["active_count"], 2)
        self.assertEqual({item["id"] for item in result["groups"]}, {"-100", "-200"})
        group = next(group for group in result["groups"] if group["id"] == "-100")
        self.assertEqual(group["title"], "Gruppo di prova")
        self.assertEqual(group["log_files"], 2)
        self.assertEqual(group["log_bytes"], current.stat().st_size + archive.stat().st_size)
        self.assertIsNotNone(group["last_update"])

    async def test_log_reader_orders_current_and_rotated_files_and_preserves_unicode(self):
        self.write_log("group_-100.txt.100", [self.record(1)])
        self.write_log("group_-100.txt.200", [self.record(2)])
        self.write_log(records=[self.record(3), self.record(4, event="edited", text="Ciao 🌙\nSeconda riga", edit_date="2026-10-29T10:01:00+00:00")])
        result = await self.bridge.dispatch("surveillance_logs", {"chat_id": "-100"})
        self.assertEqual([record["message_id"] for record in result["records"]], ["4", "3", "2", "1"])
        self.assertEqual(result["records"][0]["text"], "Ciao 🌙\nSeconda riga")
        self.assertEqual(result["records"][0]["event"], "edited")
        self.assertEqual(result["records"][0]["date"], "2026-10-29T10:01:00+00:00")

    async def test_log_reader_ignores_partial_and_wrong_group_records(self):
        path = self.write_log(records=[self.record(1), self.record(2, chat_id=-200)])
        with path.open("ab") as output:
            output.write(b'{"partial":')
        result = await self.bridge.dispatch("surveillance_logs", {"chat_id": "-100"})
        self.assertEqual([record["message_id"] for record in result["records"]], ["1"])
        self.assertEqual(result["skipped"], 2)

    async def test_log_reader_caps_records_at_100(self):
        self.write_log(records=[self.record(index) for index in range(150)])
        result = await self.bridge.dispatch("surveillance_logs", {"chat_id": "-100"})
        self.assertEqual(len(result["records"]), 100)
        self.assertEqual(result["records"][0]["message_id"], "149")
        self.assertEqual(result["records"][-1]["message_id"], "50")
        self.assertTrue(result["limited"])

    async def test_oversized_log_lines_do_not_exceed_the_read_budget(self):
        self.write_log(records=[self.record(1, text="x" * (MAX_READ_BYTES + 1024))])
        result = await self.bridge.dispatch("surveillance_logs", {"chat_id": "-100"})
        self.assertEqual(result["records"], [])
        self.assertTrue(result["limited"])

    async def test_unknown_group_and_path_traversal_are_rejected(self):
        for chat_id in ("-999", "../../.env", "/etc/passwd", 1, False):
            with self.subTest(chat_id=chat_id), self.assertRaises(ValueError):
                await self.bridge.dispatch("surveillance_logs", {"chat_id": chat_id})

    async def test_load_chats_filters_groups_without_enabling_them(self):
        self.connect()
        async def dialogs(**kwargs):
            self.assertEqual(kwargs, {"limit": 200})
            yield SimpleNamespace(chat=self.chat)
            yield SimpleNamespace(chat=SimpleNamespace(type=enums.ChatType.PRIVATE))
            yield SimpleNamespace(chat=SimpleNamespace(type=enums.ChatType.CHANNEL))
        self.client.get_dialogs = dialogs
        result = await self.bridge.dispatch("surveillance_chats", {})
        self.assertEqual(result["chats"], [{"id": "-100", "title": "Gruppo di prova", "username": "testgroup"}])
        self.assertEqual(runtime.MonitorState.load().surveillance, set())


if __name__ == "__main__":
    unittest.main()
