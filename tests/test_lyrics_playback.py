import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import requests
from pyrogram import enums
from pyrogram.errors import FloodWait
from pyrogram.types import Chat, Message

from Cogs.core import lyrics_tools as lyrics
from Cogs.core import soundcloud_tools
from Cogs.core import runtime as selfbot


class LookupTests(unittest.TestCase):
    def setUp(self):
        contact = patch.dict(lyrics.os.environ, {"LRCLIB_CLIENT_CONTACT": "https://example.com/melixsa"})
        contact.start()
        self.addCleanup(contact.stop)

    def test_identification_requires_real_contact_configuration(self):
        self.assertEqual(lyrics.client_user_agent(), "MelixsaSelfbot/1.0 (https://example.com/melixsa)")
        for contact in ("", "SoundCloud lyrics", "user@example.com\r\nInjected: x", "https://user:secret@example.com"):
            with patch.dict(lyrics.os.environ, {"LRCLIB_CLIENT_CONTACT": contact}), self.assertRaises(lyrics.LyricsError):
                lyrics.client_user_agent()
        with patch.dict(lyrics.os.environ, {"LRCLIB_CLIENT_CONTACT": "maintainer@example.com"}):
            self.assertIn("maintainer@example.com", lyrics.client_user_agent())

    def test_retry_after_and_transient_status_classification(self):
        self.assertEqual(lyrics.retry_after_seconds("90"), 90)
        self.assertEqual(lyrics.retry_after_seconds("invalid"), 0)
        self.assertEqual(lyrics.retry_after_seconds("inf"), 0)
        with patch.object(lyrics.time, "time", return_value=0):
            self.assertEqual(lyrics.retry_after_seconds("Thu, 01 Jan 1970 00:02:00 GMT"), 120)
        track = lyrics.Track(1, "Prova", "Artista", "", 120)
        for status in (429, 500, 502, 503, 504):
            response = MagicMock()
            response.__enter__.return_value = response
            response.status_code = status
            response.headers = {"Retry-After": "90"}
            with patch.object(requests, "get", return_value=response) as get, patch.object(lyrics, "_next_request_at", 0), patch.object(lyrics, "REQUEST_INTERVAL", 0):
                with self.assertRaises(lyrics.TemporaryLyricsError) as error:
                    lyrics.fetch_lyrics(track)
            self.assertEqual(error.exception.retry_after, 90)
            get.assert_called_once()

    def test_contract_missing_lyrics_errors_and_size(self):
        track = lyrics.Track(1, "Titolo prova", "Artista prova", "Album prova", 120)
        for body, status, expected in (
            (json.dumps({"duration": 120, "syncedLyrics": "[00:01]Riga A"}).encode(), 200, [(1, "Riga A")]),
            (b'{}', 404, []), (b'{"plainLyrics":"senza tempi"}', 200, []),
            (b'{"duration":300,"syncedLyrics":"[00:01]Riga A"}', 200, []),
            (b'bad json', 200, None), (b'', 429, None), (b'x' * (lyrics.MAX_RESPONSE + 1), 200, None),
        ):
            response = MagicMock()
            response.__enter__.return_value = response
            response.status_code = status
            response.headers = {"Content-Type": "application/json; charset=utf-8"}
            response.iter_content.return_value = [body]
            with patch.object(requests, "get", return_value=response) as get, patch.object(lyrics, "_next_request_at", 0), patch.object(lyrics, "REQUEST_INTERVAL", 0):
                if expected is None:
                    with self.assertRaises(lyrics.LyricsError):
                        lyrics.fetch_lyrics(track)
                else:
                    self.assertEqual(lyrics.fetch_lyrics(track), expected)
            get.assert_called_once()
            self.assertEqual(get.call_args.args, ("https://lrclib.net/api/get",))
            self.assertEqual(get.call_args.kwargs["params"], {"track_name": track.title, "artist_name": track.artist, "album_name": track.album, "duration": 120})
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
            self.assertIn("https://example.com/melixsa", get.call_args.kwargs["headers"]["User-Agent"])
            response.__exit__.assert_called_once()

    def test_plain_text_validation_error_and_non_json_success(self):
        track = lyrics.Track(1, "Prova", "Artista", "", 120)
        for status, expected in ((400, "parametri"), (200, "non JSON")):
            response = MagicMock()
            response.__enter__.return_value = response
            response.status_code = status
            response.headers = {"Content-Type": "text/html"}
            with patch.object(requests, "get", return_value=response), patch.object(lyrics, "_next_request_at", 0), patch.object(lyrics, "REQUEST_INTERVAL", 0):
                with self.assertRaisesRegex(lyrics.LyricsError, expected):
                    lyrics.fetch_lyrics(track)
            response.iter_content.assert_not_called()

    def test_request_gap_and_server_cooldown_are_shared(self):
        track = lyrics.Track(1, "Prova", "Artista", "", 120)
        with patch.object(lyrics, "_next_request_at", 0), patch.object(lyrics.time, "monotonic", return_value=100), patch.object(lyrics.time, "sleep") as sleep, patch.object(lyrics, "_fetch_lyrics", return_value=[]) as fetch:
            lyrics.fetch_lyrics(track)
            lyrics.fetch_lyrics(track)
            self.assertAlmostEqual(sleep.call_args.args[0], 0.3)
            fetch.side_effect = lyrics.TemporaryLyricsError("HTTP 429", 90)
            with self.assertRaises(lyrics.TemporaryLyricsError):
                lyrics.fetch_lyrics(track)
            self.assertEqual(lyrics._next_request_at, 190)
            fetch.reset_mock()
            with self.assertRaises(lyrics.TemporaryLyricsError):
                lyrics.fetch_lyrics(track)
            fetch.assert_not_called()

    def test_optional_metadata_is_omitted_when_unavailable(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 404
        with patch.object(requests, "get", return_value=response) as get, patch.object(lyrics, "_next_request_at", 0):
            lyrics.fetch_lyrics(lyrics.Track(1, "Prova", "Artista", "", 5000))
        self.assertEqual(get.call_args.kwargs["params"], {"track_name": "Prova", "artist_name": "Artista"})

    def test_uploader_fallback_uses_embedded_artist_and_keeps_duration(self):
        track = lyrics.Track(1, "Massimo Pericolo - MISS (original)", "Agostino Barberio", "", 170)
        missing, found = MagicMock(), MagicMock()
        missing.__enter__.return_value = missing
        missing.status_code = 404
        found.__enter__.return_value = found
        found.status_code = 200
        found.headers = {"Content-Type": "application/json"}
        for duration, expected in ((170, [(1, "Riga A")]), (200, [])):
            found.iter_content.return_value = [json.dumps({"duration": duration, "syncedLyrics": "[00:01]Riga A"}).encode()]
            with patch.object(requests, "get", side_effect=[missing, found]) as get, \
                    patch.object(lyrics, "_next_request_at", 0), patch.object(lyrics, "REQUEST_INTERVAL", 0):
                self.assertEqual(lyrics.fetch_lyrics(track), expected)
            self.assertEqual(get.call_count, 2)
            self.assertEqual(get.call_args_list[0].kwargs["params"]["artist_name"], "Agostino Barberio")
            self.assertEqual(get.call_args.kwargs["params"], {"track_name": "MISS", "artist_name": "Massimo Pericolo", "duration": 170})

    def test_metadata_fallback_preserves_remixes_and_alternative_versions(self):
        for title in ("MISS RMX", "MISS (slowed)", "MISS (live)"):
            track = lyrics.Track(1, "Massimo Pericolo - " + title, "Uploader", "", 170)
            self.assertEqual(lyrics.lookup_tracks(track)[1].title, title)
        self.assertEqual(lyrics.lookup_tracks(lyrics.Track(1, "MISS", "Massimo Pericolo", "", 170)),
                         [lyrics.Track(1, "MISS", "Massimo Pericolo", "", 170)])

    def test_metadata_fallback_does_not_bypass_service_errors(self):
        track = lyrics.Track(1, "Massimo Pericolo - MISS (original)", "Uploader", "", 170)
        with patch.object(lyrics, "_fetch_lyrics", side_effect=lyrics.TemporaryLyricsError("HTTP 503", 1)) as fetch, \
                patch.object(lyrics, "_next_request_at", 0):
            with self.assertRaises(lyrics.TemporaryLyricsError):
                lyrics.fetch_lyrics(track)
        fetch.assert_called_once()


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        jitter = patch.object(lyrics.random, "uniform", return_value=0)
        jitter.start()
        self.addCleanup(jitter.stop)
        self.player = soundcloud_tools.Player(1, 1, None, {"title": "Prova", "artist": "Artista", "state": 0, "position": 1, "duration": 120})
        self.adapter = SimpleNamespace(active_player=MagicMock(return_value=self.player))
        self.controller = lyrics.LyricsController(self.adapter)
        self.lines = [(1, "Riga A"), (5, "Riga B"), (10, "Riga C")]
        patcher = patch.object(lyrics, "fetch_lyrics", return_value=self.lines)
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)
        self.send, self.notify = AsyncMock(), AsyncMock()
        self.addAsyncCleanup(self.controller.stop)

    async def tick(self, position, now, state=0):
        self.player.values.update(position=position, state=state)
        with patch.object(self.controller, "clock", return_value=now):
            await self.controller.tick(self.send, self.notify)

    async def test_pause_seek_rate_limit_and_no_duplicates(self):
        await self.tick(1, 100)
        await self.tick(1, 101)
        await self.tick(5, 102)
        await self.tick(5, 104, state=1)
        self.send.assert_awaited_once_with("Riga A")
        await self.tick(5, 105)
        await self.tick(40, 110)
        self.assertEqual(self.send.await_count, 2)
        await self.tick(1, 115)
        self.assertEqual([call.args[0] for call in self.send.await_args_list], ["Riga A", "Riga B", "Riga A"])
        self.fetch.assert_called_once()

    async def test_503_waits_then_recovers_at_current_position(self):
        self.fetch.side_effect = [lyrics.TemporaryLyricsError("HTTP 503", 90), self.lines]
        await self.tick(1, 100)
        self.assertEqual(self.controller.lookup_retry_after, 190)
        self.assertFalse(self.controller.cache)
        await self.tick(2, 110)
        self.fetch.assert_called_once()
        self.send.assert_not_awaited()
        self.notify.assert_not_awaited()
        self.assertIn("80 s", self.controller.status)
        await self.tick(10, 190)
        self.send.assert_awaited_once_with("Riga C")
        self.assertEqual(self.controller.lookup_failures, 0)

    async def test_short_retry_after_does_not_exhaust_retries_in_seconds(self):
        self.fetch.side_effect = [lyrics.TemporaryLyricsError("HTTP 503", 1), self.lines]
        await self.tick(1, 100)
        self.assertEqual(self.controller.lookup_retry_after, 130)
        await self.tick(1, 101)
        self.fetch.assert_called_once()
        await self.tick(1, 130)
        self.assertEqual(self.fetch.call_count, 2)
        self.send.assert_awaited_once_with("Riga A")

    async def test_repeated_short_retry_after_uses_increasing_backoff(self):
        self.fetch.side_effect = lyrics.TemporaryLyricsError("HTTP 503", 1)
        for now, retry_at in ((100, 130), (130, 190), (190, 310)):
            await self.tick(1, now)
            self.assertEqual(self.controller.lookup_retry_after, retry_at)
            await self.tick(1, retry_at - 1)
        self.assertEqual(self.fetch.call_count, 3)
        with self.assertRaisesRegex(lyrics.LyricsError, "4 tentativi"):
            await self.tick(1, 310)
        self.notify.assert_not_awaited()
        self.send.assert_not_awaited()

    async def test_long_retry_after_is_not_capped_by_backoff(self):
        self.fetch.side_effect = lyrics.TemporaryLyricsError("HTTP 503", 600)
        await self.tick(1, 100)
        self.assertEqual(self.controller.lookup_retry_after, 700)
        await self.tick(1, 699)
        self.fetch.assert_called_once()

    async def test_retry_adds_jitter_after_required_wait(self):
        self.fetch.side_effect = lyrics.TemporaryLyricsError("HTTP 503", 90)
        with patch.object(lyrics.random, "uniform", return_value=5):
            await self.tick(1, 100)
        self.assertEqual(self.controller.lookup_retry_after, 195)
        await self.tick(1, 194)
        self.fetch.assert_called_once()

    async def test_retries_are_bounded_and_do_not_flood_chat(self):
        self.fetch.side_effect = lyrics.TemporaryLyricsError("HTTP 503")
        await self.tick(1, 100)
        self.assertEqual(self.controller.lookup_retry_after, 130)
        await self.tick(1, 130)
        self.assertEqual(self.controller.lookup_retry_after, 190)
        await self.tick(1, 190)
        self.assertEqual(self.controller.lookup_retry_after, 310)
        with self.assertRaisesRegex(lyrics.LyricsError, "4 tentativi"):
            await self.tick(1, 310)
        self.assertEqual(self.fetch.call_count, 4)
        self.notify.assert_not_awaited()
        self.send.assert_not_awaited()

    async def test_changing_track_does_not_bypass_service_wait(self):
        self.fetch.side_effect = lyrics.TemporaryLyricsError("HTTP 429", 120)
        await self.tick(1, 100)
        self.player.values["title"] = "Nuova canzone"
        await self.tick(1, 110)
        self.fetch.assert_called_once()

    async def test_off_cancels_pending_retry(self):
        self.controller.lookup_retry_after = self.controller.clock() + 60
        await self.controller.start((1, 7), self.send, self.notify)
        await asyncio.sleep(0)
        self.assertTrue(self.controller.running)
        await self.controller.stop()
        await asyncio.sleep(0)
        self.fetch.assert_not_called()
        self.send.assert_not_awaited()

    async def test_track_changes_during_lookup_and_missing_text(self):
        def fetch(track):
            self.player.values["title"] = "Nuovo titolo"
            return self.lines
        self.fetch.side_effect = fetch
        await self.tick(1, 100)
        self.send.assert_not_awaited()
        self.fetch.side_effect = None
        self.fetch.return_value = []
        await self.tick(1, 104)
        await self.tick(2, 105)
        self.notify.assert_awaited_once()
        self.player.values["title"] = "Terzo titolo"
        self.fetch.return_value = self.lines
        await self.tick(1, 110)
        self.send.assert_awaited_once_with("Riga A")

    async def test_disconnect_and_floodwait(self):
        self.adapter.active_player.side_effect = soundcloud_tools.SoundCloudError("disconnesso")
        await self.tick(1, 100)
        self.send.assert_not_awaited()
        self.adapter.active_player.side_effect = None
        self.send.side_effect = FloodWait(30)
        with patch.object(self.controller, "clock", return_value=100):
            await self.controller.run(self.send, self.notify)
            self.assertEqual(self.controller.retry_after, 130)
            with self.assertRaises(lyrics.LyricsError):
                await self.controller.start((1, 7), self.send, self.notify)
        self.send.assert_awaited_once()

    async def test_start_before_connection_waits_and_resumes_when_player_arrives(self):
        self.adapter.active_player.side_effect = soundcloud_tools.SoundCloudError("WebNowPlaying non collegato")
        await self.controller.start((1, 7), self.send, self.notify)
        await asyncio.sleep(0)
        self.assertTrue(self.controller.running)
        self.assertEqual(self.controller.destination, (1, 7))
        self.assertIn("in attesa", self.controller.status)
        self.fetch.assert_not_called()
        self.adapter.active_player.side_effect = None
        await self.tick(1, 100)
        self.send.assert_awaited_once_with("Riga A")
        self.assertEqual(self.controller.status, "attivo")

    async def test_invalid_chat_switch_preserves_running_destination(self):
        async def worker(*args):
            await asyncio.Event().wait()
        with patch.object(self.controller, "run", side_effect=worker):
            await self.controller.start((1, 7), self.send, self.notify)
            first = self.controller.task
            self.adapter.active_player.side_effect = soundcloud_tools.SoundCloudError("disconnesso")
            with self.assertRaises(soundcloud_tools.SoundCloudError):
                await self.controller.start((2, 8), self.send, self.notify)
            self.assertIs(self.controller.task, first)
            self.assertEqual(self.controller.destination, (1, 7))
            self.assertTrue(self.controller.running)

    async def test_failed_adapter_is_not_treated_as_pending_connection(self):
        self.adapter.error = "Porta occupata"
        self.adapter.active_player.side_effect = soundcloud_tools.SoundCloudError(self.adapter.error)
        with self.assertRaisesRegex(soundcloud_tools.SoundCloudError, "Porta occupata"):
            await self.controller.start((1, 7), self.send, self.notify)
        self.assertFalse(self.controller.running)
        self.assertIsNone(self.controller.destination)

    async def test_chat_switch_idempotent_start_and_stop(self):
        async def worker(*args):
            await asyncio.Event().wait()
        with patch.object(self.controller, "run", side_effect=worker):
            await self.controller.start((1, 7), self.send, self.notify)
            first = self.controller.task
            await self.controller.start((1, 7), self.send, self.notify)
            self.assertIs(first, self.controller.task)
            await self.controller.start((2, 8), self.send, self.notify)
            self.assertTrue(first.cancelled())
            self.assertEqual(self.controller.destination, (2, 8))
            second = self.controller.task
            await self.controller.stop()
            self.assertTrue(second.cancelled())
            self.assertIsNone(self.controller.destination)

    async def test_stop_during_lookup_prevents_late_send(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def lookup(*args):
            started.set()
            await release.wait()
            return self.lines
        with patch.object(lyrics.asyncio, "to_thread", side_effect=lookup):
            await self.controller.start((1, 7), self.send, self.notify)
            await started.wait()
            await self.controller.stop()
            release.set()
            await asyncio.sleep(0)
        self.send.assert_not_awaited()


class CommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        contact = patch.dict(lyrics.os.environ, {"LRCLIB_CLIENT_CONTACT": "https://example.com/melixsa"})
        contact.start()
        self.addCleanup(contact.stop)

    async def test_missing_contact_is_visible_in_status_without_starting_adapter(self):
        message = SimpleNamespace(chat=SimpleNamespace(id=10))
        controller = lyrics.LyricsController(None)
        with patch.dict(lyrics.os.environ, {"LRCLIB_CLIENT_CONTACT": ""}), \
                patch.object(selfbot, "lyrics", controller), \
                patch.object(selfbot.soundcloud, "start", new_callable=AsyncMock) as start, \
                patch.object(selfbot, "log_command_error") as log, \
                patch.object(selfbot, "respond", new_callable=AsyncMock) as respond:
            await selfbot.handle_lyrics_command(message, "on")
            start.assert_not_awaited()
            log.assert_called_once()
            respond.assert_not_awaited()
            await selfbot.handle_lyrics_command(message, "status")
            self.assertIn("LRCLIB_CLIENT_CONTACT", respond.call_args.args[1])
            self.assertIn("fermo:", respond.call_args.args[1])

    async def test_status_separates_old_error_from_live_connection_and_offers_start(self):
        message = SimpleNamespace(chat=SimpleNamespace(id=10))
        controller = lyrics.LyricsController(None)
        controller.status = "fermo: WebNowPlaying non collegato"
        with patch.object(selfbot, "lyrics", controller), \
                patch.object(selfbot.soundcloud, "active_player", return_value=object()), \
                patch.object(selfbot, "respond", new_callable=AsyncMock) as respond:
            await selfbot.handle_lyrics_command(message, "status")
        text = respond.call_args.args[1]
        self.assertIn("Player » collegato", text)
        self.assertIn("Ultimo esito » fermo: WebNowPlaying non collegato", text)
        self.assertIn(f"Avvia » {selfbot.state.prefix}sclyrics on", text)
        self.assertFalse(controller.running)

    async def test_adapter_failure_is_visible_in_status(self):
        message = SimpleNamespace(chat=SimpleNamespace(id=10))
        controller = lyrics.LyricsController(None)
        with patch.object(selfbot, "lyrics", controller), \
                patch.object(selfbot.soundcloud, "start", new_callable=AsyncMock,
                             side_effect=soundcloud_tools.SoundCloudError("Adattatore non disponibile")), \
                patch.object(selfbot, "log_command_error") as log, \
                patch.object(selfbot, "respond", new_callable=AsyncMock) as respond:
            await selfbot.handle_lyrics_command(message, "on")
            log.assert_called_once()
            respond.assert_not_awaited()
            await selfbot.handle_lyrics_command(message, "status")
            self.assertIn("fermo: Adattatore non disponibile", respond.call_args.args[1])

    async def test_routing_deletion_and_alias(self):
        message = SimpleNamespace(chat=SimpleNamespace(id=10, type=enums.ChatType.PRIVATE), from_user=SimpleNamespace(id=99), text=">sclyrics on", delete=AsyncMock())
        async def handle(*args):
            message.delete.assert_awaited_once()
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix=">")), patch.object(selfbot, "handle_lyrics_command", new_callable=AsyncMock, side_effect=handle) as handler:
            await selfbot.process_message(None, message, 99)
            handler.assert_awaited_once_with(message, "on")
            handler.reset_mock()
            message.from_user.id = 100
            await selfbot.process_message(None, message, 99)
            handler.assert_not_awaited()
            handler.side_effect = None
            await selfbot.handle_command(None, message, "soundcloud", "lyrics off")
            handler.assert_awaited_once_with(message, "off")
        self.assertIn(">sclyrics", selfbot.help_text(">", "soundcloud"))

    async def test_lines_are_codeblocks_in_original_topic_and_follow_timer(self):
        client = SimpleNamespace(send_message=AsyncMock())
        message = Message(client=client, id=10, message_thread_id=7, chat=Chat(id=-100123, type=enums.ChatType.SUPERGROUP))
        controller = lyrics.LyricsController(None)
        with patch.object(selfbot, "lyrics", controller), patch.object(selfbot.soundcloud, "start", new_callable=AsyncMock), patch.object(controller, "start", new_callable=AsyncMock) as start, patch.object(selfbot, "schedule_delete") as schedule:
            await selfbot.handle_lyrics_command(message, "on")
            self.assertEqual(start.call_args.args[0], (-100123, 7))
            client.send_message.reset_mock()
            schedule.reset_mock()
            await start.call_args.args[1](">autoreact off")
            kwargs = client.send_message.call_args.kwargs
            self.assertEqual(kwargs["chat_id"], -100123)
            self.assertEqual(kwargs["message_thread_id"], 7)
            self.assertIsNone(kwargs["reply_parameters"])
            self.assertEqual(kwargs["entities"][0].type, enums.MessageEntityType.PRE)
            self.assertFalse(kwargs["text"].startswith(">"))
            schedule.assert_called_once()


if __name__ == "__main__":
    unittest.main()
