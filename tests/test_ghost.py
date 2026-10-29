import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums

from Cogs.core import backup_tools, ghost_tools, luna_tools, runtime
from Cogs.settings import permitted_command, shareable_commands
from Cogs.settings import handle_backup_command
from Cogs.core.io_tools import local_io


class TextToolsTests(unittest.TestCase):
    def test_morse_roundtrip_including_numbers_and_punctuation(self):
        text = 'SOS 123? EMAIL@HOME.IT + (OK) / TEST_1 & "YES"!'
        encoded = ghost_tools.transform("encodemorsecode", text)
        self.assertEqual(ghost_tools.transform("decodemorsecode", encoded), text)
        self.assertEqual(ghost_tools.transform("encodemorsecode", "sos\n help"), "... --- ... / .... . .-.. .--.")

    def test_morse_rejects_lossy_or_invalid_input(self):
        for command, value in (("encodemorsecode", "caffè"), ("encodemorsecode", "🖤"),
                               ("decodemorsecode", "......"), ("decodemorsecode", ". / / ."),
                               ("decodemorsecode", "hello"), ("encodemorsecode", "   ")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ghost_tools.transform(command, value)

    def test_native_code_preserves_symbols_and_replied_indentation(self):
        source = '    print("🖤 <b> ``` $()")\n    pass'
        for command, language in ghost_tools.CODE_LANGUAGES.items():
            self.assertEqual(ghost_tools.format_code(command, "", source), (language, source))
        self.assertEqual(ghost_tools.format_code("codeblock", "Python", source), ("python", source))
        for value in ("", "a" * 33, "python<script>"):
            with self.assertRaises(ValueError):
                ghost_tools.format_code("codeblock", value, source)

    def test_json_validation_pretty_print_and_bounds(self):
        language, value = ghost_tools.format_code("json", '{"emoji":"🖤", "items":[1,true,null]}')
        self.assertEqual(language, "json")
        self.assertIn('\n  "emoji": "🖤",', value)
        self.assertEqual(json.loads(value)["items"], [1, True, None])
        for value in ('{"a":}', "NaN", "Infinity", "[" * 1100, '"' + "a" * 1500 + '"'):
            with self.assertRaises(ValueError):
                ghost_tools.format_code("json", value)
        with self.assertRaises(ValueError):
            ghost_tools.telegram_text("🖤" * 2001)
        with self.assertRaises(ValueError):
            ghost_tools.transform("regional", "z" * 1500)

    def test_search_aliases_pagination_and_minimal_mode(self):
        categories = {"tools": (("passgen", "[N]", "Password casuale"),)}
        result = ghost_tools.command_page(categories, ghost_tools.ALIASES, "!", query="genpassword")
        self.assertIn("!passgen [N]", result)
        self.assertIn("Risultati » 1", result)
        minimal = ghost_tools.command_page(categories, {}, "!", minimal=True)
        self.assertNotIn("Password casuale", minimal)
        all_pages = {"test": tuple((f"cmd{i:03}", "", "x" * 100) for i in range(100))}
        self.assertIn("Pagina 2/", ghost_tools.command_page(all_pages, {}, "/", page=2))
        for page in (0, -1, 99):
            with self.assertRaises(ValueError):
                ghost_tools.command_page(all_pages, {}, "/", page=page)

    def test_regional_randomcase_url_and_rps(self):
        self.assertEqual(ghost_tools.transform("regional", "Az!"), "🇦 🇿 !")
        self.assertEqual(ghost_tools.transform("randomcase", "Abc!? 123").casefold(), "abc!? 123")
        self.assertTrue(ghost_tools.transform("lmgtfy", "C++ & 🖤").endswith("C%2B%2B+%26+%F0%9F%96%A4"))
        with patch.object(ghost_tools._RNG, "randrange", return_value=2):
            self.assertIn("Hai vinto", ghost_tools.rps("sasso"))
            self.assertIn("Pareggio", ghost_tools.rps("scissors"))
            self.assertIn("Ha vinto Melixsa", ghost_tools.rps("paper"))
        with self.assertRaises(ValueError):
            ghost_tools.rps("invalid")


class BackupStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = backup_tools.BackupStore(self.root / "backups", runtime.MonitorState.from_raw)
        self.settings = backup_tools.settings_payload(runtime.MonitorState())

    def test_roundtrip_and_no_credentials_or_access_rights(self):
        state = runtime.MonitorState(prefix="!", command_users={100}, stalk={200}, surveillance={-300})
        settings = backup_tools.settings_payload(state)
        name = self.store.create(settings, {"note": "Contenuto 🖤"}, "prima")
        payload = self.store.load(name)
        self.assertEqual(payload["settings"], settings)
        self.assertEqual(payload["notes"], {"note": "Contenuto 🖤"})
        self.assertEqual(self.store.names(), ["prima"])
        for field in ("command_users", "shared_commands", "stalk", "surveillance", "anti_login_enabled",
                      "anti_login_last_reset", "api_hash", "session"):
            self.assertNotIn(field, settings)
        with self.assertRaises(ValueError):
            self.store.create(self.settings, {}, "prima")
        self.store.delete(name)
        self.assertEqual(self.store.names(), [])

    def test_rejects_traversal_reserved_names_corruption_and_overflow(self):
        for name in ("../escape", "a/b", "a\\b", "C:escape", ".", "con", "LPT1", "x" * 65):
            with self.assertRaises(ValueError):
                self.store.create(self.settings, {}, name)
        self.store.directory.mkdir()
        self.store.path("broken").write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.load("broken")
        self.store.path("huge").write_bytes(b" " * (backup_tools.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            self.store.load("huge")
        with patch.object(backup_tools, "MAX_BACKUPS", 2):
            with self.assertRaises(ValueError):
                self.store.create(self.settings, {})

    def test_modified_backup_must_validate_before_use(self):
        name = self.store.create(self.settings, {}, "valid")
        payload = self.store.load(name)
        changes = [lambda p: p["settings"].update(command_users=[100]),
                   lambda p: p["settings"].update(delete_after=True),
                   lambda p: p["settings"].update(prefix="abc"),
                   lambda p: p.update(version=2), lambda p: p.update(notes={"x": 1}),
                   lambda p: p.update(created_at="bad"), lambda p: p.update(token="secret")]
        for mutate in changes:
            changed = deepcopy(payload)
            mutate(changed)
            with self.assertRaises(ValueError):
                self.store.validate(changed)


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.state = runtime.MonitorState(prefix="!", command_users={100}, stalk={200}, surveillance={-300})
        self.store = backup_tools.BackupStore(self.root / "backups", runtime.MonitorState.from_raw)
        self.notes = luna_tools.Notes(self.root / "notes.json")
        self.history = ghost_tools.CommandHistory()
        self.message = SimpleNamespace(chat=SimpleNamespace(id=99, type=enums.ChatType.PRIVATE),
                                       id=10, from_user=SimpleNamespace(id=99), message_thread_id=7,
                                       reply_to_message=None, delete=AsyncMock(), answer=AsyncMock())
        patches = {"state": self.state, "STATE_FILE": self.root / "state.json", "DATA_DIR": self.root,
                   "backups": self.store, "notes": self.notes, "command_history": self.history,
                   "respond": AsyncMock(), "schedule_delete": unittest.mock.Mock()}
        for name, value in patches.items():
            patcher = patch.object(runtime, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(runtime.console_tools, "configure")
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_routing_code_uses_native_utf16_entities_and_same_topic(self):
        text = '🖤 <b> ``` print("test")'
        self.message.reply_to_message = SimpleNamespace(text=text)
        await runtime.handle_command(None, self.message, "pyblock", "")
        args, kwargs = self.message.answer.call_args
        self.assertEqual(args[0], text)
        self.assertEqual(kwargs["parse_mode"], enums.ParseMode.DISABLED)
        entity, = kwargs["entities"]
        self.assertEqual(entity.type, enums.MessageEntityType.PRE)
        self.assertEqual(entity.language, "python")
        self.assertEqual(entity.length, len(text.encode("utf-16-le")) // 2)
        runtime.schedule_delete.assert_called_once()

    async def test_search_and_list_respect_shared_permissions(self):
        self.state.shared_commands = {"help", "search", "allcmds", "json"}
        token = runtime.shared_command_context.set(True)
        try:
            await runtime.handle_command(None, self.message, "allcmds", "")
            result = runtime.respond.call_args.args[1]
            self.assertIn("!json", result)
            self.assertNotIn("!backup", result)
            self.assertNotIn("!commandhistory", result)
            await runtime.handle_command(None, self.message, "search", "cmdhistory")
            self.assertIn("Nessun comando", runtime.respond.call_args.args[1])
            for name in ("backup", "backups", "commandhistory", "cmdhistory"):
                self.assertFalse(permitted_command(name, ""))
                self.assertNotIn(name, shareable_commands())
                with self.assertRaises(ValueError):
                    await runtime.handle_command(None, self.message, name, "")
        finally:
            runtime.shared_command_context.reset(token)

    async def test_backup_restore_sections_preserve_security_and_make_safety_copy(self):
        self.notes.execute("note", "idea originale")
        await handle_backup_command(self.message, "backup", "create prima")
        self.state.prefix = ">"
        self.state.command_users.add(101)
        self.state.anti_login_enabled = False
        self.notes.execute("editnote", "idea modificata")
        await handle_backup_command(self.message, "backup", "restore prima settings")
        self.assertEqual(self.state.prefix, "!")
        self.assertEqual(self.state.command_users, {100, 101})
        self.assertEqual(self.state.stalk, {200})
        self.assertFalse(self.state.anti_login_enabled)
        self.assertEqual(self.notes.execute("shownote", "idea"), "modificata")
        self.assertEqual(runtime.MonitorState.load().prefix, "!")
        await handle_backup_command(self.message, "backup", "restore prima notes")
        self.assertEqual(self.notes.execute("shownote", "idea"), "originale")
        self.assertEqual(len(self.store.names()), 3)
        snapshots = [self.store.load(name) for name in self.store.names() if name != "prima"]
        self.assertTrue(any(p["settings"]["prefix"] == ">" for p in snapshots))
        self.assertTrue(all(p["notes"]["idea"] == "modificata" for p in snapshots))

    async def test_failed_settings_save_rolls_back_and_failed_snapshot_prevents_restore(self):
        self.store.create(backup_tools.settings_payload(runtime.MonitorState(prefix="/")), {}, "prima")
        with patch.object(self.state, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await handle_backup_command(self.message, "backup", "restore prima settings")
        self.assertEqual(self.state.prefix, "!")
        runtime.respond.assert_not_awaited()
        self.notes.execute("note", "idea attuale")
        with patch.object(self.store, "create", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await handle_backup_command(self.message, "backup", "restore prima notes")
        self.assertEqual(self.notes.execute("shownote", "idea"), "attuale")

    async def test_note_restore_does_not_write_unrelated_state_and_survives_failed_note_write(self):
        self.store.create(backup_tools.settings_payload(self.state), {"idea": "prima"}, "prima")
        self.notes.execute("note", "idea attuale")
        with patch.object(self.state, "save", side_effect=OSError("state read only")) as save:
            await handle_backup_command(self.message, "backup", "restore prima notes")
            save.assert_not_called()
        self.notes.execute("editnote", "idea attuale")
        original = runtime.persistence_tools.atomic_write
        def fail_notes(path, text):
            if path == self.notes.path:
                raise OSError("notes read only")
            return original(path, text)
        with patch.object(runtime.persistence_tools, "atomic_write", side_effect=fail_notes):
            with self.assertRaises(OSError):
                await handle_backup_command(self.message, "backup", "restore prima notes")
        self.assertEqual(self.notes.execute("shownote", "idea"), "attuale")

    async def test_history_is_bounded_canonical_and_never_stores_arguments(self):
        self.message.text = "!passwordgen secret-input"
        with patch.object(runtime, "handle_command", new_callable=AsyncMock):
            await runtime.process_message(None, self.message, 99)
        self.assertEqual(self.history.records[-1].command, "passgen")
        self.assertNotIn("secret-input", repr(self.history.records))
        for i in range(60):
            self.history.add("ping", True, 0.1)
        self.assertEqual(len(self.history.records), 50)
        self.message.text = "!cmdhistory clear"
        await runtime.process_message(None, self.message, 99)
        self.assertEqual(len(self.history.records), 0)
        self.message.text = "!calc invalid"
        with patch.object(runtime, "handle_command", new_callable=AsyncMock, side_effect=ValueError("invalid")):
            await runtime.process_message(None, self.message, 99)
        self.assertFalse(self.history.records[-1].success)

    async def test_io_cancellation_waits_for_write_before_unlock(self):
        import threading
        started, finish = threading.Event(), threading.Event()
        written = []
        def worker():
            started.set()
            finish.wait(timeout=5)
            written.append(True)
        task = asyncio.create_task(local_io(worker))
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        finish.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(written, [True])


if __name__ == "__main__":
    unittest.main()
