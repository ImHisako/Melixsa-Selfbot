import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pyrogram import enums, raw
from pyrogram.errors import FloodWait

from Cogs.core import runtime
from Cogs import abuse


def message(chat_id=-100):
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id, title="Amici", type=enums.ChatType.SUPERGROUP), message_thread_id=7)


def spam_client(**kwargs):
    return SimpleNamespace(invoke=AsyncMock(**kwargs), resolve_peer=AsyncMock(return_value=raw.types.InputPeerChat(chat_id=100)))


class SpamParserTests(unittest.TestCase):
    def test_text_spaces_numbers_and_fractional_interval(self):
        self.assertEqual(abuse.parse_spam("ciao  a tutti 2026 5 0"), ("ciao  a tutti 2026", 5, 0.0))
        self.assertEqual(abuse.parse_spam("ciao\na tutti 2 0.5"), ("ciao\na tutti", 2, 0.5))

    def test_invalid_bounds_and_nonfinite_values(self):
        for value in ("", "5 0", "ciao 0 0", "ciao 101 0", "ciao 1.5 0", "ciao 5 -1",
                      "ciao 5 nan", "ciao 5 inf", "ciao 5 3601", "ciao x 1", "ciao 1 x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                abuse.parse_spam(value)
        abuse.parse_spam("😀" * 2044 + " 1 0")
        with self.assertRaises(ValueError):
            abuse.parse_spam("😀" * 2045 + " 1 0")


class SpamCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await abuse.close_spam()
        abuse._sent_texts.clear()

    async def test_spam_update_before_rpc_response_never_triggers_autoreact(self):
        state = runtime.MonitorState(autoreact=True, prefix=">")
        async def send(query, **kwargs):
            update = message()
            update.from_user = SimpleNamespace(id=99)
            update.text = query.message
            await runtime.process_message(None, update, 99)
            return object()
        client = spam_client(side_effect=send)
        with patch.object(runtime, "state", state), \
             patch.object(runtime.auto_reactor, "react", new_callable=AsyncMock) as react:
            await runtime.handle_command(client, message(), "spam", "ciao a tutti 2 0")
            await abuse.jobs[-100]
            react.assert_not_awaited()
            # Lo stesso gruppo continua a ricevere autoreact sui messaggi normali.
            normal = message()
            normal.from_user = SimpleNamespace(id=99)
            normal.text = "messaggio normale | abc12"
            await runtime.process_message(None, normal, 99)
            react.assert_awaited_once()

    async def test_spam_text_that_looks_like_a_command_is_not_executed(self):
        update = message()
        update.from_user = SimpleNamespace(id=99)
        update.text = ">settings | 342f3"
        abuse.remember_spam(update.chat.id, update.text)
        with patch.object(runtime, "handle_command", new_callable=AsyncMock) as handle:
            await runtime.process_message(None, update, 99)
        handle.assert_not_awaited()

    async def test_dispatch_exact_count_suffix_topic_and_no_extra_messages(self):
        client = spam_client(return_value=object())
        with patch.object(abuse.secrets, "choice", side_effect=list("342f3abcd123xyz890q5rst67w8")), \
             patch.object(runtime.console_tools, "event"), \
             patch.object(runtime, "schedule_delete") as delete:
            await runtime.handle_command(client, message(), "spam", "ciao a tutti 5 0")
            await abuse.jobs[-100]
        self.assertEqual(client.invoke.await_count, 5)
        texts = [call.args[0].message for call in client.invoke.call_args_list]
        self.assertEqual(texts[0], "ciao a tutti | 342f3")
        self.assertEqual(len(set(texts)), 5)
        client.resolve_peer.assert_awaited_once_with(-100)
        for call in client.invoke.call_args_list:
            self.assertIsInstance(call.args[0], raw.functions.messages.SendMessage)
            self.assertEqual(call.args[0].reply_to.reply_to_msg_id, 7)
            self.assertIsNone(call.args[0].entities)
            self.assertEqual(call.kwargs["sleep_threshold"], 0)
            self.assertEqual(call.kwargs["retries"], 1)
        delete.assert_not_called()
        self.assertFalse(abuse.jobs)
        self.assertIn(">spam", runtime.help_text(">", "abuse"))
        self.assertIn(">spamstop", runtime.help_text(">", "abuse"))

    async def test_interval_occurs_only_between_messages(self):
        client = spam_client(return_value=object())
        with patch.object(abuse.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            await runtime.handle_command(client, message(), "spam", "ciao 3 0.5")
            await abuse.jobs[-100]
        self.assertEqual(sleep.await_count, 2)
        self.assertTrue(all(call.args == (0.5,) for call in sleep.call_args_list))

    async def test_stop_during_interval_and_other_chats_are_independent(self):
        first_sent = asyncio.Event()
        async def send(*args, **kwargs):
            first_sent.set()
            return object()
        client = spam_client(side_effect=send)
        await runtime.handle_command(client, message(), "spam", "ciao 5 60")
        await first_sent.wait()
        with self.assertRaises(ValueError):
            await runtime.handle_command(client, message(), "spam", "altro 2 0")
        with patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await runtime.handle_command(client, message(), "spamstop", "")
        self.assertEqual(client.invoke.await_count, 1)
        self.assertIn("fermato", respond.call_args.args[1])
        await runtime.handle_command(client, message(-200), "spam", "altra chat 1 0")
        await abuse.jobs[-200]
        self.assertFalse(abuse.jobs)

    async def test_flood_wait_stops_without_retrying(self):
        client = spam_client(side_effect=[object(), FloodWait(10)])
        with patch.object(runtime.console_tools, "event") as log:
            await runtime.handle_command(client, message(), "spam", "ciao 5 0")
            await abuse.jobs[-100]
        self.assertEqual(client.invoke.await_count, 2)
        self.assertIn("inviati=1/5", log.call_args.args[1])
        self.assertIn("10s", log.call_args.args[1])
        self.assertFalse(abuse.jobs)

    async def test_cancel_before_start_and_shutdown_cleanup(self):
        client = spam_client()
        await runtime.handle_command(client, message(), "spam", "ciao 5 0")
        self.assertTrue(await abuse.stop_spam(-100))
        self.assertFalse(await abuse.stop_spam(-100))
        await runtime.handle_command(client, message(), "spam", "ciao 5 0")
        await runtime.handle_command(client, message(-200), "spam", "ciao 5 0")
        await abuse.close_spam()
        self.assertFalse(abuse.jobs)

    async def test_validation_precedes_sending(self):
        client = spam_client()
        with self.assertRaises(ValueError):
            await runtime.handle_command(client, message(), "spam", "ciao 1 nan")
        with self.assertRaises(ValueError):
            await runtime.handle_command(client, message(), "spamstop", "extra")
        client.invoke.assert_not_awaited()
        self.assertFalse(abuse.jobs)
