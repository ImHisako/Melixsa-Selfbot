"""Verifica i tentativi con Client.invoke e Session.invoke reali, senza rete."""
import asyncio
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import Client, enums, raw
from pyrogram.session import Session

from Cogs.core import runtime
from Cogs import abuse


def client_with_real_invoke():
    started = asyncio.Event()
    started.set()
    session = SimpleNamespace(is_started=started, WAIT_TIMEOUT=5,
                              send=AsyncMock(return_value=raw.types.Pong(msg_id=1, ping_id=2)))
    session.invoke = MethodType(Session.invoke, session)
    client = SimpleNamespace(is_connected=True, session=session, no_updates=False,
                             takeout_id=None, sleep_threshold=10, fetch_peers=AsyncMock(),
                             resolve_peer=AsyncMock(return_value=raw.types.InputPeerChat(chat_id=100)))
    client.invoke = MethodType(Client.invoke, client)
    return client


class InvocationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await abuse.close_spam()
        abuse._sent_texts.clear()

    @staticmethod
    def message():
        return SimpleNamespace(chat=SimpleNamespace(id=-100, title="Test", type=enums.ChatType.SUPERGROUP),
                               message_thread_id=None)

    async def test_ping_reaches_session_send_exactly_once(self):
        client = client_with_real_invoke()
        with patch.object(runtime, "respond", new_callable=AsyncMock) as respond:
            await runtime.handle_command(client, self.message(), "ping", "")
        client.session.send.assert_awaited_once()
        self.assertIsInstance(client.session.send.call_args.args[0], raw.functions.Ping)
        self.assertIn("ms", respond.call_args.args[1])

    async def test_spam_reaches_session_send_for_each_message(self):
        client = client_with_real_invoke()
        with patch.object(runtime.console_tools, "event") as log:
            await runtime.handle_command(client, self.message(), "spam", "ciao a tutti 8 0")
            await abuse.jobs[-100]
        self.assertEqual(client.session.send.await_count, 8)
        self.assertTrue(all(isinstance(call.args[0], raw.functions.messages.SendMessage)
                            for call in client.session.send.call_args_list))
        self.assertIn("inviati=8/8", log.call_args.args[1])
