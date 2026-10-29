import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pyrogram import enums
from pyrogram.errors import FloodWait

from Cogs.core import runtime
from Cogs.settings import default_shared_commands, handle_access_command, permitted_command


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorized_help_aliases_and_menus_preserve_incoming_message(self):
        state = runtime.MonitorState(command_users={100})
        with patch.object(runtime, "state", state), \
             patch.object(runtime, "handle_command", new_callable=AsyncMock) as handle:
            for text in ("/help", "/h osint", "/?", "/fun", "/osint"):
                message = self.message(text)
                await runtime.process_message(None, message, 99)
                message.delete.assert_not_awaited()
            self.assertEqual(handle.await_count, 5)

    @staticmethod
    def message(text):
        return SimpleNamespace(
            chat=SimpleNamespace(id=100, type=enums.ChatType.PRIVATE),
            from_user=SimpleNamespace(id=100), text=text, delete=AsyncMock(),
        )

    async def test_settings_aliases_and_wrappers_cannot_bypass_permissions(self):
        state = runtime.MonitorState(command_users={100}, shared_commands={"help", "prefix", "access", "anti-login"})
        with patch.object(runtime, "state", state), \
             patch.object(runtime, "handle_command", new_callable=AsyncMock) as handle, \
             patch.object(runtime.afk, "reply", new_callable=AsyncMock) as afk:
            for text in ("/prefix !", "/access add 101", "/antilogin off", "/osint ip 1.1.1.1", "/sc pause", "/soundcloud scpause"):
                await runtime.process_message(None, self.message(text), 99)
            handle.assert_not_awaited()
            self.assertEqual(afk.await_count, 6)
            state.shared_commands.add("scpause")
            await runtime.process_message(None, self.message("/sc pause"), 99)
            handle.assert_awaited_once_with(None, unittest.mock.ANY, "sc", "pause")
            state.command_users.clear()
            await runtime.process_message(None, self.message("/help"), 99)
            self.assertEqual(handle.await_count, 1)

    async def test_management_reply_revocation_command_selection_and_rollback(self):
        state = runtime.MonitorState()
        message = SimpleNamespace(reply_to_message=SimpleNamespace(from_user=SimpleNamespace(
            id=100, is_bot=False, first_name="Mario", last_name="Rossi")))
        with patch.object(runtime, "state", state), patch.object(state, "save") as save, \
             patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await handle_access_command(None, message, "")
            self.assertIn("/access add", respond.call_args.args[1])
            await handle_access_command(None, message, "add")
            self.assertEqual(state.command_users, {100})
            self.assertIn("100 (Mario Rossi)", respond.call_args.args[1])
            await handle_access_command(None, message, "allow /whois")
            self.assertIn("whois", state.shared_commands)
            await handle_access_command(None, message, "block whois")
            self.assertNotIn("whois", state.shared_commands)
            await handle_access_command(None, message, "remove")
            self.assertFalse(state.command_users)
            self.assertIn("100 (Mario Rossi)", respond.call_args.args[1])
            for value in ("allow prefix", "allow access", "allow antilogin", "allow unknown", "allow abuse", "allow spam", "allow spamstop"):
                with self.assertRaises(ValueError):
                    await handle_access_command(None, message, value)
            save.side_effect = OSError("read only")
            with self.assertRaises(OSError):
                await handle_access_command(None, message, "add")
            self.assertFalse(state.command_users)

    async def test_list_displays_names_next_to_ids_and_keeps_unresolved_users(self):
        state = runtime.MonitorState(command_users={300, 100, 200})
        client = SimpleNamespace(get_users=AsyncMock(return_value=[
            SimpleNamespace(id=200, first_name="Anna", last_name=None),
            SimpleNamespace(id=100, first_name="Mario", last_name="Rossi"),
        ]))
        with patch.object(runtime, "state", state), \
             patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            for argument in ("", "list"):
                await handle_access_command(client, None, argument)
                self.assertIn("100 (Mario Rossi)\n200 (Anna)\n300 (Nome non disponibile)",
                              respond.call_args.args[1])
        client.get_users.assert_awaited_with([100, 200, 300])

    async def test_list_keeps_ids_when_telegram_cannot_resolve_names(self):
        state = runtime.MonitorState(command_users={100})
        client = SimpleNamespace(get_users=AsyncMock(side_effect=FloodWait(30)))
        with patch.object(runtime, "state", state), \
             patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await handle_access_command(client, None, "list")
        self.assertIn("100 (Nome non disponibile)", respond.call_args.args[1])
        self.assertEqual(state.command_users, {100})

    def test_saved_permissions_and_legacy_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "state.json"
            with patch.object(runtime, "STATE_FILE", file), patch.object(runtime, "DATA_DIR", Path(folder)):
                file.write_text("{}", encoding="utf-8")
                self.assertEqual(runtime.MonitorState.load().shared_commands, default_shared_commands())
                self.assertFalse(runtime.MonitorState.load().command_users)
                runtime.MonitorState(command_users={100}, shared_commands={"help", "whois"}).save()
                loaded = runtime.MonitorState.load()
                self.assertEqual(loaded.command_users, {100})
                self.assertEqual(loaded.shared_commands, {"help", "whois"})
                file.write_text(json.dumps({"command_users": [True, -1, "100", 100], "shared_commands": []}), encoding="utf-8")
                self.assertEqual(runtime.MonitorState.load().command_users, {100})
                self.assertEqual(runtime.MonitorState.load().shared_commands, set())

    async def test_categories_can_be_blocked_and_allowed_with_alias_and_prefix(self):
        state = runtime.MonitorState(prefix=">")
        with patch.object(runtime, "state", state), patch.object(state, "save"), \
             patch.object(runtime, "respond", new_callable=AsyncMock):
            for category in ("admin", "fun", "misc", "soundcloud", "mass"):
                canonical = runtime.HELP_CATEGORY_ALIASES.get(category, category)
                commands = {name for name, _, _ in runtime.HELP_CATEGORIES[canonical]}
                await handle_access_command(None, None, f"block {category}")
                self.assertTrue(commands.isdisjoint(state.shared_commands))
                await handle_access_command(None, None, f"allow >{category}")
                self.assertTrue(commands <= state.shared_commands)
            self.assertTrue(permitted_command("sc", "pause"))
            self.assertTrue(permitted_command("unafk", ""))
            with self.assertRaises(ValueError):
                await handle_access_command(None, None, "allow settings")
            with self.assertRaises(ValueError):
                await handle_access_command(None, None, "block settings")

    def test_default_permissions_cover_all_requested_categories(self):
        state = runtime.MonitorState()
        with patch.object(runtime, "state", state):
            for category, entries in runtime.HELP_CATEGORIES.items():
                for name, _, _ in entries:
                    expected = name == "help" or category not in {"settings", "abuse", "soundcloud", "misc"}
                    self.assertEqual(permitted_command(name, ""), expected, name)
            self.assertTrue(permitted_command("osint", "ip 1.1.1.1"))
            self.assertFalse(permitted_command("sc", "pause"))
            self.assertFalse(permitted_command("unafk", ""))

    async def test_blocked_categories_help_aliases_and_stale_abuse_grants(self):
        state = runtime.MonitorState(command_users={100})
        state.shared_commands.update({"spam", "spamstop", "prefix"})
        with patch.object(runtime, "state", state), \
             patch.object(runtime, "handle_command", new_callable=AsyncMock) as handle, \
             patch.object(runtime.afk, "reply", new_callable=AsyncMock):
            for text in ("/abuse", "/spam ciao 5 0", "/spamstop", "/settings", "/soundcloud", "/sc",
                         "/misc", "/profile", "/help abuse", "/h settings", "/? sc", "/help spam"):
                await runtime.process_message(None, self.message(text), 99)
            handle.assert_not_awaited()
            # Una categoria bloccata con access non resta accessibile tramite il menu.
            state.shared_commands.difference_update(name for name, _, _ in runtime.HELP_CATEGORIES["fun"])
            self.assertFalse(permitted_command("fun", ""))
            self.assertFalse(permitted_command("help", "fun"))
            state.shared_commands.add("scpause")
            self.assertTrue(permitted_command("sc", ""))
            self.assertTrue(permitted_command("sc", "pause"))
            self.assertFalse(permitted_command("sc", "play"))

    def test_shared_help_filters_menus_and_individual_commands(self):
        state = runtime.MonitorState(shared_commands={"help", "scpause", "whois"})
        with patch.object(runtime, "state", state):
            token = runtime.shared_command_context.set(True)
            try:
                menu = runtime.help_text(">")
                for category in ("abuse", "settings", "misc", "osint"):
                    self.assertNotIn(f">{category}", menu)
                self.assertIn(">soundcloud", menu)
                detail = runtime.help_text(">", "soundcloud")
                self.assertIn(">scpause", detail)
                self.assertNotIn(">scplay", detail)
                self.assertIn("non disponibile", runtime.help_text(">", "settings"))
            finally:
                runtime.shared_command_context.reset(token)
            self.assertIn(">abuse", runtime.help_text(">"))
            self.assertIn(">settings", runtime.help_text(">"))
