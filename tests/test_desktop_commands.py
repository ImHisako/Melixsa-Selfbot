import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Cogs.core import catalog, runtime
from MelixsaUI.backend.bridge import DesktopBridge
from MelixsaUI.backend.commands import command_catalog


class DesktopCommandCatalogTests(unittest.TestCase):
    def test_all_commands_aliases_and_categories_are_represented(self):
        result = command_catalog()
        represented = set()
        canonical = []
        for section in result["categories"]:
            represented.update([section["id"], *section["aliases"]])
            self.assertNotIn(" ", section["shortcut"])
            self.assertIn(section["shortcut"], {section["id"], *section["aliases"]})
            for command in section["commands"]:
                canonical.append(command["name"])
                represented.update([command["name"], *command["aliases"]])
        self.assertEqual(len(canonical), len(set(canonical)))
        self.assertEqual(represented, catalog.COMMANDS)

    def test_syntax_and_details_match_the_selfbot_help(self):
        for section in command_catalog()["categories"]:
            expected = catalog.HELP_CATEGORIES[section["id"]]
            self.assertEqual([(item["name"], item["usage"], item["description"]) for item in section["commands"]], list(expected))
            for command in section["commands"]:
                self.assertEqual(command["details"], catalog.HELP_DETAILS.get(command["name"], command["description"]))

    def test_help_aliases_are_included(self):
        commands = {command["name"]: command for section in command_catalog()["categories"] for command in section["commands"]}
        self.assertEqual(commands["help"]["aliases"], ["?", "h"])
        self.assertIn("morse", commands["encodemorsecode"]["aliases"])
        self.assertIn("unafk", commands["back"]["aliases"])

    def test_browser_catalog_is_current(self):
        path = Path(__file__).resolve().parents[1] / "MelixsaUI/src/catalog/commands.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), command_catalog(),
                         "Rigenera con .venv/Scripts/python.exe MelixsaUI/scripts/export-command-catalog.py")

    def test_result_cannot_mutate_the_source_catalog(self):
        first = command_catalog()
        first["categories"][0]["commands"][0]["aliases"].append("fake")
        first["categories"].clear()
        second = command_catalog()
        self.assertEqual(len(second["categories"]), len(catalog.HELP_CATEGORIES))
        self.assertNotIn("fake", second["categories"][0]["commands"][0]["aliases"])


class DesktopCommandDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_is_available_offline_without_loading_personal_state(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runtime, "DATA_DIR", Path(directory)), patch.object(runtime, "state_lock", asyncio.Lock()):
                bridge = DesktopBridge()
                try:
                    with patch.object(runtime.MonitorState, "load", side_effect=AssertionError("State access")):
                        self.assertEqual(await bridge.dispatch("command_catalog", {}), command_catalog())
                    self.assertEqual(bridge.connection, "offline")
                    self.assertIsNone(bridge.client)
                finally:
                    await bridge.close()


if __name__ == "__main__":
    unittest.main()
