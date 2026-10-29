import logging
import re
from pathlib import Path
import tempfile
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pyrogram import Client, enums, raw
from pyrogram.errors import PeerIdInvalid
from pyrogram.parser import Parser
from pyrogram.types import Chat, Message

from Cogs.core import console_tools
from Cogs.core import luna_tools
from Cogs.core import runtime as selfbot


class PortableToolsTests(unittest.TestCase):
    def test_calculator_rejects_code_and_excessive_arithmetic(self):
        self.assertEqual(luna_tools.calculate("(2 + 3) * 4 ** 2"), "80")
        for expression in ("__import__('os').system('echo nope')", "2**100000000", "1/0", "[1]*10000", "(-1)**0.5"):
            with self.assertRaises(ValueError, msg=expression):
                luna_tools.calculate(expression)

    def test_base64_utf8_roundtrip_and_invalid_data(self):
        value = "Ciao 🖤"
        self.assertEqual(luna_tools.transform("decode_base64", luna_tools.transform("encode_base64", value)), value)
        for value in ("!", "/w=="):
            with self.assertRaises(ValueError):
                luna_tools.transform("decode_base64", value)

    def test_note_crud_persists_without_filename_interpolation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.json"
            notes = luna_tools.Notes(path)
            notes.execute("note", "../name contenuto")
            self.assertEqual(luna_tools.Notes(path).execute("shownote", "../name"), "contenuto")
            with self.assertRaises(ValueError): notes.execute("note", "../name duplicato")
            notes.execute("editnote", "../name aggiornato")
            self.assertEqual(notes.execute("sendnote", "../name"), "aggiornato")
            notes.execute("delnote", "../name")
            self.assertEqual(notes.execute("notes", ""), "Note » nessuna")

    def test_password_bounds_and_character_groups(self):
        password = luna_tools.password("32")
        self.assertEqual(len(password), 32)
        self.assertTrue(any(c.isdigit() for c in password))
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.islower() for c in password))
        for size in ("7", "129"):
            with self.assertRaises(ValueError): luna_tools.password(size)

    def test_all_commands_and_aliases_have_help(self):
        for category, entries in luna_tools.CATEGORIES.items():
            first = selfbot.help_text("!", category)
            count = re.search(r"Pagina 1/(\d+)", first)
            total = int(count[1]) if count else 1
            pages = "\n".join(selfbot.help_text("!", category, page=page) for page in range(1, total + 1))
            for command, _, _ in entries:
                self.assertIn(command, selfbot.COMMANDS)
                self.assertIn("!" + command, pages)
                self.assertNotIn("Voce sconosciuta", selfbot.help_text("!", command))
        for alias in luna_tools.ALIASES:
            self.assertNotIn("Voce sconosciuta", selfbot.help_text("!", alias))

    def test_gif_validation_blocks_untrusted_url(self):
        response = Mock(headers={"Content-Type": "application/json"})
        response.json.return_value = {"results": [{"url": "https://evil.example/test.gif"}]}
        with patch.object(luna_tools.requests, "get", return_value=response):
            with self.assertRaises(ValueError): luna_tools.reaction_gif("hug")

    def test_fun_input_bounds(self):
        for cmd, arg in (("dice", "1"), ("dice", "1001"), ("choose", "solo"), ("8ball", "")):
            with self.assertRaises(ValueError): luna_tools.fun_result(cmd, arg, "te")


class ConsoleTests(unittest.TestCase):
    def test_format_redacts_secrets_and_control_characters(self):
        record = logging.LogRecord("melixsa", logging.ERROR, "", 0, "secret123\n\033[31m", (), None)
        record.category = "Error"
        with patch.object(console_tools, "_secrets", ["secret123"]):
            rendered = console_tools.ConsoleFormatter(False).format(record)
        self.assertNotIn("secret123", rendered)
        self.assertNotIn("\n", rendered)
        self.assertNotIn("\033", rendered)
        self.assertIn("[redacted]", rendered)

    def test_file_always_keeps_timestamp_and_console_preferences_apply_without_color(self):
        record = logging.LogRecord("melixsa", logging.INFO, "", 0, "online", (), None)
        record.category = "Selfbot"
        with patch.object(console_tools, "_settings", dict(timestamp=False, spacers=False, pgradient=False, lgradient=False)):
            self.assertTrue(console_tools.ConsoleFormatter(False).format(record).startswith("Selfbot"))
            self.assertRegex(console_tools.ConsoleFormatter(False, console=False).format(record), r"^\d{2}:\d{2}:\d{2} \|")


