"""Verifica il protocollo reale su loopback, senza browser o account Telegram."""

import asyncio
import socket
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from websockets.asyncio.client import connect

from Cogs.core import soundcloud_tools as sc


def player_payload(**overrides):
    values = {name: 0 for name in sc.FIELDS}
    values.update(
        id=42, name="SoundCloud", title="Una canzone | live", artist="Artista",
        album="", cover="", state=0, position=30, duration=240, volume=50,
        rating=0, repeat=1, rating_system=1, available_repeat=7,
        created_at=10, updated_at=20, active_at=20,
    )
    values.update({capability: 1 for _, capability in sc.EVENTS.values()})
    values.update(overrides)
    return encode_fields(values)


def encode_fields(values):
    fields = []
    for name in sc.FIELDS:
        value = values.get(name)
        if value is None:
            fields.append("")
        elif isinstance(value, str):
            fields.append(value.replace("|", r"\|") if value else "\x01")
        else:
            fields.append(str(int(value)))
    return "|".join(fields) + "|"


class ParserTests(unittest.TestCase):
    def test_escaped_text_empty_strings_and_delta(self):
        parsed = sc.parse_player_data(player_payload())
        self.assertEqual(parsed["title"], "Una canzone | live")
        self.assertEqual(parsed["album"], "")
        self.assertEqual(sc.parse_player_data(encode_fields({"title": "", "volume": 0})), {"title": "", "volume": 0})
        with self.assertRaises(ValueError):
            sc.parse_player_data("42|SoundCloud|")

    def test_times(self):
        for text, seconds in (("90", 90), ("1:30", 90), ("1:02:03", 3723), ("0", 0)):
            self.assertEqual(sc.parse_position(text), seconds)
        for text in ("", "-1", "1:99", "1.5", "abc", "1:2", "0:00:00:00"):
            with self.assertRaises(sc.SoundCloudError):
                sc.parse_position(text)
        self.assertEqual(sc.format_time(3723), "1:02:03")


class SocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
        self.adapter = sc.SoundCloudAdapter(port, event_timeout=0.2)
        await self.adapter.start()
        self.assertEqual(self.adapter.error, "")
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        await self.adapter.close()

    async def until(self, predicate):
        async def check():
            while not predicate():
                await asyncio.sleep(0.005)
        await asyncio.wait_for(check(), 1)

    async def browser(self, **overrides):
        client = await connect(f"ws://127.0.0.1:{self.adapter.port}")
        self.clients.append(client)
        self.assertEqual(await client.recv(), "ADAPTER_VERSION 3.0.0;WNPLIB_REVISION 3")
        await client.send("4 1")
        count = len(self.adapter.players)
        remote_id = overrides.get("id", 42)
        await client.send(f"0 {remote_id} {player_payload(**overrides)}")
        await self.until(lambda: len(self.adapter.players) == count + 1)
        return client

    async def test_loopback_binding_and_setup(self):
        self.assertEqual(self.adapter.server.sockets[0].getsockname()[0], "127.0.0.1")
        setup = await self.adapter.execute("scconnect", "", "!")
        self.assertIn("!scnp", setup)
        self.assertIn(str(self.adapter.port), setup)
        with self.assertRaisesRegex(sc.SoundCloudError, "non collegato"):
            await self.adapter.execute("scnp", "")

    async def test_metadata_delta_binary_and_non_soundcloud_filter(self):
        client = await self.browser()
        await client.send(b"\x2a\x00\x00\x00PNG")
        await client.send("not a valid message")
        await client.send("1 42 broken|")
        await client.send("1 42 " + encode_fields({"position": 90, "album": ""}))
        await self.until(lambda: self.adapter.active_player().number("position") == 90)
        result = await self.adapter.execute("scnp", "")
        self.assertIn("Una canzone | live", result)
        self.assertIn("1:30 / 4:00", result)
        await self.browser(id=42, name="YouTube", active_at=9999)
        self.assertEqual(len(self.adapter.soundcloud_players()), 1)
        self.assertTrue(self.adapter.active_player().is_soundcloud)

    async def test_all_event_types_and_acknowledgements(self):
        client = await self.browser()
        for command, argument, expected_event, expected_value in (
            ("scplay", "", 0, 0), ("scpause", "", 0, 1), ("sctoggle", "", 0, 1),
            ("scprev", "", 1, 0), ("scnext", "", 2, 0), ("scseek", "1:30", 3, 90),
            ("scvolume", "0", 4, 0), ("sclike", "on", 5, 5),
            ("screpeat", "one", 6, 4), ("scshuffle", "on", 7, 1),
        ):
            with self.subTest(command=command):
                task = asyncio.create_task(self.adapter.execute(command, argument))
                remote_id, event_id, event, value = (await client.recv()).split(" ")
                self.assertEqual((int(remote_id), int(event), int(value)), (42, expected_event, expected_value))
                self.assertFalse(task.done())
                await client.send(f"3 {event_id} 1")
                self.assertTrue(await task)
                self.assertFalse(self.adapter.pending)

    async def test_invalid_or_unsupported_controls_do_not_send_events(self):
        client = await self.browser(can_skip_next=0, available_repeat=1)
        for command, argument in (
            ("scnext", ""), ("scvolume", "101"), ("scvolume", "-1"),
            ("scseek", "4:01"), ("scseek", "1:99"), ("screpeat", "one"),
            ("scshuffle", "yes"), ("sclike", "maybe"), ("scplay", "url"),
        ):
            with self.subTest(command=command, argument=argument):
                with self.assertRaises(sc.SoundCloudError):
                    await self.adapter.execute(command, argument)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(client.recv(), 0.03)
        self.assertFalse(self.adapter.pending)

    async def test_failed_ack_timeout_disconnect_and_no_false_success(self):
        client = await self.browser()
        task = asyncio.create_task(self.adapter.execute("scnext", ""))
        _, event_id, _, _ = (await client.recv()).split(" ")
        await client.send(f"3 {event_id} 2")
        with self.assertRaisesRegex(sc.SoundCloudError, "non ha eseguito"):
            await task
        task = asyncio.create_task(self.adapter.execute("scnext", ""))
        await client.recv()
        with self.assertRaisesRegex(sc.SoundCloudError, "Nessuna conferma"):
            await task
        task = asyncio.create_task(self.adapter.execute("scnext", ""))
        await client.recv()
        await client.close()
        with self.assertRaisesRegex(sc.SoundCloudError, "disconnesso"):
            await task
        self.assertFalse(self.adapter.pending)
        await self.until(lambda: not self.adapter.players)

    async def test_manual_selection_and_cross_browser_ids(self):
        first = await self.browser(title="Primo", active_at=10)
        second = await self.browser(title="Secondo", active_at=30)
        players = self.adapter.soundcloud_players()
        self.assertEqual(len(players), 2)
        self.assertEqual(self.adapter.active_player().values["title"], "Secondo")
        await self.adapter.execute("scselect", str(players[0].local_id))
        task = asyncio.create_task(self.adapter.execute("scnext", ""))
        _, event_id, _, _ = (await first.recv()).split(" ")
        await second.send(f"3 {event_id} 1")
        await asyncio.sleep(0.01)
        self.assertFalse(task.done())
        await first.send(f"3 {event_id} 1")
        await task
        await first.send("2 42")
        await self.until(lambda: len(self.adapter.players) == 1)
        self.assertIsNone(self.adapter.selected_id)
        self.assertEqual(self.adapter.active_player().values["title"], "Secondo")
        await self.adapter.execute("scselect", "auto")
        self.assertIn("automatica", await self.adapter.execute("scplayers", ""))

    async def test_port_conflict_is_reported_and_retry_works(self):
        other = sc.SoundCloudAdapter(self.adapter.port)
        try:
            await other.start()
            self.assertIsNone(other.server)
            self.assertIn("occupata", other.error)
            await self.adapter.close()
            await other.start()
            self.assertIsNotNone(other.server)
            self.assertEqual(other.error, "")
        finally:
            await other.close()

    async def test_long_unicode_metadata_and_many_tabs_fit_telegram(self):
        client = await self.browser(title="🎶" * 1000, artist="🎵" * 1000, album="💿" * 1000)
        for remote_id in range(43, 106):
            await client.send(f"0 {remote_id} " + player_payload(id=remote_id, title="🎶" * 1000, artist="🎵" * 1000))
        await self.until(lambda: len(self.adapter.players) == 64)
        for command in ("scnp", "scplayers"):
            result = "[ MELIXSA / SOUNDCLOUD ]\n" + await self.adapter.execute(command, "")
            self.assertLess(len(result.encode("utf-16-le")) // 2, 4096)
        result = await self.adapter.execute("scplayers", "")
        self.assertRegex(result, r"(?m)^64(?: \*)? » ")


class TelegramIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_prefixes_routing_and_own_account_only(self):
        from Cogs.core import runtime as selfbot

        with patch.object(selfbot.state, "minimal_mode", False):
            self.assertIn("!soundcloud » SoundCloud", selfbot.help_text("!"))
        self.assertEqual(selfbot.help_text("!", "sc"), selfbot.help_text("!", "soundcloud"))
        for command in sc.COMMANDS:
            self.assertIn(command, selfbot.COMMANDS)
            self.assertIn("!" + command, selfbot.help_text("!", command))
        client = SimpleNamespace()
        message = SimpleNamespace(chat=SimpleNamespace(id=10, type=selfbot.enums.ChatType.PRIVATE),
                                  from_user=SimpleNamespace(id=99), text="/scnext", delete=AsyncMock())
        with patch.object(selfbot, "handle_soundcloud_command", new_callable=AsyncMock) as handler, \
             patch.object(selfbot, "schedule_delete"), patch.object(selfbot.state, "prefix", "/"):
            await selfbot.process_message(client, message, 99)
            handler.assert_awaited_once_with(message, "scnext", "")
            handler.reset_mock()
            message.from_user.id = 100
            await selfbot.process_message(client, message, 99)
            handler.assert_not_awaited()
            message.from_user.id = 99
            message.text = "/soundcloud volume 50"
            await selfbot.process_message(client, message, 99)
            handler.assert_awaited_once_with(message, "scvolume", "50")
            handler.reset_mock()
            with patch.object(selfbot.state, "prefix", "!"):
                message.text = "!scpause"
                await selfbot.process_message(client, message, 99)
                handler.assert_awaited_once_with(message, "scpause", "")

    async def test_soundcloud_error_is_console_only(self):
        from Cogs.core import runtime as selfbot

        message = SimpleNamespace()
        with patch.object(selfbot.soundcloud, "execute", new_callable=AsyncMock) as execute, \
             patch.object(selfbot, "respond", new_callable=AsyncMock) as respond, \
             patch.object(selfbot.state, "prefix", "!"), patch.object(selfbot.console_tools, "event") as log:
            execute.side_effect = sc.SoundCloudError("Nessuna scheda collegata")
            await selfbot.handle_soundcloud_command(message, "scnp", "")
            execute.assert_awaited_once_with("scnp", "", "!")
            respond.assert_not_awaited()
            self.assertIn("Nessuna scheda collegata", log.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
