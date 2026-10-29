import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums
from pyrogram.errors import FloodWait, RPCError

from Cogs.core import afk_tools, runtime


def message(user_id=42, chat_type=enums.ChatType.PRIVATE):
    return SimpleNamespace(chat=SimpleNamespace(id=user_id, type=chat_type, first_name="Amico"),
                           from_user=SimpleNamespace(id=user_id, is_bot=False, is_self=False),
                           outgoing=False, service=None, empty=False, text="Ciao")


class AFKTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 0.0
        self.afk = afk_tools.AFKController(lambda: self.now)
        self.client = SimpleNamespace(send_animation=AsyncMock(), send_message=AsyncMock())

    async def test_private_reply_once_per_user_every_six_hours_and_concurrent_duplicates(self):
        self.afk.enable("Torno più tardi.")
        await asyncio.gather(*(self.afk.reply(self.client, message(), "Amico") for _ in range(3)))
        self.client.send_animation.assert_awaited_once()
        self.now = afk_tools.REPLY_INTERVAL - 1
        await self.afk.reply(self.client, message(), "Amico")
        self.assertEqual(self.client.send_animation.await_count, 1)
        self.now += 1
        await self.afk.reply(self.client, message(), "Amico")
        self.assertEqual(self.client.send_animation.await_count, 2)
        await self.afk.reply(self.client, message(43), "Altro amico")
        self.assertEqual(self.client.send_animation.await_count, 3)

    async def test_disabled_groups_bots_service_and_outgoing_do_not_reply(self):
        await self.afk.reply(self.client, message(), "Amico")
        self.afk.enable()
        await self.afk.reply(self.client, message(chat_type=enums.ChatType.SUPERGROUP), "Gruppo")
        for field in ("is_bot", "is_self"):
            msg = message()
            setattr(msg.from_user, field, True)
            await self.afk.reply(self.client, msg, "Amico")
        for field in ("outgoing", "service", "empty"):
            msg = message()
            setattr(msg, field, True)
            await self.afk.reply(self.client, msg, "Amico")
        self.client.send_animation.assert_not_awaited()

    async def test_duration_reset_and_disable(self):
        self.afk.enable("Prima")
        self.now = 3661
        self.assertEqual(self.afk.duration(), "1h 1m 1s")
        self.assertEqual(self.afk.disable(), "1h 1m 1s")
        await self.afk.reply(self.client, message(), "Amico")
        self.client.send_animation.assert_not_awaited()
        self.afk.enable("Seconda")
        self.assertEqual(self.afk.duration(), "0h 0m 0s")
        self.assertEqual(self.afk.message, "Seconda")

    async def test_long_unicode_message_sends_gif_then_complete_codeblock(self):
        self.afk.enable("🖤" * 600)
        await self.afk.reply(self.client, message(), "Amico")
        self.assertEqual(self.client.send_animation.call_args.kwargs["caption"], "")
        panel = self.client.send_message.call_args.args[1]
        entity, = self.client.send_message.call_args.kwargs["entities"]
        self.assertIn("🖤" * 600, panel)
        self.assertEqual(entity.length, len(panel.encode("utf-16-le")) // 2)
        self.assertEqual(entity.language, "ini")
        with self.assertRaises(ValueError): self.afk.enable("🖤" * 1501)

    async def test_gif_rpc_error_falls_back_to_text(self):
        self.afk.enable("Torno presto")
        self.client.send_animation.side_effect = RPCError("GIF unavailable")
        await self.afk.reply(self.client, message(), "Amico")
        self.client.send_message.assert_awaited_once()

    async def test_flood_wait_applies_globally_and_survives_reactivation(self):
        self.afk.enable()
        self.client.send_animation.side_effect = FloodWait(30)
        await self.afk.reply(self.client, message(), "Amico")
        self.afk.disable()
        self.afk.enable()
        await self.afk.reply(self.client, message(43), "Altro")
        self.assertEqual(self.client.send_animation.await_count, 1)
        self.client.send_message.assert_not_awaited()
        self.now = 30
        self.client.send_animation.side_effect = None
        await self.afk.reply(self.client, message(43), "Altro")
        self.assertEqual(self.client.send_animation.await_count, 2)

    async def test_send_error_retries_only_after_sixty_seconds(self):
        self.afk.enable()
        self.client.send_animation.side_effect = OSError("offline")
        await self.afk.reply(self.client, message(), "Amico")
        self.now = 59
        await self.afk.reply(self.client, message(), "Amico")
        self.assertEqual(self.client.send_animation.await_count, 1)
        self.now = 60
        self.client.send_animation.side_effect = None
        await self.afk.reply(self.client, message(), "Amico")
        self.assertEqual(self.client.send_animation.await_count, 2)

    async def test_commands_routing_and_saved_messages_do_not_auto_reply(self):
        own = message(99)
        own.text, own.delete = ">afk Al cinema", AsyncMock()
        with patch.object(runtime, "state", runtime.MonitorState(prefix=">")), patch.object(runtime, "afk", self.afk), \
             patch.object(runtime, "respond", new_callable=AsyncMock):
            await runtime.process_message(self.client, own, 99)
            self.assertTrue(self.afk.active)
            self.assertEqual(self.afk.message, "Al cinema")
            await runtime.process_message(self.client, message(99), 99)
            self.client.send_animation.assert_not_awaited()
            await runtime.process_message(self.client, message(), 99)
            self.client.send_animation.assert_awaited_once()
            await runtime.handle_command(self.client, own, "unafk", "")
            self.assertFalse(self.afk.active)
        self.assertIn(">afk", runtime.help_text(">", "misc"))
        self.assertNotIn("Voce sconosciuta", runtime.help_text(">", "unafk"))


if __name__ == "__main__":
    unittest.main()