def message(text="!calc 2+2", chat_type=enums.ChatType.SUPERGROUP):
    return SimpleNamespace(id=10, text=text, chat=SimpleNamespace(id=-100123, type=chat_type),
                           from_user=SimpleNamespace(id=99), message_thread_id=7,
                           reply_to_message=None, delete=AsyncMock(), answer=AsyncMock())


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_body_games_unknown_reply_peer_send_without_clickable_mention(self):
        client = SimpleNamespace(resolve_peer=AsyncMock(side_effect=PeerIdInvalid))
        for command in ("dick", "boobs"):
            msg = message()
            msg.reply_to_message = SimpleNamespace(from_user=SimpleNamespace(id=123, first_name="Luca 😀"))

            async def serialize_entities(panel, **kwargs):
                for entity in kwargs["entities"]:
                    entity._client = client
                    await entity.write()
                return SimpleNamespace(id=20)

            msg.answer.side_effect = serialize_entities
            with self.subTest(command=command), patch.object(selfbot, "schedule_delete") as delete:
                await selfbot.handle_command(client, msg, command, "")
            self.assertEqual(msg.answer.await_count, 2)
            first, retry = msg.answer.call_args_list
            self.assertEqual(first.args[0], retry.args[0])
            self.assertIn(f"Luca 😀's {command}", retry.args[0])
            pre, = retry.kwargs["entities"]
            self.assertEqual(pre.type, enums.MessageEntityType.PRE)
            self.assertEqual(pre.offset, len("Luca 😀\n".encode("utf-16-le")) // 2)
            self.assertEqual(pre.offset + pre.length, len(retry.args[0].encode("utf-16-le")) // 2)
            delete.assert_called_once()

    async def test_response_unknown_chat_peer_still_raises(self):
        msg = message()
        msg.answer.side_effect = PeerIdInvalid
        with self.assertRaises(PeerIdInvalid):
            await selfbot.respond(msg, "test")
        self.assertEqual(msg.answer.await_count, 1)

    async def test_body_games_resolve_ids_and_keep_ascii_spacing(self):
        user = SimpleNamespace(id=123, first_name="Anna", last_name="Rossi", username="anna")
        client = SimpleNamespace(get_users=AsyncMock(return_value=user))
        for command, size, drawing in (("dick", 13, "8" + "=" * 13 + "D"),
                                       ("boobs", 5, "(     .     ) (     .     )")):
            msg = message()
            with self.subTest(command=command), patch.object(luna_tools.RNG, "randint", return_value=size), \
                 patch.object(selfbot, "schedule_delete") as delete:
                await selfbot.handle_command(client, msg, command, "123")
            panel = msg.answer.call_args.args[0]
            self.assertIn(f"@anna's {command}", panel)
            self.assertIn(drawing, panel)
            self.assertEqual(msg.answer.call_args.kwargs["entities"][0].type, enums.MessageEntityType.PRE)
            pre, mention = msg.answer.call_args.kwargs["entities"]
            self.assertEqual(mention.type, enums.MessageEntityType.TEXT_MENTION)
            self.assertEqual(mention.user.id, 123)
            self.assertEqual(pre.offset, len("@anna\n"))
            delete.assert_called_once()
        client.get_users.assert_awaited_with(123)

    async def test_body_games_accept_reply_and_require_a_target(self):
        client = SimpleNamespace(get_users=AsyncMock())
        for command, minimum, drawing in (("dick", 1, "8=D"), ("boobs", 0, "(.) (.)")):
            msg = message()
            msg.reply_to_message = SimpleNamespace(from_user=SimpleNamespace(id=123, first_name="Luca"))
            with self.subTest(command=command), patch.object(luna_tools.RNG, "randint", return_value=minimum), \
                 patch.object(selfbot, "respond", new_callable=AsyncMock) as respond:
                await selfbot.handle_command(client, msg, command, "")
                self.assertEqual(respond.call_args.args[1], f"Luca's {command}\n{drawing}")
            with self.assertRaises(ValueError):
                await selfbot.handle_command(client, message(), command, "")
        client.get_users.assert_not_awaited()

    async def test_ping_measures_server_round_trip_in_milliseconds(self):
        client = SimpleNamespace(invoke=AsyncMock())
        with patch.object(selfbot.time, "perf_counter", side_effect=[10.0, 10.12345]), \
             patch.object(selfbot, "respond", new_callable=AsyncMock) as respond:
            await selfbot.handle_command(client, message(), "ping", "")
        query = client.invoke.call_args.args[0]
        self.assertIsInstance(query, raw.functions.Ping)
        self.assertEqual(client.invoke.call_args.kwargs, dict(retries=1, timeout=5, sleep_threshold=0))
        self.assertIn("123.45 ms", respond.call_args.args[1])

    async def test_ping_does_not_report_latency_when_server_fails(self):
        client = SimpleNamespace(invoke=AsyncMock(side_effect=TimeoutError("Timeout")))
        with patch.object(selfbot, "respond", new_callable=AsyncMock) as respond:
            with self.assertRaises(TimeoutError):
                await selfbot.handle_command(client, message(), "ping", "")
        respond.assert_not_awaited()

    async def test_new_command_dispatch_is_owner_only_and_logs_execution(self):
        msg = message(chat_type=enums.ChatType.PRIVATE)
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix="!")), \
             patch.object(selfbot, "handle_command", new_callable=AsyncMock) as handler, \
             patch.object(console_tools, "event") as log:
            await selfbot.process_message(None, msg, 100)
            handler.assert_not_awaited()
            await selfbot.process_message(None, msg, 99)
            msg.delete.assert_awaited_once()
            handler.assert_awaited_once_with(None, msg, "calc", "2+2")
            self.assertEqual([call.args[0] for call in log.call_args_list], ["Command", "Command"])

    async def test_spoiler_uses_telegram_utf16_entity_and_timer(self):
        msg = message()
        with patch.object(selfbot, "schedule_delete") as timer:
            await selfbot.handle_command(None, msg, "spoiler", "🖤Ciao")
            timer.assert_called_once_with(msg.answer.return_value)
        entity, = msg.answer.call_args.kwargs["entities"]
        self.assertEqual(entity.length, 6)
        self.assertEqual(entity.type, enums.MessageEntityType.SPOILER)

    async def test_poll_preserves_topic_and_validates_before_sending(self):
        msg = message()
        client = SimpleNamespace(send_poll=AsyncMock())
        with patch.object(selfbot, "schedule_delete") as timer:
            await selfbot.handle_command(client, msg, "cpoll", "Domanda | Uno | Due")
            timer.assert_called_once()
        self.assertEqual(client.send_poll.call_args.kwargs["message_thread_id"], 7)
        self.assertFalse(client.send_poll.call_args.kwargs["is_anonymous"])
        client.send_poll.reset_mock()
        with self.assertRaises(ValueError): await selfbot.handle_command(client, msg, "poll", "Domanda | Uno")
        client.send_poll.assert_not_awaited()

    async def test_moderation_private_chat_rejected_without_api_call(self):
        client = SimpleNamespace(ban_chat_member=AsyncMock())
        with self.assertRaises(ValueError):
            await selfbot.handle_command(client, message(chat_type=enums.ChatType.PRIVATE), "ban", "99")
        client.ban_chat_member.assert_not_awaited()

    async def test_kick_bans_then_unbans_only_target(self):
        msg = message()
        client = SimpleNamespace(get_users=AsyncMock(return_value=SimpleNamespace(id=123)),
                                 ban_chat_member=AsyncMock(), unban_chat_member=AsyncMock())
        with patch.object(selfbot, "respond", new_callable=AsyncMock):
            await selfbot.handle_command(client, msg, "kick", "123")
        client.ban_chat_member.assert_awaited_once_with(-100123, 123)
        client.unban_chat_member.assert_awaited_once_with(-100123, 123)

    async def test_gif_sent_as_animation_in_topic_with_timer(self):
        msg = message()
        client = SimpleNamespace(send_animation=AsyncMock(), get_users=AsyncMock(
            return_value=SimpleNamespace(id=123, username="amico")))
        with patch.object(luna_tools, "reaction_gif", return_value=("https://nekos.best/api/v2/hug/test.gif", "Anime")), \
             patch.object(selfbot, "schedule_delete") as timer:
            await selfbot.handle_command(client, msg, "hug", "@amico")
            timer.assert_called_once()
        self.assertEqual(client.send_animation.call_args.kwargs["message_thread_id"], 7)
        self.assertIn("@amico", client.send_animation.call_args.kwargs["caption"])
        mention, = client.send_animation.call_args.kwargs["caption_entities"]
        self.assertEqual(mention.type, enums.MessageEntityType.TEXT_MENTION)
        self.assertEqual(mention.user.id, 123)

    async def test_fun_without_username_uses_clickable_name_and_preserves_codeblock(self):
        msg = message()
        msg.reply_to_message = SimpleNamespace(from_user=SimpleNamespace(id=123, first_name="Luca 😀", last_name="Rossi"))
        with patch.object(selfbot, "schedule_delete"):
            await selfbot.handle_command(None, msg, "iq", "")
        pre, mention = msg.answer.call_args.kwargs["entities"]
        label = "Luca 😀 Rossi"
        self.assertEqual(mention.user.id, 123)
        self.assertEqual(mention.length, len(label.encode("utf-16-le")) // 2)
        self.assertEqual(pre.offset, mention.length + 1)
        self.assertEqual(pre.offset + pre.length, len(msg.answer.call_args.args[0].encode("utf-16-le")) // 2)

    async def test_animation_timer_starts_after_final_frame_and_recovers_on_failure(self):
        msg = message()
        msg.answer.return_value = SimpleNamespace(edit_text=AsyncMock(side_effect=RuntimeError("offline")))
        with patch.object(selfbot.asyncio, "sleep", new_callable=AsyncMock), \
             patch.object(selfbot, "schedule_delete") as timer:
            with self.assertRaises(RuntimeError): await selfbot.handle_command(None, msg, "cathi", "Ciao")
            timer.assert_called_once_with(msg.answer.return_value)
        self.assertNotIn(msg.chat.id, selfbot.animation_chats)

    async def test_every_animation_edit_sends_a_complete_codeblock_through_kurigram(self):
        # Usa il vero percorso di modifica della libreria, simulando solo Telegram.
        # Un mock di edit_text non rileverebbe la perdita delle entità PRE.
        client = SimpleNamespace(
            parser=Parser(None), link_preview_options=None,
            resolve_peer=AsyncMock(return_value=raw.types.InputPeerSelf()),
            invoke=AsyncMock(return_value=SimpleNamespace(updates=[])),
        )
        client.edit_message_text = MethodType(Client.edit_message_text, client)
        argument = '<b>🖤 & ciao</b>'
        for command, frames in luna_tools.ANIMATIONS.items():
            with self.subTest(command=command):
                client.invoke.reset_mock()
                msg = message()
                sent = Message(client=client, id=20, chat=Chat(id=msg.chat.id, type=msg.chat.type))
                msg.answer.return_value = sent
                with patch.object(selfbot.asyncio, "sleep", new_callable=AsyncMock), \
                     patch.object(selfbot, "schedule_delete") as timer:
                    await selfbot.handle_command(client, msg, command, argument)
                    timer.assert_called_once_with(sent)
                initial, = msg.answer.call_args.kwargs["entities"]
                self.assertEqual(initial.type, enums.MessageEntityType.PRE)
                self.assertEqual(initial.language, "ini")
                self.assertEqual(client.invoke.await_count, len(frames) - 1)
                for call, frame in zip(client.invoke.call_args_list, frames[1:]):
                    request = call.args[0]
                    expected = f"[ MELIXSA / {command.upper()} ]\n{frame.format(text=argument)}"
                    self.assertEqual(request.message, expected)
                    entity, = request.entities
                    self.assertIsInstance(entity, raw.types.MessageEntityPre)
                    self.assertEqual(entity.language, "ini")
                    self.assertEqual(entity.offset, 0)
                    self.assertEqual(entity.length, len(expected.encode("utf-16-le")) // 2)
                    self.assertEqual(request.id, sent.id)

    async def test_unmute_uses_group_default_permissions(self):
        permissions = SimpleNamespace(can_send_messages=True, can_send_photos=False)
        client = SimpleNamespace(get_users=AsyncMock(return_value=SimpleNamespace(id=123)),
                                 get_chat=AsyncMock(return_value=SimpleNamespace(permissions=permissions)),
                                 restrict_chat_member=AsyncMock())
        with patch.object(selfbot, "respond", new_callable=AsyncMock):
            await selfbot.handle_command(client, message(), "unmute", "123")
        client.restrict_chat_member.assert_awaited_once_with(-100123, 123, permissions)


if __name__ == "__main__":
    unittest.main()
