import json
import re
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums

from Cogs.core import runtime


class MinimalMenuTests(unittest.TestCase):
    def test_minimal_menus_keep_order_and_syntax_without_descriptions(self):
        with patch.object(runtime, "state", runtime.MonitorState(minimal_mode=True)):
            menu = runtime.help_text(">")
            self.assertNotIn("»", menu)
            self.assertEqual(menu.splitlines()[1:-1], [
                ">admin", ">abuse", ">animated", ">fun", ">text", ">misc", ">mass",
                ">tools", ">osint", ">soundcloud", ">settings",
            ])
            for category, entries in runtime.HELP_CATEGORIES.items():
                first = runtime.help_text(">", category)
                count = re.search(r"Pagina 1/(\d+)", first)
                total = int(count[1]) if count else 1
                outputs = [runtime.help_text(">", category, page=page) for page in range(1, total + 1)]
                for output in outputs:
                    self.assertNotIn("»", output)
                self.assertEqual([line for output in outputs for line in output.splitlines() if line.startswith(">")],
                                 [f">{name} {usage}".rstrip() for name, usage, _ in entries])
            detail = runtime.help_text(">", "minimal-mode")
            self.assertEqual(detail, "[ MELIXSA / MINIMAL-MODE ]\n>minimal-mode [on|off]")
            self.assertNotIn("»", runtime.help_text(">", "unknown"))

    def test_full_menu_restores_descriptions(self):
        with patch.object(runtime, "state", runtime.MonitorState(minimal_mode=False)):
            self.assertIn("»", runtime.help_text(">", "settings"))
            self.assertIn(runtime.HELP_DETAILS["minimal-mode"], runtime.help_text(">", "minimal-mode"))

    def test_saved_mode_survives_restart_and_older_state_defaults_off(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "state.json"
            with patch.object(runtime, "STATE_FILE", file), patch.object(runtime, "DATA_DIR", Path(folder)):
                file.write_text(json.dumps({"prefix": ">"}), encoding="utf-8")
                self.assertFalse(runtime.MonitorState.load().minimal_mode)
                state = runtime.MonitorState(minimal_mode=True)
                state.save()
                self.assertTrue(runtime.MonitorState.load().minimal_mode)


class MinimalCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_toggle_status_validation_and_failed_save(self):
        state = runtime.MonitorState()
        message = SimpleNamespace(chat=SimpleNamespace(id=1, type=enums.ChatType.PRIVATE))
        with patch.object(runtime, "state", state), patch.object(state, "save") as save, \
             patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await runtime.handle_command(None, message, "minimal-mode", "on")
            self.assertTrue(state.minimal_mode)
            await runtime.handle_command(None, message, "minimal-mode", "")
            self.assertEqual(respond.call_args.args[1], "Minimal-mode on")
            self.assertEqual(save.call_count, 1)
            await runtime.handle_command(None, message, "minimal-mode", "off")
            self.assertFalse(state.minimal_mode)
            with self.assertRaises(ValueError):
                await runtime.handle_command(None, message, "minimal-mode", "invalid")
            self.assertEqual(save.call_count, 2)
            save.side_effect = OSError("read only")
            with self.assertRaises(OSError):
                await runtime.handle_command(None, message, "minimal-mode", "on")
            self.assertFalse(state.minimal_mode)


if __name__ == "__main__":
    unittest.main()
