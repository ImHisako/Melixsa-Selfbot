import asyncio
import logging
from collections import deque
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums
from pyrogram.errors import FloodWait

from Cogs.core import console_tools, runtime
from Cogs.settings import configuration_status
from Cogs.settings import permitted_command
from Cogs.core.error_tools import ErrorNotifier


class DoctorTests(unittest.IsolatedAsyncioTestCase):
    async def test_doctor_works_with_services_off_and_scrubs_secrets(self):
        message = SimpleNamespace(chat=SimpleNamespace(id=1, type=enums.ChatType.PRIVATE))
        secret = "test-secret-do-not-display"
        errors = deque([("now", f"failed {secret}")])
        with patch.object(runtime, "state", runtime.MonitorState()), patch.object(runtime, "respond", new_callable=AsyncMock) as respond, \
             patch.object(console_tools, "_secrets", [secret]), patch.object(console_tools, "recent_errors", errors):
            await runtime.handle_command(SimpleNamespace(is_connected=True), message, "doctor", "")
            text = "\n".join(call.args[1] for call in respond.call_args_list)
            self.assertIn("Telegram » connesso", text)
            self.assertIn("Worker log", text)
            self.assertIn("[redacted]", text)
            self.assertNotIn(secret, text)
            self.assertTrue(all(len(call.args[1].encode("utf-16-le")) // 2 <= 3400 for call in respond.call_args_list))
            with self.assertRaises(ValueError): await runtime.handle_command(None, message, "doctor", "invalid")

    async def test_new_settings_are_owner_only_even_if_stale_permissions_grant_them(self):
        with patch.object(runtime, "state", runtime.MonitorState(shared_commands={"doctor", "errornotify", "logconfig", "osintjobs", "osintcancel"})):
            for command in ("doctor", "errornotify", "logconfig"):
                self.assertFalse(permitted_command(command, ""))
            self.assertTrue(permitted_command("osintjobs", ""))

    async def test_logconfig_validation_persistence_and_cleanup(self):
        state = runtime.MonitorState()
        message = SimpleNamespace(chat=SimpleNamespace(id=1, type=enums.ChatType.PRIVATE))
        with patch.object(runtime, "state", state), patch.object(state, "save") as save, \
             patch.object(runtime, "respond", new_callable=AsyncMock), patch.object(runtime.writer, "cleanup", new_callable=AsyncMock) as cleanup:
            for argument in ("size 65536", "backups 3", "days 7"):
                await runtime.handle_command(None, message, "logconfig", argument)
            self.assertEqual((state.log_max_bytes, state.log_backups, state.log_retention_days), (65536, 3, 7))
            self.assertEqual(save.call_count, 3)
            self.assertEqual(cleanup.await_count, 3)
            for argument in ("size 1", "backups 0", "days -1", "days 4000", "size invalid", "unknown 1"):
                with self.assertRaises(ValueError): await runtime.handle_command(None, message, "logconfig", argument)
            self.assertEqual(save.call_count, 3)

    def test_configuration_checks_format_without_showing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            secret = "a" * 32
            (path / ".env").write_text(f"TELEGRAM_API_ID=1234\nTELEGRAM_API_HASH={secret}\nGEOSEEER_API_KEY=private-key\n")
            with patch.dict("os.environ", {}, clear=True):
                text = configuration_status(path)
            self.assertIn("formato valido", text)
            self.assertIn("chiave configurata", text)
            self.assertNotIn(secret, text)
            self.assertNotIn("private-key", text)

    def test_recent_errors_are_bounded_and_redacted(self):
        with patch.object(console_tools, "recent_errors", deque(maxlen=10)), patch.object(console_tools, "_secrets", ["secret123"]):
            for index in range(15): console_tools.event("Error", f"{index} secret123", error=True)
            self.assertEqual(len(console_tools.recent_errors), 10)
            self.assertNotIn("secret123", str(console_tools.recent_errors))

    def test_library_errors_are_collected_without_duplicate_application_events(self):
        handler = console_tools.RecentErrorHandler(level=logging.ERROR)
        with patch.object(console_tools, "recent_errors", deque(maxlen=10)), patch.object(console_tools, "error_callback") as callback:
            handler.emit(logging.LogRecord("pyrogram.session", logging.ERROR, "", 0, "connection failed", (), None))
            self.assertEqual(len(console_tools.recent_errors), 1)
            callback.assert_called_once()
            handler.emit(logging.LogRecord("melixsa", logging.ERROR, "", 0, "already recorded", (), None))
            self.assertEqual(len(console_tools.recent_errors), 1)


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_by_default_and_rate_limited_without_error_content(self):
        enabled = False
        sent = asyncio.Event()
        client = SimpleNamespace(send_message=AsyncMock(side_effect=lambda *a, **kw: sent.set()))
        notifier = ErrorNotifier(client, lambda: enabled, interval=0.05)
        self.addAsyncCleanup(notifier.close)
        notifier.signal()
        await asyncio.sleep(0.01)
        client.send_message.assert_not_awaited()
        enabled = True
        notifier.signal()
        await asyncio.wait_for(sent.wait(), 1)
        sent.clear()
        for _ in range(3): notifier.signal()
        await asyncio.sleep(0.01)
        self.assertEqual(client.send_message.await_count, 1)
        await asyncio.wait_for(sent.wait(), 1)
        self.assertEqual(client.send_message.await_count, 2)
        self.assertEqual(client.send_message.call_args.args[0], "me")
        self.assertIn("Errori rilevati » 3", client.send_message.call_args.args[1])

    async def test_floodwait_does_not_create_recursive_notifications(self):
        client = SimpleNamespace(send_message=AsyncMock(side_effect=FloodWait(30)))
        notifier = ErrorNotifier(client, lambda: True)
        self.addAsyncCleanup(notifier.close)
        with patch.object(console_tools, "error_callback", notifier.signal):
            console_tools.event("Error", "sensitive target", error=True)
            for _ in range(10): await asyncio.sleep(0)
            self.assertEqual(client.send_message.await_count, 1)
            self.assertGreater(notifier.next_send, time.monotonic() + 29)
            self.assertFalse(notifier.event.is_set())
            self.assertNotIn("sensitive target", client.send_message.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
