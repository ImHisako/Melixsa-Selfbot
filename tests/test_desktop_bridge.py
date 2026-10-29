import asyncio
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from Cogs.core import afk_tools, runtime
from Cogs.core.instance_tools import InstanceLock
from MelixsaUI.backend.bridge import DesktopBridge


class DesktopBridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name, value in {
            "DATA_DIR": self.root, "STATE_FILE": self.root / "state.json",
            "state": runtime.MonitorState(), "state_lock": asyncio.Lock(),
            "afk": afk_tools.AFKController(),
        }.items():
            patcher = patch.object(runtime, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.bridge = DesktopBridge()
        self.addAsyncCleanup(self.bridge.close)

    async def test_settings_round_trip_preserves_access_and_monitoring(self):
        runtime.state.command_users = {123}
        runtime.state.surveillance = {-100}
        runtime.state.save()
        result = await self.bridge.update_settings({"autoreact": True, "autoreact_emojis": ["🔥", "💜"], "autoreact_count": 2})
        self.assertTrue(result["settings"]["autoreact"])
        saved = runtime.MonitorState.load()
        self.assertEqual(saved.autoreact_emojis, ("🔥", "💜"))
        self.assertEqual(saved.command_users, {123})
        self.assertEqual(saved.surveillance, {-100})

    async def test_invalid_patches_do_not_write_or_mutate(self):
        runtime.state.save()
        before = runtime.STATE_FILE.read_bytes()
        for patch_values in ({"delete_after": True}, {"prefix": "a"}, {"autoreact": "on"},
                             {"command_users": [1]}, {"autoreact_emojis": ["🔥", "🔥"]},
                             {"autoreact_count": 3}, {"console": {"debug_mode": 1}},
                             {"afk": {"enabled": True}}):
            with self.subTest(patch=patch_values), self.assertRaises(ValueError):
                await self.bridge.update_settings(patch_values)
            self.assertEqual(runtime.STATE_FILE.read_bytes(), before)

    async def test_failed_save_rolls_back_live_state(self):
        self.bridge.connection = "connected"
        with patch.object(runtime.state, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await self.bridge.update_settings({"autoreact": True, "delete_after": 5})
        self.assertFalse(runtime.state.autoreact)
        self.assertEqual(runtime.state.delete_after, 40)

    async def test_offline_edits_are_blocked_while_other_runtime_owns_lock(self):
        with InstanceLock(self.root / "runtime.lock"):
            with self.assertRaises(RuntimeError):
                await self.bridge.update_settings({"autoreact": True})
        self.assertFalse(runtime.STATE_FILE.exists())
        await self.bridge.update_settings({"autoreact": True})
        self.assertTrue(runtime.MonitorState.load().autoreact)

    async def test_afk_uses_real_controller_and_resets_on_disconnect(self):
        self.bridge.connection = "connected"
        await self.bridge.update_settings({"afk": {"enabled": True, "message": "Torno presto."}})
        self.assertTrue(runtime.afk.active)
        self.assertEqual(runtime.afk.message, "Torno presto.")
        await self.bridge.disconnect()
        self.assertFalse(runtime.afk.active)

    async def test_profile_uses_telegram_name_and_downloaded_photo(self):
        me = SimpleNamespace(id=42, first_name="Test", last_name="User", username="test_user", photo=SimpleNamespace(small_file_id="photo-id"), is_premium=True)
        client = SimpleNamespace(get_me=AsyncMock(return_value=me), download_media=AsyncMock(return_value=io.BytesIO(b"photo")))
        self.bridge.client = client
        result = await self.bridge.refresh_profile()
        self.assertEqual(result["profile"]["name"], "Test User")
        self.assertEqual(result["profile"]["photo"], "data:image/jpeg;base64,cGhvdG8=")
        client.download_media.assert_awaited_once_with("photo-id", in_memory=True)
        self.assertEqual(json.loads(self.bridge.profile_path.read_text())["id"], 42)

    async def test_afk_message_can_be_configured_before_enabling(self):
        self.bridge.connection = "connected"
        result = await self.bridge.update_settings({"afk": {"enabled": False, "message": "Torno fra poco."}})
        self.assertFalse(result["afk"]["enabled"])
        self.assertEqual(result["afk"]["message"], "Torno fra poco.")
        await self.bridge.update_settings({"afk": {"enabled": True}})
        self.assertTrue(runtime.afk.active)
        self.assertEqual(runtime.afk.message, "Torno fra poco.")

    async def test_snapshot_does_not_expose_credentials_or_session(self):
        snapshot = self.bridge.snapshot()
        self.assertNotIn("api_hash", json.dumps(snapshot))
        self.assertNotIn("api_id", json.dumps(snapshot))
        self.assertNotIn("command_users", snapshot["settings"])
        self.assertFalse(snapshot["afk"]["enabled"])

    async def test_protocol_rejects_arbitrary_operations(self):
        with self.assertRaises(ValueError):
            await self.bridge.dispatch("eval", {"code": "anything"})

    async def test_authorized_session_starts_runtime_without_terminal_prompts(self):
        client = SimpleNamespace(connect=AsyncMock(return_value=True), disconnect=AsyncMock(), is_connected=True)
        with patch("pyrogram.Client", return_value=client), \
             patch("MelixsaUI.backend.bridge.config_tools.load_credentials", return_value=(123, "a" * 32)), \
             patch("MelixsaUI.backend.bridge.console_tools.setup"), \
             patch.object(self.bridge, "run_runtime", new=AsyncMock()) as run:
            result = await self.bridge.connect()
            await self.bridge.task
        self.assertEqual(result["connection"], "connecting")
        client.disconnect.assert_awaited_once()
        run.assert_awaited_once()
        self.assertIsNone(self.bridge.login_lock)

    async def test_code_challenge_continues_with_two_factor_password(self):
        from pyrogram.errors import SessionPasswordNeeded
        client = SimpleNamespace(sign_in=AsyncMock(side_effect=SessionPasswordNeeded()), check_password=AsyncMock(), is_connected=False)
        self.bridge.login_client = client
        self.bridge.connection = "login_code"
        self.bridge.phone, self.bridge.phone_code_hash = "+39000000000", "hash"
        result = await self.bridge.login_code({"code": "12345"})
        self.assertEqual(result["connection"], "login_password")
        with patch.object(self.bridge, "start_runtime", new=AsyncMock()) as start:
            await self.bridge.login_password({"password": "test-password"})
        client.check_password.assert_awaited_once_with("test-password")
        start.assert_awaited_once()


class ProtocolTests(unittest.TestCase):
    def test_stdout_contains_only_json_and_shutdown_is_graceful(self):
        root = Path(__file__).resolve().parents[1]
        commands = '\n'.join(json.dumps({"method": method}) for method in ("snapshot", "unknown", "shutdown")) + '\n'
        process = subprocess.run([sys.executable, "-u", str(root / "MelixsaUI/backend/bridge.py")],
                                 input=commands, text=True, capture_output=True, cwd=root, timeout=20)
        self.assertEqual(process.returncode, 0)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(responses), 3)
        self.assertEqual(responses[0]["result"]["connection"], "offline")
        self.assertIn("error", responses[1])
        self.assertEqual(responses[2]["result"]["connection"], "offline")


if __name__ == "__main__":
    unittest.main()
