from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import Cogs
import selfbot
from Cogs.core import catalog, router, runtime
from Cogs.core.osint_extras import checker


class SectionLayoutTests(unittest.TestCase):
    def test_each_menu_category_has_one_section_module(self):
        self.assertEqual(set(Cogs.SECTION_MODULES), set(catalog.HELP_CATEGORIES))
        section_files = {path.stem for path in Path(Cogs.__file__).parent.glob("*.py")
                         if path.stem != "__init__"}
        self.assertEqual(section_files, set(Cogs.SECTION_MODULES.values()))
        for category, name in Cogs.SECTION_MODULES.items():
            self.assertEqual(router.SECTIONS[category].handle_command.__module__, f"Cogs.{name}")
        names = [name for entries in catalog.HELP_CATEGORIES.values() for name, _, _ in entries]
        self.assertEqual(len(names), len(set(names)))

    def test_moved_core_keeps_original_data_locations(self):
        self.assertEqual(runtime.ROOT, selfbot.ROOT)
        self.assertEqual(runtime.DATA_DIR, selfbot.ROOT / "data")
        self.assertEqual(runtime.STATE_FILE, selfbot.ROOT / "data" / "state.json")
        self.assertEqual(checker.CACHE, selfbot.ROOT / "data" / "osint" / "wmn-data.json")


class SectionRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_command_and_alias_routes_to_its_catalog_category(self):
        with ExitStack() as stack:
            handlers = {category: stack.enter_context(patch.object(module, "handle_command", new_callable=AsyncMock))
                        for category, module in router.SECTIONS.items()}
            for entered in set(catalog.COMMAND_CATEGORIES) | set(runtime.luna_tools.ALIASES):
                command = runtime.luna_tools.ALIASES.get(entered, entered)
                category = catalog.COMMAND_CATEGORIES[command]
                for handler in handlers.values():
                    handler.reset_mock()
                with self.subTest(command=entered, section=category):
                    await runtime.handle_command("client", "message", entered, "argomento")
                    handlers[category].assert_awaited_once_with("client", "message", command, "argomento")
                    self.assertEqual(sum(handler.await_count for handler in handlers.values()), 1)

    async def test_category_menus_and_wrappers_keep_their_meaning(self):
        with patch.object(runtime, "send_help", new_callable=AsyncMock) as help_handler:
            for category in runtime.CATEGORY_COMMANDS:
                await runtime.handle_command(None, None, category, "")
                help_handler.assert_awaited_with(None, None, category)
        with patch.object(runtime, "handle_osint_command", new_callable=AsyncMock) as osint, \
             patch.object(runtime, "handle_soundcloud_command", new_callable=AsyncMock) as soundcloud:
            await runtime.handle_command("client", "message", "osint", "ip 1.1.1.1")
            osint.assert_awaited_once_with("message", "ip", "1.1.1.1", client="client")
            await runtime.handle_command("client", "message", "sc", "pause")
            soundcloud.assert_awaited_once_with("message", "scpause", "")

    async def test_text_and_fun_commands_still_send_their_results(self):
        message = SimpleNamespace(chat=SimpleNamespace(id=99), reply_to_message=None)
        with patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            for command, argument, expected in (
                ("shrug", "", r"¯\_(ツ)_/¯"),
                ("morse", "SOS", "... --- ..."),
                ("unmorse", "... --- ...", "SOS"),
                ("regional", "AZ", "🇦 🇿"),
                ("reverse", "abc", "cba"),
                ("rps", "sasso", "Tu » sasso"),
            ):
                respond.reset_mock()
                await runtime.handle_command(None, message, command, argument)
                respond.assert_awaited_once()
                self.assertIn(expected, respond.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
