import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pyrogram import enums

from Cogs.core import runtime


class LogWriterTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_preserves_records_names_order_and_single_echo(self):
        writer = runtime.LogWriter()
        record = dict(event="new", chat_id=-100, chat_name="Amici 💬", user_id=10,
                      name="Anna Rossi", text="ciao\n😀", media=None)
        with tempfile.TemporaryDirectory() as directory:
            group = Path(directory) / "group.txt"
            stalk = Path(directory) / "stalk.txt"
            await writer.submit(group, record)
            await writer.submit(stalk, record, echo=False)
            record["text"] = "modificato"
            record["event"] = "edited"
            await writer.submit(group, record)
            batch = [writer.queue.get_nowait() for _ in range(3)]
            with patch.object(runtime.console_tools, "event") as log:
                runtime.LogWriter._write_batch(batch)
            saved = [json.loads(line) for line in group.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([item["text"] for item in saved], ["ciao\n😀", "modificato"])
            self.assertEqual([item["event"] for item in saved], ["new", "edited"])
            self.assertEqual(json.loads(stalk.read_text(encoding="utf-8")), saved[0])
            self.assertEqual(log.call_count, 2)
            self.assertIn("chat=Amici 💬 | user=Anna Rossi", log.call_args_list[0].args[1])


class MonitorListTests(unittest.IsolatedAsyncioTestCase):
    async def test_combined_list_names_ids_and_unavailable_targets(self):
        state = runtime.MonitorState(stalk={10, 20}, surveillance={-100, -200})
        client = SimpleNamespace(
            get_users=AsyncMock(side_effect=[SimpleNamespace(first_name="Anna", last_name="Rossi", username="anna"), ValueError("unknown")]),
            get_chat=AsyncMock(side_effect=[ValueError("private"), SimpleNamespace(title="Amici", username="amici")]),
        )
        message = SimpleNamespace(chat=SimpleNamespace(id=99, type=enums.ChatType.PRIVATE))
        with patch.object(runtime, "state", state), patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await runtime.handle_command(client, message, "monitorlist", "")
        text = respond.call_args.args[1]
        for expected in ("Anna Rossi | @anna | ID » 10", "Utente non disponibile | ID » 20", "Amici | @amici | ID » -100", "Gruppo non disponibile | ID » -200"):
            self.assertIn(expected, text)
        self.assertEqual(state.stalk, {10, 20})
        self.assertEqual(state.surveillance, {-100, -200})

    async def test_empty_lists_and_separate_commands(self):
        client = SimpleNamespace(get_users=AsyncMock(), get_chat=AsyncMock())
        message = SimpleNamespace(chat=SimpleNamespace(id=99, type=enums.ChatType.PRIVATE))
        with patch.object(runtime, "state", runtime.MonitorState()), patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await runtime.handle_command(client, message, "stalklist", "")
            self.assertIn("Nessuna persona", respond.call_args.args[1])
            self.assertNotIn("Gruppi", respond.call_args.args[1])
            await runtime.handle_command(client, message, "sulist", "")
            self.assertIn("Nessun gruppo", respond.call_args.args[1])
            self.assertNotIn("Persone", respond.call_args.args[1])
            with self.assertRaises(ValueError):
                await runtime.handle_command(client, message, "monitorlist", "unexpected")
        client.get_users.assert_not_awaited()
        client.get_chat.assert_not_awaited()

    async def test_long_lists_are_split_into_telegram_sized_messages(self):
        client = SimpleNamespace(get_users=AsyncMock(return_value=SimpleNamespace(first_name="😀" * 64, last_name="", username=None)))
        message = SimpleNamespace(chat=SimpleNamespace(id=99, type=enums.ChatType.PRIVATE))
        with patch.object(runtime, "state", runtime.MonitorState(stalk=set(range(1, 61)))), patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await runtime.handle_command(client, message, "stalklist", "")
        self.assertGreater(respond.await_count, 1)
        for call in respond.call_args_list:
            self.assertLessEqual(len(call.args[1].encode("utf-16-le")) // 2, 3500)
        output = "\n".join(call.args[1] for call in respond.call_args_list)
        self.assertEqual(output.count("ID »"), 60)
