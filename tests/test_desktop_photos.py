import asyncio
import base64
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image
from pyrogram import enums
from pyrogram.errors import FloodWait

from MelixsaUI.backend.chats import ChatService
from MelixsaUI.backend.photos import MAX_SOURCE_BYTES, image_data


def picture(color="purple", size=(320, 240)):
    stream = io.BytesIO()
    Image.new("RGB", size, color=color).save(stream, format="PNG")
    return stream


def profile(target=7, token="one", kind=enums.ChatType.PRIVATE):
    return SimpleNamespace(id=target, first_name="Anna", last_name="Rossi", title=None, type=kind,
                           photo=SimpleNamespace(small_file_id=f"small-{token}", big_file_id=f"big-{token}",
                                                 small_photo_unique_id=token) if token else None)


class PhotoImageTests(unittest.TestCase):
    def test_image_is_normalized_to_a_bounded_jpeg_data_url(self):
        data = image_data(picture(size=(800, 400)))
        self.assertTrue(data.startswith("data:image/jpeg;base64,"))
        with Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))) as image:
            self.assertEqual(image.size, (160, 80))
            self.assertEqual(image.format, "JPEG")

    def test_bad_oversized_and_large_dimension_sources_are_rejected(self):
        for stream in (None, "file.jpg", io.BytesIO(), io.BytesIO(b"not an image"),
                       io.BytesIO(b"x" * (MAX_SOURCE_BYTES + 1)), picture(size=(4001, 1001))):
            with self.subTest(type=type(stream).__name__), self.assertRaises(ValueError):
                image_data(stream)


class DesktopPhotoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = SimpleNamespace(get_chat=AsyncMock(return_value=profile()),
                                      download_media=AsyncMock(side_effect=lambda *args, **kwargs: picture()))
        self.bridge = SimpleNamespace(connection="connected", client=self.client)
        self.service = ChatService(self.bridge)
        self.photos = self.service.photos
        self.addAsyncCleanup(self.service.close)

    async def drain(self):
        await asyncio.gather(*list(self.photos.tasks.values()))

    async def test_photos_load_in_background_for_people_groups_bots_and_channels(self):
        for target, kind in ((7, enums.ChatType.PRIVATE), (8, enums.ChatType.BOT),
                             (-1001, enums.ChatType.SUPERGROUP), (-1002, enums.ChatType.CHANNEL)):
            self.photos.remember(profile(target, str(target), kind))
        first = await self.service.profile_photos({"ids": ["7", "8", "-1001", "-1002"]})
        self.assertTrue(first["pending"])
        self.assertTrue(all(item["photo"] is None for item in first["photos"].values()))
        self.client.download_media.assert_not_awaited()
        await self.drain()
        result = await self.service.profile_photos({"ids": ["7", "8", "-1001", "-1002"]})
        self.assertFalse(result["pending"])
        self.assertTrue(all(item["photo"].startswith("data:image/jpeg;base64,") for item in result["photos"].values()))
        self.assertEqual(self.client.download_media.await_count, 4)
        self.client.get_chat.assert_not_awaited()
        known = {key: item["version"] for key, item in result["photos"].items()}
        cached = await self.service.profile_photos({"ids": list(known), "known": known})
        self.assertEqual(cached, {"photos": {}, "pending": False})
        self.assertEqual(self.client.download_media.await_count, 4)
        self.assertNotIn("small-", json.dumps(result))

    async def test_missing_photos_do_not_download_and_are_refreshed_after_ttl(self):
        self.photos.remember(profile(token=None))
        first = await self.service.profile_photos({"ids": ["7"]})
        self.assertFalse(first["pending"])
        self.assertIsNone(first["photos"]["7"]["photo"])
        self.client.download_media.assert_not_awaited()
        self.photos.entries[7].refresh_at = 0
        await self.service.profile_photos({"ids": ["7"]})
        await self.drain()
        self.client.get_chat.assert_awaited_once_with(7)
        self.assertIsNotNone(self.photos.entries[7].data)

    async def test_photo_changes_and_removals_invalidate_the_previous_image(self):
        self.photos.remember(profile())
        await self.service.profile_photos({"ids": ["7"]})
        await self.drain()
        old_version = self.photos.entries[7].version
        self.photos.remember(profile(token="two"))
        changed = await self.service.profile_photos({"ids": ["7"], "known": {"7": old_version}})
        self.assertIsNone(changed["photos"]["7"]["photo"])
        self.assertGreater(changed["photos"]["7"]["version"], old_version)
        await self.drain()
        self.client.download_media.assert_awaited_with("small-two", in_memory=True)
        self.photos.remember(profile(token=None))
        removed = await self.service.profile_photos({"ids": ["7"]})
        self.assertIsNone(removed["photos"]["7"]["photo"])
        self.assertFalse(removed["pending"])

    async def test_replaced_inflight_photo_cannot_restore_an_old_avatar(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def download(file_id, **kwargs):
            if file_id == "small-one":
                started.set()
                await release.wait()
            return picture("red" if file_id == "small-one" else "blue")
        self.client.download_media.side_effect = download
        self.photos.remember(profile())
        await self.service.profile_photos({"ids": ["7"]})
        await asyncio.wait_for(started.wait(), 1)
        old_tasks = list(self.photos.tasks.values())
        self.photos.remember(profile(token="two"))
        release.set()
        await asyncio.gather(*old_tasks, return_exceptions=True)
        await self.service.profile_photos({"ids": ["7"]})
        await self.drain()
        self.assertEqual(self.photos.entries[7].data, image_data(picture("blue")))

    async def test_download_failure_and_bad_images_use_backoff_without_breaking_chats(self):
        self.photos.remember(profile())
        self.client.download_media.return_value = io.BytesIO(b"bad image")
        self.client.download_media.side_effect = None
        await self.service.profile_photos({"ids": ["7"]})
        await self.drain()
        for _ in range(3):
            result = await self.service.profile_photos({"ids": ["7"]})
            self.assertFalse(result["pending"])
            self.assertIsNone(result["photos"]["7"]["photo"])
        self.assertEqual(self.client.download_media.await_count, 1)

    async def test_unknown_users_resolve_once_and_reject_mismatched_profiles(self):
        await self.service.profile_photos({"ids": ["7"]})
        await self.drain()
        self.client.get_chat.assert_awaited_once_with(7)
        self.client.get_chat.return_value = profile(123)
        await self.service.profile_photos({"ids": ["8"]})
        await self.drain()
        self.assertIsNone(self.photos.entries[8].data)
        self.assertNotIn(123, self.photos.entries)

    async def test_preview_downloads_the_large_photo_and_handles_removed_photos(self):
        self.client.download_media.side_effect = lambda *args, **kwargs: picture(size=(1500, 1000))
        result = await self.service.profile_photo({"chat_id": "7"})
        self.client.download_media.assert_awaited_once_with("big-one", in_memory=True)
        with Image.open(io.BytesIO(base64.b64decode(result["photo"].split(",", 1)[1]))) as image:
            self.assertEqual(image.size, (1024, 683))
        self.client.get_chat.return_value = profile(token=None)
        self.assertEqual(await self.service.profile_photo({"chat_id": "7"}), {"photo": None})

    async def test_parallel_downloads_are_limited_to_three(self):
        ready = asyncio.Event()
        release = asyncio.Event()
        active = 0
        peak = 0

        async def download(*args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 3:
                ready.set()
            await release.wait()
            active -= 1
            return picture()
        self.client.download_media.side_effect = download
        for target in range(1, 8):
            self.photos.remember(profile(target, str(target)))
        await self.service.profile_photos({"ids": [str(target) for target in range(1, 8)]})
        await asyncio.wait_for(ready.wait(), 1)
        self.assertEqual(active, 3)
        release.set()
        await self.drain()
        self.assertEqual(peak, 3)

    async def test_floodwait_pauses_new_photo_downloads(self):
        self.photos.remember(profile())
        self.client.download_media.side_effect = FloodWait(120)
        await self.service.profile_photos({"ids": ["7"]})
        await self.drain()
        self.photos.remember(profile(8, "two"))
        result = await self.service.profile_photos({"ids": ["8"]})
        self.assertFalse(result["pending"])
        self.assertEqual(self.client.download_media.await_count, 1)

    async def test_disconnect_cancels_pending_downloads_and_clears_images(self):
        started = asyncio.Event()

        async def download(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        self.client.download_media.side_effect = download
        self.photos.remember(profile())
        await self.service.profile_photos({"ids": ["7"]})
        await asyncio.wait_for(started.wait(), 1)
        tasks = list(self.photos.tasks.values())
        await self.service.close()
        self.assertTrue(all(task.done() for task in tasks))
        self.assertEqual(self.photos.entries, {})
        self.assertEqual(self.photos.tasks, {})

    async def test_thumbnail_cache_has_a_fixed_size_and_eviction_changes_versions(self):
        with patch("MelixsaUI.backend.photos.MAX_PHOTOS", 2):
            self.photos.remember(profile(1))
            original_version = self.photos.entries[1].version
            self.photos.remember(profile(2))
            self.photos.remember(profile(3))
            self.assertEqual(list(self.photos.entries), [2, 3])
            self.photos.remember(profile(1))
            self.assertGreater(self.photos.entries[1].version, original_version)
            self.assertEqual(len(self.photos.entries), 2)

    async def test_dialog_refresh_keeps_thumbnails_and_records_chat_photos(self):
        async def dialogs(from_archive):
            if not from_archive:
                yield SimpleNamespace(chat=profile())
        self.client.get_dialogs = Mock(side_effect=dialogs)
        await self.service.list_dialogs({})
        await self.service.profile_photos({"ids": ["7"]})
        await self.drain()
        version = self.photos.entries[7].version
        await self.service.list_dialogs({})
        self.assertEqual(self.photos.entries[7].version, version)
        self.assertIsNotNone(self.photos.entries[7].data)
        self.assertEqual(self.client.download_media.await_count, 1)

    async def test_history_records_both_user_and_sender_chat_profile_photos(self):
        async def history(*args, **kwargs):
            yield SimpleNamespace(id=2, from_user=profile(7))
            yield SimpleNamespace(id=1, sender_chat=profile(-1001, kind=enums.ChatType.CHANNEL))
        self.client.get_chat_history = history
        await self.service.history({"chat_id": "-1002"})
        self.assertEqual(set(self.photos.entries), {7, -1001})
        self.assertTrue(all(entry.known for entry in self.photos.entries.values()))

    async def test_invalid_batches_and_versions_never_reach_telegram(self):
        for params in ({}, {"ids": "7"}, {"ids": [True]}, {"ids": ["7"] * 61},
                       {"ids": ["7"], "known": {"7": True}}, {"ids": ["7"], "known": {"8": 1}},
                       {"ids": ["7"], "known": []}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                await self.service.profile_photos(params)
        self.client.get_chat.assert_not_awaited()
        self.client.download_media.assert_not_awaited()
        self.assertEqual(await self.service.profile_photos({"ids": []}), {"photos": {}, "pending": False})


if __name__ == "__main__":
    unittest.main()
