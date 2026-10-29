import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums, raw
from pyrogram.errors import FloodWait, FreshResetAuthorisationForbidden

from Cogs.core import anti_login_tools as tools, runtime


def session(hash, current=False):
    return SimpleNamespace(hash=hash, current=current)


def service_message(text, user_id=777000, chat_id=777000):
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id, type=enums.ChatType.PRIVATE),
                           from_user=SimpleNamespace(id=user_id), text=text, outgoing=False)


class AntiLoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_on_saved_off_and_last_success_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            with patch.object(runtime, "STATE_FILE", path), patch.object(runtime, "DATA_DIR", Path(folder)):
                self.assertTrue(runtime.MonitorState.load().anti_login_enabled)
                state = runtime.MonitorState(anti_login_enabled=False, anti_login_last_reset=100.0)
                state.save()
                loaded = runtime.MonitorState.load()
                self.assertFalse(loaded.anti_login_enabled)
                self.assertEqual(loaded.anti_login_last_reset, 100.0)

    def setUp(self):
        self.enabled = True
        self.now = 100.0
        self.saved = AsyncMock()
        self.guard = tools.AntiLoginController(lambda: self.enabled, save_reset=self.saved, clock=lambda: self.now)
        self.sessions = [session(0, True), session(10)]
        self.reset_error = None
        async def invoke(request, **kwargs):
            if isinstance(request, raw.functions.account.GetAuthorizations):
                return SimpleNamespace(authorizations=list(self.sessions))
            if isinstance(request, raw.functions.account.ResetAuthorization) and self.reset_error:
                raise self.reset_error
            return True
        self.client = SimpleNamespace(invoke=AsyncMock(side_effect=invoke), send_message=AsyncMock())

    async def test_only_new_sessions_are_reset_and_current_is_always_protected(self):
        await self.guard.initialize(self.client)
        self.sessions += [session(20), session(30, True)]
        await self.guard.scan(self.client)
        resets = [call.args[0].hash for call in self.client.invoke.call_args_list if isinstance(call.args[0], raw.functions.account.ResetAuthorization)]
        self.assertEqual(resets, [20])
        self.saved.assert_awaited_once()
        self.assertNotIn(20, self.guard.trusted)

    async def test_initialization_failure_never_causes_mass_session_reset(self):
        self.client.invoke.side_effect = OSError("unreachable")
        self.assertFalse(await self.guard.initialize(self.client))
        self.assertIsNone(self.guard.trusted)
        self.client.invoke.reset_mock()
        await self.guard.scan(self.client)
        self.client.invoke.assert_not_awaited()
        self.saved.assert_not_awaited()

    async def test_failed_reset_stays_untrusted_and_does_not_record_success(self):
        await self.guard.initialize(self.client)
        self.sessions.append(session(20))
        self.reset_error = FreshResetAuthorisationForbidden()
        await self.guard.scan(self.client)
        self.now += tools.MIN_RESET_INTERVAL
        await self.guard.scan(self.client)
        self.assertNotIn(20, self.guard.trusted)
        self.saved.assert_not_awaited()
        self.assertIn("24 ore", self.guard.last_error)
        self.client.send_message.assert_not_awaited()
        resets = [c for c in self.client.invoke.call_args_list if isinstance(c.args[0], raw.functions.account.ResetAuthorization)]
        self.assertEqual(len(resets), 2)

    async def test_off_prevents_code_invalidation_and_resets(self):
        await self.guard.initialize(self.client)
        self.client.invoke.reset_mock()
        self.enabled = False
        await self.guard.handle_message(self.client, service_message("Login code: 54321"))
        await self.guard.scan(self.client)
        self.client.invoke.assert_not_awaited()

    async def test_detects_labeled_codes_without_exposing_them_in_notifications_or_logs(self):
        for text, code in (("Login code: 54321. Do not share.", "54321"), ("Codice di accesso: 98765.", "98765")):
            with self.subTest(text=text), patch.object(tools.console_tools, "event") as log:
                self.client.invoke.reset_mock()
                self.client.send_message.reset_mock()
                await self.guard.handle_message(self.client, service_message(text))
                request = self.client.invoke.call_args.args[0]
                self.assertIsInstance(request, raw.functions.account.InvalidateSignInCodes)
                self.assertEqual(request.codes, [code])
                self.assertNotIn(code, str(self.client.send_message.call_args_list))
                self.assertNotIn(code, str(log.call_args_list))
        self.assertTrue(self.guard.wakeup.is_set())

    async def test_unrelated_numbers_and_spoofed_or_forwarded_messages_are_ignored(self):
        for msg in (service_message("New login on 2026-10-12 at 16:56"),
                    service_message("Login code: 123456789"),
                    service_message("Login code: 54321", user_id=42),
                    service_message("Login code: 54321", chat_id=42)):
            await self.guard.handle_message(self.client, msg)
        self.client.invoke.assert_not_awaited()

    async def test_flood_wait_blocks_further_requests_until_required_time(self):
        await self.guard.initialize(self.client)
        self.client.invoke.side_effect = FloodWait(30)
        await self.guard.handle_message(self.client, service_message("Login code: 54321"))
        self.client.invoke.reset_mock()
        await self.guard.scan(self.client)
        await self.guard.handle_message(self.client, service_message("Login code: 54321"))
        self.client.invoke.assert_not_awaited()
        self.assertEqual(self.guard.retry_after, self.now + 30)

    async def test_unconfirmed_rpc_does_not_record_reset_success(self):
        await self.guard.initialize(self.client)
        self.sessions.append(session(20))
        original = self.client.invoke.side_effect
        async def invoke(request, **kwargs):
            if isinstance(request, raw.functions.account.ResetAuthorization):
                return False
            return await original(request, **kwargs)
        self.client.invoke.side_effect = invoke
        await self.guard.scan(self.client)
        self.saved.assert_not_awaited()
        self.assertNotIn(20, self.guard.trusted)

    async def test_background_monitor_catches_new_sessions_without_a_login_code_and_stops_cleanly(self):
        await self.guard.start(self.client)
        self.sessions.append(session(20))
        self.guard.wakeup.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if self.saved.await_count:
                break
        self.saved.assert_awaited_once()
        await self.guard.close()
        self.assertIsNone(self.guard.task)

    async def test_settings_command_saves_mode_and_alias_routes_correctly(self):
        state = runtime.MonitorState()
        msg = service_message("", user_id=99, chat_id=99)
        with patch.object(runtime, "state", state), patch.object(state, "save") as save, \
             patch.object(runtime, "anti_login", self.guard), patch.object(runtime, "respond", new_callable=AsyncMock):
            await runtime.handle_command(self.client, msg, "anti-login", "off")
            self.assertFalse(state.anti_login_enabled)
            await runtime.handle_command(self.client, msg, "antilogin", "enable")
            self.assertTrue(state.anti_login_enabled)
            self.assertEqual(save.call_count, 2)
            with self.assertRaises(ValueError):
                await runtime.handle_command(self.client, msg, "anti-login", "invalid")
        self.assertIn(">anti-login", runtime.help_text(">", "settings"))

    async def test_failed_setting_save_preserves_previous_mode(self):
        state = runtime.MonitorState(anti_login_enabled=False)
        with patch.object(runtime, "state", state), patch.object(state, "save", side_effect=OSError("read only")), \
             patch.object(runtime, "anti_login", self.guard):
            with self.assertRaises(OSError):
                await runtime.handle_command(self.client, service_message(""), "anti-login", "on")
        self.assertFalse(state.anti_login_enabled)
        self.client.invoke.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
