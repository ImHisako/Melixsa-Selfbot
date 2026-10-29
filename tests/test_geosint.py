import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import requests

from pyrogram import enums
from pyrogram.types import Chat, Message, User

from Cogs.core import geosint_tools as geo
from Cogs.core import runtime as selfbot


RESULT = {
    "status": "success",
    "locations": [{"latitude": 48.8584, "longitude": 2.2945, "confidence": 0.95,
                   "address": "Paris", "reasoning": "Visual clues"}],
    "processing_time": "45.2s", "API_Requests_remaining": 67,
}


class RequestTests(unittest.TestCase):
    def response(self, raw, status=200):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = status
        response.iter_content.side_effect = lambda **kwargs: iter([raw])
        return response

    def request(self, **kwargs):
        response = self.response(json.dumps(RESULT).encode())
        with patch.object(requests, "post", return_value=response) as post:
            result = geo.analyze("dummy-key", **kwargs)
        self.assertEqual(result, RESULT)
        post.assert_called_once()
        response.__exit__.assert_called_once()
        options = dict(post.call_args.kwargs)
        self.assertFalse(options.pop("allow_redirects"))
        self.assertTrue(options.pop("stream"))
        self.assertEqual(options.pop("timeout"), (15, 180))
        return requests.Request("POST", post.call_args.args[0], **options).prepare()

    def test_multipart_upload_preserves_media_and_contract(self):
        request = self.request(media=b"image-bytes", mime="image/jpeg")
        self.assertEqual(request.url, geo.ENDPOINT)
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["X-API-Key"], "dummy-key")
        self.assertIn(b'name="analysis_mode"\r\n\r\nfast\r\n', request.body)
        self.assertIn(b'name="file"; filename="media.jpg"', request.body)
        self.assertIn(b'Content-Type: image/jpeg\r\n\r\nimage-bytes', request.body)

    def test_url_json_contract(self):
        request = self.request(url="https://example.com/image.jpg")
        self.assertEqual(json.loads(request.body), {
            "url": "https://example.com/image.jpg", "analysis_mode": "fast", "stream": False,
        })

    def test_http_errors_do_not_leak_raw_response_or_retry(self):
        for status in (302, 401, 402, 403, 429, 500):
            response = self.response(b"dummy-secret", status)
            with patch.object(requests, "post", return_value=response) as post:
                with self.assertRaises(geo.GeoSintError) as error:
                    geo.analyze("dummy-secret", url="https://example.com/a.jpg")
            self.assertNotIn("dummy-secret", str(error.exception))
            post.assert_called_once()
            response.__exit__.assert_called_once()

    def test_invalid_and_oversized_responses(self):
        for raw in (b"no-json", b'[]', b'{"status":"error"}', b"x" * (geo.MAX_RESPONSE_BYTES + 1)):
            response = self.response(raw)
            with patch.object(requests, "post", return_value=response), self.assertRaises(geo.GeoSintError):
                geo.analyze("dummy-key", url="https://example.com/a.jpg")

    def test_cloudflare_block_is_distinguished_from_key_errors(self):
        for body in (
            b'{"detail":"The site owner has blocked access based on your browser\'s signature."}',
            b'<html>Cloudflare error 1010 dummy-secret</html>',
        ):
            detail = geo.http_error_message(403, body)
            self.assertIn("Cloudflare 1010", detail)
            self.assertNotIn("dummy-secret", detail)
        self.assertIn("piano", geo.http_error_message(403, b'{"error":"Free plan fast mode only"}'))

    def test_connection_failure_does_not_leak_credentials_or_retry(self):
        with patch.object(requests, "post", side_effect=requests.Timeout("dummy-secret")) as post:
            with self.assertRaises(geo.GeoSintError) as error:
                geo.analyze("dummy-secret", url="https://example.com/a.jpg")
        self.assertNotIn("dummy-secret", str(error.exception))
        post.assert_called_once()

    def test_stream_read_stops_at_limit(self):
        response = MagicMock()
        response.iter_content.return_value = iter([b"abc", b"def", b"ghi"])
        self.assertEqual(geo.read_response(response, 4), b"abcd")
        self.assertEqual(next(response.iter_content.return_value), b"ghi")

    def test_chunks_preserve_every_field_and_utf16_limit(self):
        result = {**RESULT, "extra": "🦇" * 5000, "locations": RESULT["locations"] * 50}
        chunks = geo.result_chunks(result)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(json.loads("".join(chunks)), result)
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 3600 for part in chunks))


class ReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_is_memory_only_and_buffer_closed(self):
        downloaded = io.BytesIO(b"image-bytes")
        client = SimpleNamespace(download_media=AsyncMock(return_value=downloaded))
        reply = SimpleNamespace(photo=SimpleNamespace(file_size=11))
        with patch.object(geo, "analyze", return_value=RESULT) as analyze:
            result = await geo.analyze_reply(client, SimpleNamespace(reply_to_message=reply), "dummy-key")
        self.assertEqual(result, RESULT)
        client.download_media.assert_awaited_once_with(reply, in_memory=True)
        self.assertTrue(downloaded.closed)
        analyze.assert_called_once_with("dummy-key", media=b"image-bytes", mime="image/jpeg")

    async def test_missing_key_missing_reply_unsupported_and_oversized_never_analyze(self):
        client = SimpleNamespace(download_media=AsyncMock())
        cases = [
            (SimpleNamespace(), "dummy-key"),
            (SimpleNamespace(reply_to_message=SimpleNamespace()), ""),
            (SimpleNamespace(reply_to_message=SimpleNamespace(document=SimpleNamespace(mime_type="application/pdf"))), "dummy-key"),
            (SimpleNamespace(reply_to_message=SimpleNamespace(photo=SimpleNamespace(file_size=geo.MAX_MEDIA_BYTES + 1))), "dummy-key"),
        ]
        with patch.object(geo, "analyze") as analyze:
            for message, key in cases:
                with self.assertRaises(geo.GeoSintError):
                    await geo.analyze_reply(client, message, key)
            analyze.assert_not_called()
        client.download_media.assert_not_awaited()

    async def test_reply_id_fetch_and_url(self):
        reply = SimpleNamespace(text="https://example.com/image.jpg")
        client = SimpleNamespace(get_messages=AsyncMock(return_value=reply))
        message = SimpleNamespace(reply_to_message_id=12, chat=SimpleNamespace(id=34))
        with patch.object(geo, "analyze", return_value=RESULT) as analyze:
            await geo.analyze_reply(client, message, "dummy-key")
        client.get_messages.assert_awaited_once_with(34, 12)
        analyze.assert_called_once_with("dummy-key", url="https://example.com/image.jpg")

    async def test_command_deleted_before_analysis_and_all_parts_are_codeblocks(self):
        client = SimpleNamespace(delete_messages=AsyncMock(), send_message=AsyncMock())
        message = Message(client=client, id=10, text=">geosint", message_thread_id=7,
                          chat=Chat(id=-100123, type=enums.ChatType.SUPERGROUP), from_user=User(id=99))
        result = {**RESULT, "extra": "🖤" * 5000}
        async def analyze(*args):
            client.delete_messages.assert_awaited_once()
            return result
        with patch.object(selfbot, "state", selfbot.MonitorState(prefix=">")), \
             patch.object(geo, "analyze_reply", new_callable=AsyncMock, side_effect=analyze), \
             patch.object(selfbot, "schedule_delete") as schedule:
            await selfbot.process_message(client, message, 99)
            schedule.assert_not_called()
        reconstructed = []
        for call in client.send_message.call_args_list:
            kwargs = call.kwargs
            self.assertEqual(kwargs["message_thread_id"], 7)
            self.assertIsNone(kwargs["reply_parameters"])
            self.assertEqual(kwargs["entities"][0].type, enums.MessageEntityType.PRE)
            text = kwargs["text"]
            self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 4096)
            reconstructed.append(text.split("\n", 1)[1])
        self.assertEqual(json.loads("".join(reconstructed)), result)

    async def test_configuration_error_is_console_only(self):
        message = SimpleNamespace(answer=AsyncMock())
        with patch.object(geo, "analyze_reply", new_callable=AsyncMock, side_effect=geo.GeoSintError("Missing key")), \
             patch.object(selfbot, "schedule_delete"), patch.object(selfbot.console_tools, "event") as log:
            await selfbot.handle_geosint_command(None, message, "")
        message.answer.assert_not_awaited()
        self.assertIn("Missing key", log.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
