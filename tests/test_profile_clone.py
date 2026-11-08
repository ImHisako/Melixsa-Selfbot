import json
from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pyrogram import enums, raw
from pyrogram.file_id import FileId, FileType, ThumbnailSource

from Cogs.core import profile_tools, runtime


def photo(media_id):
    return SimpleNamespace(big_file_id=FileId(
        file_type=FileType.PHOTO, dc_id=2, media_id=media_id, access_hash=123,
        thumbnail_source=ThumbnailSource.THUMBNAIL, thumbnail_file_type=FileType.PHOTO,
        thumbnail_size="x", volume_id=0, local_id=0,
    ).encode())


class ProfileCloneTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = root / "profile-backups" / "101.json"
        self.enterContext(patch.object(runtime, "DATA_DIR", root))
        self.enterContext(patch.object(runtime, "respond", new_callable=AsyncMock))
        self.owner = SimpleNamespace(id=101, first_name="Anna", last_name="Rossi", bio="Bio originale",
                                     photo=photo(301))
        self.target = SimpleNamespace(id=202, first_name="Luca", last_name=None, bio=None,
                                      photo=photo(302), public_photo=None)
        self.message = SimpleNamespace(
            chat=SimpleNamespace(id=101, type=enums.ChatType.PRIVATE),
            reply_to_message=SimpleNamespace(from_user=self.target),
        )
        self.upload = raw.types.InputFile(id=12, parts=1, name="profilo.jpg", md5_checksum="")
        self.cloned_photo = photo(303)
        self.client = SimpleNamespace(
            get_chat=AsyncMock(side_effect=lambda user: self.owner if user == "me" else self.target),
            get_users=AsyncMock(return_value=self.target),
            download_media=AsyncMock(side_effect=lambda file_id, **_: BytesIO(
                b"original" if file_id == self.owner.photo.big_file_id else b"target"
            )),
            save_file=AsyncMock(return_value=self.upload),
            update_profile=AsyncMock(return_value=True),
            invoke=AsyncMock(return_value=SimpleNamespace(photo=SimpleNamespace(id=303))),
            delete_profile_photos=AsyncMock(return_value=True),
        )

    async def run_command(self, command, argument=""):
        await runtime.handle_command(self.client, self.message, command, argument)

    async def test_clones_by_username_after_persisting_and_restores_original(self):
        async def update(**details):
            self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["photo"], "b3JpZ2luYWw=")
            self.assertEqual(details, {"first_name": "Luca", "last_name": "", "bio": ""})
            return True

        self.client.update_profile.side_effect = update
        await self.run_command("clone", "@luca")
        self.client.get_users.assert_awaited_once_with("@luca")
        query = self.client.invoke.call_args.args[0]
        self.assertIsInstance(query, raw.functions.photos.UploadProfilePhoto)
        self.assertEqual(query.file, self.upload)
        query.write()
        with self.assertRaisesRegex(ValueError, "già un backup"):
            await self.run_command("cloneprofile")
        self.client.update_profile.assert_awaited_once()

        original = self.owner.photo
        self.client.update_profile.side_effect = None
        self.owner.photo = self.cloned_photo

        def delete(_):
            self.owner.photo = original
            return True

        self.client.delete_profile_photos.side_effect = delete
        await self.run_command("restore")
        self.client.update_profile.assert_awaited_with(first_name="Anna", last_name="Rossi", bio="Bio originale")
        self.client.delete_profile_photos.assert_awaited_once_with(self.cloned_photo.big_file_id)
        self.assertFalse(self.path.exists())

    async def test_keeps_backup_after_upload_failure_and_restores_by_reply(self):
        self.client.invoke.side_effect = TimeoutError("Telegram timeout")
        with self.assertRaisesRegex(RuntimeError, "restoreprofile"):
            await self.run_command("cloneprofile")
        self.client.get_chat.assert_awaited_with(self.target.id)
        self.assertTrue(self.path.exists())
        await self.run_command("restoreprofile")
        self.client.delete_profile_photos.assert_not_awaited()
        self.assertFalse(self.path.exists())

    async def test_restore_removes_cloned_photo_when_owner_had_none(self):
        self.owner.photo = None
        self.client.download_media.side_effect = None
        self.client.download_media.return_value = BytesIO(b"target")
        await self.run_command("cloneprofile")
        self.owner.photo = self.cloned_photo
        self.client.delete_profile_photos.return_value = False
        with self.assertRaises(RuntimeError):
            await self.run_command("restoreprofile")
        self.assertTrue(self.path.exists())

        def delete(_):
            self.owner.photo = None
            return True

        self.client.delete_profile_photos.side_effect = delete
        await self.run_command("restoreprofile")
        self.assertFalse(self.path.exists())

    async def test_failed_backup_write_stops_before_profile_changes(self):
        with patch.object(profile_tools, "atomic_write", side_effect=OSError("disco pieno")):
            with self.assertRaises(OSError):
                await self.run_command("cloneprofile")
        self.client.update_profile.assert_not_awaited()
        self.client.invoke.assert_not_awaited()

    async def test_uses_local_photo_if_original_was_removed_from_telegram(self):
        await self.run_command("cloneprofile")
        self.owner.photo = None

        async def album(*_):
            yield photo(304)

        async def upload(*, photo):
            self.assertEqual(photo.photo.read(), b"original")
            return True

        self.client.get_chat_photos = album
        self.client.set_profile_photo = AsyncMock(side_effect=upload)
        await self.run_command("restoreprofile")
        self.client.set_profile_photo.assert_awaited_once()
        self.client.delete_profile_photos.assert_not_awaited()
        self.assertFalse(self.path.exists())

    def test_owner_commands_cannot_be_shared_by_name_or_alias(self):
        commands = {"clone", "cloneprofile", "restore", "restoreprofile"}
        with patch.object(runtime, "state", runtime.MonitorState(shared_commands=commands)):
            for command in commands:
                self.assertFalse(runtime.permitted_command(command, ""), command)
