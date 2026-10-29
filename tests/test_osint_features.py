import asyncio
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image

from Cogs.core import osint_features as features, runtime
from Cogs.core.osint_extras import checker, queries


class ReportTests(unittest.TestCase):
    def test_conversion_keeps_links_unicode_and_literal_user_text(self):
        report = queries.Result('<b>Report</b>\n&lt;b&gt;utente&lt;/b&gt; 🖤 <a href="https://example.com/u">Profilo</a>',
                                links=[("Google", "https://example.com")], actions=[("Scan", "user", "utente")])
        text = features.plain_result(report, ">")
        self.assertIn("<b>utente</b>", text)
        self.assertIn("Profilo (https://example.com/u)", text)
        self.assertIn(">username utente", text)
        parts = features.chunks(text * 300)
        self.assertEqual("".join(parts), text * 300)
        self.assertTrue(all(len(part.encode('utf-16-le')) // 2 <= 3400 for part in parts))

    def test_hidden_forward_never_invents_sender_id(self):
        result = features.forward_report(SimpleNamespace(forward_sender_name="Nome nascosto"))
        self.assertIn("Nome nascosto", result.text)
        self.assertIn("non fornisce", result.text)
        with self.assertRaises(ValueError): features.forward_report(SimpleNamespace())

    def test_image_exif_reads_camera_without_external_upload(self):
        image = Image.new("RGB", (10, 10))
        exif = Image.Exif()
        exif[271] = "Test Camera"
        data = io.BytesIO()
        image.save(data, format="JPEG", exif=exif)
        result = queries.exif_report(data.getvalue())
        self.assertIn("Test Camera", result.text)
        self.assertIn("No GPS", result.text)


class OSINTTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_detects_and_dispatches_without_using_profile_name_command(self):
        with patch.object(queries, "name_search", new_callable=AsyncMock, return_value=queries.Result("Name")) as name:
            await features.lookup("autoosint", "Jane Doe")
            name.assert_awaited_once_with("Jane Doe")
        with patch.object(runtime, "handle_osint_command", new_callable=AsyncMock) as handle:
            msg = SimpleNamespace(chat=SimpleNamespace(id=1, type=runtime.enums.ChatType.PRIVATE))
            await runtime.handle_command(None, msg, "osint", "name Jane Doe")
            handle.assert_awaited_once_with(msg, "namesearch", "Jane Doe", client=None)

    async def test_phone_local_numbers_require_region_and_international_format_works(self):
        result = await features.lookup("phone", "+12025550123")
        self.assertIn("+12025550123", features.plain_result(result, ">"))
        with patch.object(queries, "phone", new_callable=AsyncMock, return_value=queries.Result("Phone")) as phone:
            await features.lookup("phone", "IT 0612345678")
            phone.assert_awaited_once_with("0612345678", "IT")

    async def test_unavailable_breach_service_is_not_reported_as_clean(self):
        with patch.object(queries, "_breach", new_callable=AsyncMock, return_value=("error", [])):
            result = await features.lookup("breach", "test@example.com")
        self.assertIn("unavailable", result.text)
        self.assertNotIn("Not found", result.text)

    async def test_failed_dns_is_reported_as_unknown_in_email_and_domain(self):
        with patch.object(queries, "_dns", new_callable=AsyncMock, return_value=None), \
             patch.object(queries, "_gravatar", new_callable=AsyncMock, return_value=None), \
             patch.object(queries, "_holehe", new_callable=AsyncMock, return_value=None), \
             patch.object(queries, "_breach", new_callable=AsyncMock, return_value=("error", [])), \
             patch.object(queries, "_whois", return_value=None), \
             patch.object(queries, "_subdomains", new_callable=AsyncMock, return_value=None):
            email = await queries.email("test@example.com")
            domain = await queries.domain("example.com")
        self.assertIn("MX lookup unavailable", email.text)
        self.assertIn("SPF unknown", domain.text)
        self.assertIn("DMARC unknown", domain.text)

    async def test_username_report_contains_full_file_and_possible_match_wording(self):
        hits = [{"cat": "coding", "site": "Example", "url": "https://example.com/user"}]
        with patch.object(checker, "scan", new_callable=AsyncMock, return_value=(hits, 1)):
            result = await features.lookup("username", "user")
        self.assertIn("possible profiles", result.text)
        self.assertIn(b"https://example.com/user", result.file[1])

    async def test_adult_and_invalid_sites_are_filtered_before_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder) / "data.json"
            cache.write_text(json.dumps({"sites": [
                {"name": "Public", "uri_check": "https://example.com/{account}", "cat": "coding"},
                {"name": "Excluded", "uri_check": "https://example.org/{account}", "cat": "nsfw"},
                {"name": "Invalid", "uri_check": "https://example.net/{account}", "valid": False},
            ]}), encoding="utf-8")
            with patch.object(checker, "CACHE", cache), patch.dict(checker.os.environ, {"OSINT_INCLUDE_ADULT": "0"}):
                sites = await checker.load_sites(None)
        self.assertEqual([site["name"] for site in sites], ["Public"])

    async def test_stream_read_is_complete_and_enforces_bound(self):
        async def stream(size):
            yield b"first"
            yield b"second"
        response = SimpleNamespace(content=SimpleNamespace(iter_chunked=stream))
        self.assertEqual(await checker.read_limited(response, 20), b"firstsecond")
        with self.assertRaises(ValueError): await checker.read_limited(response, 5)

    async def test_report_files_and_chunks_preserve_topic_and_timer(self):
        msg = SimpleNamespace(chat=SimpleNamespace(id=123), message_thread_id=7)
        client = SimpleNamespace(send_document=AsyncMock())
        report = queries.Result("🖤" * 4000, file=("report.txt", b"full result"))
        with patch.object(runtime, "respond", new_callable=AsyncMock) as respond, \
             patch.object(runtime, "schedule_delete") as timer, patch.object(features.asyncio, "sleep", new_callable=AsyncMock):
            await features.send_report(client, msg, report, "username", ">")
        self.assertEqual(client.send_document.call_args.kwargs["message_thread_id"], 7)
        timer.assert_called_once_with(client.send_document.return_value)
        self.assertEqual("".join(call.args[1] for call in respond.call_args_list), "🖤" * 4000)

    async def test_all_commands_are_registered_with_help(self):
        for command in features.COMMANDS:
            self.assertIn(command, runtime.COMMANDS)
            self.assertNotIn("Voce sconosciuta", runtime.help_text(">", command))


if __name__ == "__main__":
    unittest.main()
