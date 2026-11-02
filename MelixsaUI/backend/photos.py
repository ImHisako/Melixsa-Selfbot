"""Foto profilo Telegram in memoria, con download limitati e cache per identità."""
from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
from dataclasses import dataclass
import io
import time

from PIL import Image, ImageOps
from pyrogram.errors import FloodWait


MAX_PHOTOS = 512
MAX_BATCH = 60
MAX_SOURCE_BYTES = 2_000_000
PHOTO_TTL = 300
RETRY_DELAY = 60


@dataclass
class Photo:
    version: int
    known: bool = False
    unique_id: str | None = None
    small_id: str | None = None
    big_id: str | None = None
    data: str | None = None
    refresh_at: float = 0
    retry_at: float = 0


def image_data(stream, size=160):
    if not isinstance(stream, io.BytesIO) or not 0 < stream.getbuffer().nbytes <= MAX_SOURCE_BYTES:
        raise ValueError("Foto profilo non disponibile.")
    try:
        with Image.open(io.BytesIO(stream.getvalue())) as source:
            if source.width * source.height > 4_000_000:
                raise ValueError("Foto profilo non disponibile.")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((size, size))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("Foto profilo non disponibile.") from error


class ProfilePhotos:
    def __init__(self, bridge):
        self.bridge = bridge
        self.entries = OrderedDict()
        self.tasks = {}
        self.slots = asyncio.Semaphore(3)
        self.sequence = 0
        self.blocked_until = 0

    def _version(self):
        self.sequence += 1
        return self.sequence

    def _entry(self, target):
        if target not in self.entries:
            self.entries[target] = Photo(version=self._version())
        self.entries.move_to_end(target)
        while len(self.entries) > MAX_PHOTOS:
            evicted, _ = self.entries.popitem(last=False)
            task = self.tasks.get(evicted)
            if task is not None:
                task.cancel()
        return self.entries[target]

    def remember(self, entity):
        target = getattr(entity, "id", None)
        if type(target) is not int or not target:
            return
        entry = self._entry(target)
        # Some message/service objects contain only an ID, not profile information.
        if not hasattr(entity, "photo"):
            return
        photo = entity.photo
        small = getattr(photo, "small_file_id", None)
        big = getattr(photo, "big_file_id", None)
        small = small if isinstance(small, str) and small else None
        big = big if isinstance(big, str) and big else small
        unique = getattr(photo, "small_photo_unique_id", None) or small
        if not entry.known or entry.unique_id != unique:
            entry.data = None
            entry.version = self._version()
            entry.retry_at = 0
            task = self.tasks.get(target)
            if task is not None and task is not asyncio.current_task():
                task.cancel()
        entry.known = True
        entry.unique_id = unique
        entry.small_id = small
        entry.big_id = big
        entry.refresh_at = time.monotonic() + PHOTO_TTL

    def _connected(self, client):
        return self.bridge.connection == "connected" and self.bridge.client is client

    def schedule(self, target):
        entry = self._entry(target)
        task = self.tasks.get(target)
        now = time.monotonic()
        if (task is not None and not task.done()) or now < max(entry.retry_at, self.blocked_until):
            return
        if entry.known and now < entry.refresh_at and (entry.data is not None or not entry.small_id):
            return
        client = self.bridge.client
        task = asyncio.create_task(self._refresh(target, entry, client))
        self.tasks[target] = task

        def finished(done):
            if self.tasks.get(target) is done:
                self.tasks.pop(target, None)
        task.add_done_callback(finished)

    async def _lookup(self, client, target):
        entity = await client.get_chat(target)
        if getattr(entity, "id", None) != target:
            raise ValueError("Foto profilo non disponibile.")
        self.remember(entity)

    async def _download(self, client, target, entry):
        if not entry.known or time.monotonic() >= entry.refresh_at:
            await self._lookup(client, target)
        if not entry.small_id:
            return
        version = entry.version
        stream = await client.download_media(entry.small_id, in_memory=True)
        data = await asyncio.to_thread(image_data, stream)
        if self._connected(client) and self.entries.get(target) is entry and entry.version == version:
            entry.data = data
            entry.version = self._version()
            entry.retry_at = 0

    async def _refresh(self, target, entry, client):
        try:
            async with self.slots:
                if not self._connected(client) or self.entries.get(target) is not entry or time.monotonic() < self.blocked_until:
                    return
                await asyncio.wait_for(self._download(client, target, entry), timeout=10)
        except FloodWait as error:
            self.blocked_until = time.monotonic() + max(RETRY_DELAY, error.value)
            entry.retry_at = self.blocked_until
        except Exception:
            # A private/deleted photo or a failed download must never break messages.
            entry.retry_at = time.monotonic() + RETRY_DELAY

    def snapshot(self, targets, known):
        changed = {}
        for target in targets:
            self.schedule(target)
            entry = self.entries[target]
            if known.get(str(target)) != entry.version:
                changed[str(target)] = {"photo": entry.data, "version": entry.version}
        return {"photos": changed, "pending": any(
            target in self.tasks and not self.tasks[target].done() for target in targets
        )}

    async def preview(self, target):
        client = self.bridge.client
        if time.monotonic() < self.blocked_until:
            raise ValueError("Foto profilo non disponibile. Riprova tra poco.")

        async def load():
            async with self.slots:
                await self._lookup(client, target)
                entry = self.entries[target]
                if not entry.big_id:
                    return None
                stream = await client.download_media(entry.big_id, in_memory=True)
                return await asyncio.to_thread(image_data, stream, 1024)
        try:
            return {"photo": await asyncio.wait_for(load(), timeout=15)}
        except asyncio.TimeoutError:
            raise ValueError("Caricamento della foto scaduto. Riprova.") from None
        except FloodWait as error:
            self.blocked_until = time.monotonic() + max(RETRY_DELAY, error.value)
            raise

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        self.entries.clear()
        self.blocked_until = 0
