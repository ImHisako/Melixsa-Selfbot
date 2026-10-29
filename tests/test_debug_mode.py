import json
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums

from Cogs.core import console_tools, runtime


class DebugFilterTests(unittest.TestCase):
    def test_library_details_and_marked_events_follow_live_setting(self):
        records = [logging.LogRecord(name, logging.INFO, "", 0, "Connection established", (), None)
                   for name in ("pyrogram.connection.connection", "pyrogram.session.session", "websockets.server")]
        startup = logging.LogRecord("melixsa", logging.INFO, "", 0, "Telegram connesso", (), None)
        startup.debug_only = True
        records.append(startup)
        gate = console_tools.DebugModeFilter()
        with patch.object(console_tools, "_settings", dict(debug_mode=False)):
            self.assertTrue(all(not gate.filter(record) for record in records))
            console_tools.configure(dict(debug_mode=True))
            self.assertTrue(all(gate.filter(record) for record in records))
            console_tools.configure(dict(debug_mode=False))
            self.assertTrue(all(not gate.filter(record) for record in records))

    def test_commands_and_library_warnings_errors_remain_visible(self):
        gate = console_tools.DebugModeFilter()
        with patch.object(console_tools, "_settings", dict(debug_mode=False)):
            command = logging.LogRecord("melixsa", logging.INFO, "", 0, ">help", (), None)
            self.assertTrue(gate.filter(command))
            for name in ("pyrogram.session", "websockets.server", "melixsa"):
                for level in (logging.WARNING, logging.ERROR):
                    record = logging.LogRecord(name, level, "", 0, "Problema", (), None)
                    record.debug_only = True
                    self.assertTrue(gate.filter(record))

    def test_state_migration_defaults_off_and_saved_value_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            state_file = Path(folder) / "state.json"
            with patch.object(runtime, "STATE_FILE", state_file), patch.object(runtime, "DATA_DIR", Path(folder)):
                self.assertFalse(runtime.MonitorState.load().console["debug_mode"])
                state_file.write_text(json.dumps({"console": {"timestamp": False}}), encoding="utf-8")
                state = runtime.MonitorState.load()
                self.assertFalse(state.console["debug_mode"])
                self.assertFalse(state.console["timestamp"])
                state.console["debug_mode"] = True
                state.save()
                self.assertTrue(runtime.MonitorState.load().console["debug_mode"])
                state_file.write_text(json.dumps({"console": {"debug_mode": "on"}}), encoding="utf-8")
                self.assertFalse(runtime.MonitorState.load().console["debug_mode"])


class DebugCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_command_updates_filter_and_saves_then_reports_status(self):
        state = runtime.MonitorState(prefix=">")
        msg = SimpleNamespace(chat=SimpleNamespace(id=1, type=enums.ChatType.PRIVATE))
        with patch.object(runtime, "state", state), patch.object(state, "save") as save, \
             patch.object(console_tools, "_settings", console_tools.CONSOLE_DEFAULTS.copy()), \
             patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await runtime.handle_command(None, msg, "debug-mode", "on")
            self.assertTrue(state.console["debug_mode"])
            self.assertTrue(console_tools._settings["debug_mode"])
            save.assert_called_once()
            await runtime.handle_command(None, msg, "debug-mode", "")
            self.assertIn("on", respond.call_args.args[1])
            self.assertEqual(save.call_count, 1)
            await runtime.handle_command(None, msg, "debug-mode", "off")
            self.assertFalse(console_tools._settings["debug_mode"])
            self.assertEqual(save.call_count, 2)
            with self.assertRaises(ValueError):
                await runtime.handle_command(None, msg, "debug-mode", "invalid")
            self.assertEqual(save.call_count, 2)
        self.assertIn(">debug-mode", runtime.help_text(">", "settings"))
        self.assertNotIn("Voce sconosciuta", runtime.help_text(">", "debug-mode"))

    async def test_failed_save_does_not_activate_debug_mode(self):
        state = runtime.MonitorState()
        msg = SimpleNamespace(chat=SimpleNamespace(id=1, type=enums.ChatType.PRIVATE))
        with patch.object(runtime, "state", state), patch.object(state, "save", side_effect=OSError("read only")), \
             patch.object(console_tools, "_settings", console_tools.CONSOLE_DEFAULTS.copy()):
            with self.assertRaises(OSError):
                await runtime.handle_command(None, msg, "debug-mode", "on")
            self.assertFalse(state.console["debug_mode"])
            self.assertFalse(console_tools._settings["debug_mode"])


if __name__ == "__main__":
    unittest.main()
