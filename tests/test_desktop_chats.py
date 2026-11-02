import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pyrogram import enums
from pyrogram.errors import ChatWriteForbidden

from MelixsaUI.backend.chats import ChatService, STYLES, chat_id, transform_text


def message(identifier, text=None, **extra):
    return SimpleNamespace(
        id=identifier, text=text if text is not None else f"Messaggio {identifier}",
        date=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
        from_user=SimpleNamespace(id=7, first_name="Anna", last_name="Rossi"), **extra,
    )


class TextStylesTests(unittest.TestCase):
    def test_sample_styles_and_non_ascii_are_preserved(self):
        samples = {"plain": "Abc è 😀", "fraktur": "𝔄𝔟𝔠 è 😀", "squared": "🅰🅱🅲 è 😀",
                   "circled": "Ⓐⓑⓒ è 😀", "boldItalic": "𝘼𝙗𝙘 è 😀", "fullWidth": "Ａｂｃ è 😀"}
        for style, expected in samples.items():
            with self.subTest(style=style):
                self.assertEqual(transform_text("Abc è 😀", style), expected)
        self.assertEqual(transform_text("Hi!", "strikethrough"), "H\u0336i\u0336!")
        self.assertEqual(transform_text("Ab", "invisibleSeparator"), "A\u2060b\u2060")
        self.assertEqual(transform_text("a", "zalgo"), "a\u0334\u033a\u030f\u0309\u0308\u0301")

    def test_styles_match_the_attached_example_for_every_latin_letter(self):
        from string import ascii_lowercase, ascii_uppercase
        mapping = dict(zip("qwertyuioplkjhgfdsazxcvbnm", "qwеrтуціорlкјнgfdѕаᴢхсvЬпм"))
        for char in ascii_lowercase + ascii_uppercase:
            expected = mapping[char] if char.islower() else mapping[char.lower()].upper()
            self.assertEqual(transform_text(char, "undetected"), expected + "\u2060")
        for style in STYLES:
            if "lower" in style:
                self.assertEqual(len(style["lower"]), 26, style["id"])
                self.assertEqual(len(style["upper"]), 26, style["id"])
        for invalid in ("unknown", [], None):
            with self.assertRaises(ValueError):
                transform_text("a", invalid)

    def test_chat_ids_reject_booleans_floats_and_non_numeric_targets(self):
        self.assertEqual(chat_id("-1001234567890"), -1001234567890)
        self.assertEqual(chat_id("123"), 123)
        for value in (True, 0, 1.5, "@someone", "../data", [], 2**63):
            with self.subTest(value=value), self.assertRaises(ValueError):
                chat_id(value)


class DesktopChatsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = SimpleNamespace(send_message=AsyncMock(return_value=message(100, outgoing=True)))
        self.bridge = SimpleNamespace(connection="connected", client=self.client)
        self.service = ChatService(self.bridge)
        self.addAsyncCleanup(self.service.close)

    async def test_every_operation_requires_connection(self):
        self.bridge.connection = "offline"
        for operation, params in ((self.service.list_dialogs, {}), (self.service.history, {"chat_id": "7"}),
                                  (self.service.send, {"chat_id": "7", "text": "hello"}),
                                  (self.service.profile_photos, {"ids": ["7"]}),
                                  (self.service.profile_photo, {"chat_id": "7"})):
            with self.assertRaisesRegex(ValueError, "Collega Telegram"):
                await operation(params)
        self.client.send_message.assert_not_awaited()

    async def test_dialog_pagination_includes_all_kinds_and_archive_without_duplicates(self):
        def dialog(identifier, kind=enums.ChatType.PRIVATE):
            return SimpleNamespace(chat=SimpleNamespace(id=identifier, first_name=f"Chat {identifier}", type=kind),
                                   top_message=message(1), unread_messages_count=4)
        async def dialogs(from_archive):
            for identifier in (range(1, 126) if not from_archive else [125, -1001, -1002]):
                yield dialog(identifier, enums.ChatType.SUPERGROUP if identifier == -1001 else
                             enums.ChatType.CHANNEL if identifier == -1002 else enums.ChatType.PRIVATE)
        self.client.get_dialogs = Mock(side_effect=dialogs)
        first = await self.service.list_dialogs({})
        self.assertEqual(len(first["chats"]), 60)
        self.assertTrue(first["has_more"])
        second = await self.service.list_dialogs({"offset": first["next_offset"]})
        third = await self.service.list_dialogs({"offset": second["next_offset"]})
        rows = first["chats"] + second["chats"] + third["chats"]
        self.assertEqual(len(rows), 127)
        self.assertEqual(len({row["id"] for row in rows}), 127)
        self.assertFalse(third["has_more"])
        self.assertEqual([row["kind"] for row in rows[-2:]], ["supergroup", "channel"])
        self.assertTrue(rows[-1]["archived"])
        self.assertFalse(rows[0]["archived"])
        self.assertEqual(rows[0]["unread"], 4)
        self.client.get_dialogs.assert_any_call(from_archive=False)
        self.client.get_dialogs.assert_any_call(from_archive=True)
        repeated = await self.service.list_dialogs({"offset": first["next_offset"]})
        self.assertEqual(repeated, second)

    async def test_refresh_restarts_iteration_and_disconnect_clears_content(self):
        async def dialogs(from_archive):
            if not from_archive:
                yield SimpleNamespace(chat=SimpleNamespace(id=7, type=enums.ChatType.BOT, first_name="Bot"))
        self.client.get_dialogs = Mock(side_effect=dialogs)
        self.assertEqual(len((await self.service.list_dialogs({}))["chats"]), 1)
        await self.service.list_dialogs({})
        self.assertEqual(self.client.get_dialogs.call_count, 4)
        await self.service.close()
        self.assertEqual(self.service.dialogs, [])
        self.assertIsNone(self.service.iterator)

    async def test_history_returns_chronological_pages_and_uses_exclusive_cursor(self):
        async def history(target, limit, max_id):
            self.assertEqual(target, -100)
            for identifier in range(max_id or 120, max(0, (max_id or 120) - limit), -1):
                yield message(identifier)
        self.client.get_chat_history = Mock(side_effect=history)
        first = await self.service.history({"chat_id": "-100"})
        self.assertEqual([row["id"] for row in first["messages"]], list(range(71, 121)))
        self.assertTrue(first["has_more"])
        self.assertEqual(first["next_before"], 71)
        second = await self.service.history({"chat_id": "-100", "before": first["next_before"]})
        self.assertEqual([row["id"] for row in second["messages"]], list(range(21, 71)))
        self.client.get_chat_history.assert_called_with(-100, limit=51, max_id=70)
        earliest = await self.service.history({"chat_id": "-100", "before": 1})
        self.assertEqual(earliest["messages"], [])
        self.assertFalse(earliest["has_more"])

    async def test_dialog_loading_continues_past_two_hundred_chats(self):
        async def dialogs(from_archive):
            if not from_archive:
                for identifier in range(1, 226):
                    yield SimpleNamespace(chat=SimpleNamespace(id=identifier, type=enums.ChatType.PRIVATE))
        self.client.get_dialogs = dialogs
        offset = 0
        ids = []
        while True:
            result = await self.service.list_dialogs({"offset": offset})
            ids.extend(row["id"] for row in result["chats"])
            if not result["has_more"]:
                break
            offset = result["next_offset"]
        self.assertEqual(ids, [str(identifier) for identifier in range(1, 226)])

    async def test_captions_edits_sender_chats_and_service_messages_are_serialized(self):
        async def history(*args, **kwargs):
            yield message(3, text="", service=True)
            yield SimpleNamespace(id=2, caption="caption", media=enums.MessageMediaType.PHOTO,
                                  sender_chat=SimpleNamespace(id=-100, title="Canale"), edit_date=datetime.now(timezone.utc))
            yield message(1, text="<script>alert('x')</script>")
        self.client.get_chat_history = Mock(side_effect=history)
        rows = (await self.service.history({"chat_id": "7"}))["messages"]
        self.assertEqual(rows[0]["text"], "<script>alert('x')</script>")
        self.assertEqual(rows[1]["text"], "caption")
        self.assertEqual(rows[1]["media"], "photo")
        self.assertEqual(rows[1]["sender"], "Canale")
        self.assertIsNotNone(rows[1]["edited"])
        self.assertTrue(rows[2]["service"])
        json.dumps(rows)

    async def test_send_transforms_exactly_and_disables_markup_parsing(self):
        await self.service.send({"chat_id": "-100", "text": "Abc **ok** è 😀", "style": "fraktur"})
        self.client.send_message.assert_awaited_once_with(-100, "𝔄𝔟𝔠 **𝔬𝔨** è 😀", parse_mode=enums.ParseMode.DISABLED)

    async def test_send_validates_the_transformed_utf16_length_without_truncation(self):
        for value, style in (("a" * 2049, "fraktur"), ("a" * 586, "zalgo"), ("😀" * 2049, "plain"),
                             ("a" * 4097, "plain"), (" \n\t", "plain"), (None, "plain"), ("\ud800", "plain")):
            with self.subTest(style=style), self.assertRaises(ValueError):
                await self.service.send({"chat_id": "7", "text": value, "style": style})
        self.client.send_message.assert_not_awaited()
        await self.service.send({"chat_id": "7", "text": "a" * 2048, "style": "fraktur"})
        self.assertEqual(len(self.client.send_message.call_args.args[1].encode("utf-16-le")) // 2, 4096)

    async def test_failed_send_is_not_retried_and_does_not_log_message_content(self):
        self.client.send_message.side_effect = ChatWriteForbidden()
        with self.assertRaises(ChatWriteForbidden):
            await self.service.send({"chat_id": "7", "text": "private draft"})
        self.assertEqual(self.client.send_message.await_count, 1)

    async def test_invalid_offsets_and_ids_do_not_reach_telegram(self):
        for params in ({"chat_id": True}, {"chat_id": "7", "before": -1}, {"chat_id": "7", "before": True}):
            with self.assertRaises(ValueError):
                await self.service.history(params)
        for offset in (-1, True, "60", 2**32):
            with self.assertRaises(ValueError):
                await self.service.list_dialogs({"offset": offset})

    async def test_timeout_resets_dialog_pagination_and_has_an_actionable_error(self):
        async def dialogs(**kwargs):
            await asyncio.Event().wait()
            yield
        self.client.get_dialogs = dialogs
        wait_for = asyncio.wait_for
        with patch("MelixsaUI.backend.chats.asyncio.wait_for", new=lambda task, timeout: wait_for(task, 0.01)):
            with self.assertRaisesRegex(ValueError, "Caricamento delle chat scaduto"):
                await self.service.list_dialogs({})
        self.assertIsNone(self.service.iterator)
        self.assertEqual(self.service.dialogs, [])

    async def test_unconfirmed_sends_do_not_report_success(self):
        for response in (None, SimpleNamespace(empty=True)):
            self.client.send_message.return_value = response
            with self.assertRaisesRegex(ValueError, "Telegram non ha confermato"):
                await self.service.send({"chat_id": "7", "text": "hello"})

    async def test_bridge_routes_chat_methods_to_the_chat_service(self):
        from MelixsaUI.backend.bridge import DesktopBridge
        bridge = object.__new__(DesktopBridge)
        bridge.chats = SimpleNamespace(list_dialogs=AsyncMock(return_value={"chats": []}),
                                       history=AsyncMock(return_value={"messages": []}),
                                       send=AsyncMock(return_value={"message": {"id": 1}}),
                                       profile_photos=AsyncMock(return_value={"photos": {}}),
                                       profile_photo=AsyncMock(return_value={"photo": None}))
        for rpc, method in (("chat_dialogs", "list_dialogs"), ("chat_history", "history"), ("chat_send", "send"),
                            ("chat_photos", "profile_photos"), ("chat_photo", "profile_photo")):
            result = await bridge.dispatch(rpc, {"chat_id": "7"})
            getattr(bridge.chats, method).assert_awaited_once_with({"chat_id": "7"})
            self.assertEqual(result, getattr(bridge.chats, method).return_value)


if __name__ == "__main__":
    unittest.main()
