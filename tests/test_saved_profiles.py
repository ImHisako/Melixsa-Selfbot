from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image
from pyrogram import enums

from Cogs.core import profile_tools, runtime
from Cogs.core.saved_profiles import SavedProfiles
from MelixsaUI.backend.bridge import DesktopBridge


class SavedProfilesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(runtime, "DATA_DIR", root))
        self.enterContext(patch.object(runtime, "respond", new_callable=AsyncMock))
        self.enterContext(patch.object(profile_tools, "photo_id", side_effect=lambda photo: photo.id if photo else None))
        self.store = SavedProfiles(root)
        self.photo = SimpleNamespace(id=17, big_file_id="full-photo")
        self.owner = SimpleNamespace(id=41, first_name="Anna", last_name="Rossi", bio="La mia bio", photo=self.photo)
        self.message = SimpleNamespace(chat=SimpleNamespace(id=41, type=enums.ChatType.PRIVATE))
        with BytesIO() as buffer:
            Image.new("RGB", (24, 24), "purple").save(buffer, "JPEG")
            self.image = buffer.getvalue()
        self.client = SimpleNamespace(
            get_chat=AsyncMock(return_value=self.owner),
            download_media=AsyncMock(side_effect=lambda *_args, **_kwargs: BytesIO(self.image)),
            update_profile=AsyncMock(return_value=True),
            set_profile_photo=AsyncMock(return_value=True),
        )

    async def test_chat_save_is_previewable_in_desktop_and_isolated_by_account(self):
        await runtime.handle_command(self.client, self.message, "saveprofile", "Profilo Caffè")
        self.owner.first_name = "Giulia"
        with self.assertRaisesRegex(ValueError, "già un profilo"):
            await runtime.handle_command(self.client, self.message, "saveprofile", "PROFILO CAFFE\u0300")

        bridge = DesktopBridge()
        self.addAsyncCleanup(bridge.close)
        bridge.profile = {"id": 42}
        self.assertEqual(await bridge.dispatch("saved_profiles", {}), [])
        with self.assertRaisesRegex(ValueError, "inesistente"):
            await bridge.dispatch("saved_profile_preview", {"name": "Profilo Caffè"})

        bridge.profile = {"id": 41}
        self.assertEqual(await bridge.dispatch("saved_profiles", {}), ["Profilo Caffè"])
        preview = await bridge.dispatch("saved_profile_preview", {"name": "profilo caffè"})
        self.assertEqual((preview["first_name"], preview["last_name"], preview["bio"]), ("Anna", "Rossi", "La mia bio"))
        self.assertTrue(preview["photo"].startswith("data:image/jpeg;base64,"))
        with self.assertRaisesRegex(ValueError, "Collega Telegram"):
            await bridge.dispatch("load_profile", {"name": "Profilo Caffè"})

    async def test_desktop_load_applies_existing_photo_and_refreshes_account(self):
        bridge = DesktopBridge()
        self.addAsyncCleanup(bridge.close)
        bridge.connection = "connected"
        bridge.client = self.client
        self.assertEqual(await bridge.dispatch("save_profile", {"name": "Lavoro"}), {"name": "Lavoro"})
        self.owner.photo = SimpleNamespace(id=19)
        self.owner.bio = "Altra bio"

        async def album(_):
            yield self.photo

        self.client.get_chat_photos = album
        with patch.object(bridge, "refresh_profile", new_callable=AsyncMock, return_value={"updated": True}) as refresh:
            self.assertEqual(await bridge.dispatch("load_profile", {"name": "lavoro"}), {"updated": True})
            refresh.assert_awaited_once()
        self.client.update_profile.assert_awaited_once_with(first_name="Anna", last_name="Rossi", bio="La mia bio")
        self.assertEqual(self.client.set_profile_photo.call_args.kwargs["photo"].chat_photo_file_id, "full-photo")

    async def test_uploads_missing_photo_from_disk_once_and_reuses_its_new_id(self):
        await self.store.save(self.client, "Originale")
        self.owner.photo = None

        async def upload(stream):
            self.assertEqual(stream.read(), self.image)
            return object()

        async def album(_):
            yield SimpleNamespace(id=18)

        self.client.get_chat_photos = album
        self.client.save_file = AsyncMock(side_effect=upload)
        self.client.invoke = AsyncMock(return_value=SimpleNamespace(photo=SimpleNamespace(id=21)))
        await runtime.handle_command(self.client, self.message, "loadprofile", "originale")
        self.owner.photo = SimpleNamespace(id=21)
        await runtime.handle_command(self.client, self.message, "loadprofile", "originale")
        self.client.invoke.assert_awaited_once()
        self.client.set_profile_photo.assert_not_awaited()

    async def test_no_photo_load_applies_name_and_bio_without_photo_operations(self):
        self.owner.photo = None
        self.owner.bio = None
        await self.store.save(self.client, "Solo testo")
        self.owner.photo = self.photo
        self.owner.bio = "Nuova bio"
        await runtime.handle_command(self.client, self.message, "loadprofile", "Solo testo")
        self.client.update_profile.assert_awaited_once_with(first_name="Anna", last_name="Rossi", bio="")
        self.client.set_profile_photo.assert_not_awaited()

    def test_commands_remain_owner_only(self):
        state = runtime.MonitorState(shared_commands={"saveprofile", "loadprofile"})
        with patch.object(runtime, "state", state):
            self.assertFalse(runtime.permitted_command("saveprofile", "copia"))
            self.assertFalse(runtime.permitted_command("loadprofile", "copia"))
