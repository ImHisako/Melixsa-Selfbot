import re
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums

from Cogs.core import ghost_tools, pagination, runtime
from Cogs.settings import permitted_command


def page_count(text):
    count = re.search(r"Pagina 1/(\d+)", text)
    return int(count[1]) if count else 1


class MenuPaginationTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(runtime, "state", runtime.MonitorState(prefix=">"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_all_categories_preserve_every_command_once_and_in_order(self):
        for category, entries in runtime.HELP_CATEGORIES.items():
            first = runtime.help_text(">", category)
            total = page_count(first)
            outputs = [runtime.help_text(">", category, page=number) for number in range(1, total + 1)]
            with self.subTest(category=category):
                rows = [line.split()[0] for output in outputs for line in output.splitlines() if line.startswith(">")]
                self.assertEqual(rows, [f">{name}" for name, _, _ in entries])
                for output in outputs:
                    self.assertLessEqual(sum(line.startswith(">") for line in output.splitlines()), pagination.MAX_ROWS)
                    self.assertLessEqual(len(output.encode("utf-16-le")) // 2, 4096)

    def test_navigation_and_aliases_use_current_prefix(self):
        first = runtime.help_text(">", "text")
        total = page_count(first)
        self.assertGreater(total, 1)
        self.assertIn("Successiva: >text 2", first)
        self.assertNotIn("Precedente:", first)
        second = runtime.help_text(">", ">text 2")
        self.assertEqual(second, runtime.help_text(">", "text", page=2))
        self.assertIn("Precedente: >text 1", second)
        last = runtime.help_text(">", "text", page=total)
        self.assertNotIn("Successiva:", last)
        self.assertEqual(runtime.help_text(">", "sc 2"), runtime.help_text(">", "soundcloud 2"))
        self.assertEqual(runtime.help_text(">", "h 1"), runtime.help_text(">", "help 1"))
        self.assertNotIn("Pagina", runtime.help_text(">", "animated"))

    def test_invalid_page_reports_range_without_sending_the_whole_menu(self):
        for topic in ("text 0", "text -1", "text " + "9" * 100):
            self.assertIn("Pagina non valida", runtime.help_text(">", topic))
        text = runtime.help_text(">", "text 999")
        self.assertIn("Pagina non disponibile", text)
        self.assertIn("Prima pagina: >text 1", text)
        self.assertNotIn(">reverse", text)

    def test_permissions_filter_before_pagination_and_block_reserved_topics(self):
        runtime.state.shared_commands = {"help", "json", "regional", "scpause", "email"}
        token = runtime.shared_command_context.set(True)
        try:
            first = runtime.help_text(">", "text")
            self.assertIn(">json", first)
            self.assertIn(">regional", first)
            self.assertNotIn(">reverse", first)
            self.assertNotIn("Pagina", first)
            for command, argument in (("help", "text 2"), ("h", "sc 2"),
                                      ("osint", "2"), ("sc", "2"), ("help", "1")):
                self.assertTrue(permitted_command(command, argument), (command, argument))
            for argument in ("settings 2", "abuse 2", "backup 2", "clearconsole 2"):
                self.assertFalse(permitted_command("help", argument))
                self.assertIn("non disponibile", runtime.help_text(">", argument))
            self.assertFalse(permitted_command("help", "text -1"))
        finally:
            runtime.shared_command_context.reset(token)

    def test_unicode_and_long_details_respect_telegram_limit_without_truncation(self):
        detail = "🖤" * 3500
        with patch.dict(runtime.HELP_DETAILS, {"bold": detail}):
            total = page_count(runtime.help_text(">", "bold"))
            pages = [runtime.help_text(">", "bold", page=page) for page in range(1, total + 1)]
        self.assertEqual(sum(page.count("🖤") for page in pages), 3500)
        for page in pages:
            self.assertLessEqual(len(page.encode("utf-16-le")) // 2, 4096)
            page.encode("utf-8")
        self.assertIn("Successiva: >help bold 2", pages[0])
        self.assertEqual(pagination.paginate_lines(["a🖤bc🖤"], max_units=3), [["a🖤"], ["bc"], ["🖤"]])

    def test_search_and_complete_list_have_the_same_page_size_and_navigation(self):
        entries = {"tools": tuple((f"cmd{i:02}", "", "descrizione") for i in range(30))}
        first = ghost_tools.command_page(entries, {}, ">")
        self.assertIn("Pagina 1/3", first)
        self.assertIn("Successiva: >allcmds 2", first)
        second = ghost_tools.command_page(entries, {}, ">", query="cmd", page=2)
        self.assertIn("Precedente: >search cmd 1", second)
        self.assertIn("Successiva: >search cmd 3", second)


class MenuDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_category_arguments_open_pages_and_not_external_operations(self):
        with patch.object(runtime, "send_help", new_callable=AsyncMock) as send, \
             patch.object(runtime, "handle_osint_command", new_callable=AsyncMock) as osint, \
             patch.object(runtime, "handle_soundcloud_command", new_callable=AsyncMock) as soundcloud:
            for command in ("text", "settings", "osint", "sc", "soundcloud", "mass"):
                await runtime.handle_command(None, None, command, "2")
                send.assert_awaited_with(None, None, f"{command} 2")
            osint.assert_not_awaited()
            soundcloud.assert_not_awaited()

    async def test_help_aliases_deliver_one_page_in_same_topic_with_native_entities(self):
        message = SimpleNamespace(chat=SimpleNamespace(id=-100123, type=enums.ChatType.SUPERGROUP), message_thread_id=7)
        sent = SimpleNamespace(id=10)
        client = SimpleNamespace(send_message=AsyncMock(return_value=sent))
        with patch.object(runtime, "state", runtime.MonitorState(prefix=">")), \
             patch.object(runtime, "schedule_delete") as delete:
            for alias in ("help", "h", "?"):
                await runtime.handle_command(client, message, alias, "text 2")
        self.assertEqual(client.send_message.await_count, 3)
        for call in client.send_message.call_args_list:
            self.assertIn("Pagina 2/", call.args[1])
            self.assertEqual(call.kwargs["message_thread_id"], 7)
            self.assertEqual(call.kwargs["parse_mode"], enums.ParseMode.DISABLED)
            header, body = call.kwargs["entities"]
            self.assertEqual(header.language, "lua")
            self.assertEqual(body.length + body.offset, len(call.args[1].encode("utf-16-le")) // 2)
        self.assertEqual(delete.call_count, 3)


if __name__ == "__main__":
    unittest.main()
