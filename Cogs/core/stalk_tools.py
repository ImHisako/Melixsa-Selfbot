"""Profile and presence events for users explicitly enabled in Stalk."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import struct

from pyrogram import enums, raw
from pyrogram.file_id import FileId


PROFILE_EVENTS = frozenset({"name_changed", "username_changed", "photo_changed", "online", "offline"})
FIELDS = {"name": "name_changed", "username": "username_changed", "photo_id": "photo_changed"}


def photo_id(photo):
    if photo is None or isinstance(photo, raw.types.UserProfilePhotoEmpty):
        return None
    if isinstance(photo, raw.types.UserProfilePhoto):
        return str(photo.photo_id)
    try:
        return str(FileId.decode(photo.small_file_id).media_id)
    except (AttributeError, ValueError, TypeError, IndexError, struct.error):
        return getattr(photo, "small_photo_unique_id", None) or getattr(photo, "small_file_id", None)


def presence(status):
    if isinstance(status, raw.types.UserStatusOnline) or status is enums.UserStatus.ONLINE:
        return "online"
    if isinstance(status, raw.types.UserStatusOffline) or status is enums.UserStatus.OFFLINE:
        return "offline"
    # Approximate/hidden last seen is not an offline transition.
    return "unknown"


def primary_username(user):
    username = getattr(user, "username", None)
    if username:
        return username
    active = [item for item in (getattr(user, "usernames", None) or []) if getattr(item, "active", False)]
    return next((item.username for item in active if getattr(item, "editable", False)),
                active[0].username if active else "")


def snapshot(user):
    return {
        "name": " ".join(filter(None, (getattr(user, "first_name", None), getattr(user, "last_name", None)))),
        "username": primary_username(user),
        "photo_id": photo_id(getattr(user, "photo", None)),
        "status": presence(getattr(user, "status", None)),
    }


class StalkMonitor:
    def __init__(self, targets, submit, *, interval=30):
        self.targets = targets
        self.submit = submit
        self.interval = interval
        self.profiles = {}
        self.revisions = {}
        self.lock = asyncio.Lock()
        self.slots = asyncio.Semaphore(3)
        self.task = None
        self.own_id = None

    def forget(self, target):
        self.profiles.pop(target, None)
        self.revisions[target] = self.revisions.get(target, 0) + 1

    def seed(self, user):
        """Establish a baseline when monitoring starts, without inventing changes."""
        if user.id in self.targets() and user.id != self.own_id and not getattr(user, "is_self", False):
            self.profiles[user.id] = snapshot(user)
            self.revisions[user.id] = self.revisions.get(user.id, 0) + 1

    async def observe(self, target, values, *, explicit=False, source="telegram"):
        async with self.lock:
            if target not in self.targets() or target == self.own_id:
                if target in self.profiles:
                    self.forget(target)
                return
            before = self.profiles.get(target, {})
            after = {**before, **values}
            changes = []
            for field, event in FIELDS.items():
                if field in values and field in before and before[field] != values[field]:
                    changes.append((event, before.get(field), values[field]))
            status = values.get("status")
            if status in {"online", "offline"} and status != before.get("status") and ("status" in before or explicit):
                changes.append((status, before.get("status"), status))
            self.profiles[target] = after
            self.revisions[target] = self.revisions.get(target, 0) + 1
            version = self.revisions[target]
            for event, old, new in changes:
                if target not in self.targets() or version != self.revisions.get(target):
                    break
                await self.submit(target, {
                    "event": event, "date": datetime.now(timezone.utc).isoformat(),
                    "user_id": target, "name": after.get("name", ""), "username": after.get("username", ""),
                    "old_value": old, "new_value": new, "source": source,
                    "text": "", "chat_id": None, "message_id": None,
                })

    async def observe_user(self, user, *, source="telegram"):
        if (getattr(user, "is_self", False) or getattr(user, "is_deleted", False)
                or getattr(user, "deleted", False) or getattr(user, "is_min", False) or getattr(user, "min", False)):
            return
        await self.observe(user.id, snapshot(user), source=source)

    async def handle_update(self, update, users):
        if isinstance(update, raw.types.UpdateUserName):
            await self.observe(update.user_id, {
                "name": " ".join(filter(None, (update.first_name, update.last_name))),
                "username": primary_username(update),
            }, explicit=True)
        elif isinstance(update, raw.types.UpdateUserStatus):
            await self.observe(update.user_id, {"status": presence(update.status)}, explicit=True)
        else:
            # Modern photo updates arrive as updated User objects, including UpdateUser bundles.
            for target in self.targets() & users.keys():
                user = users[target]
                if isinstance(user, raw.types.User) and not user.is_self:
                    await self.observe_user(user)

    async def refresh(self, client, target):
        async with self.slots:
            if target not in self.targets() or target == self.own_id:
                return
            version = self.revisions.get(target, 0)
            try:
                user = await asyncio.wait_for(client.get_users(target), timeout=10)
                # A pushed update received during this request is newer than its snapshot.
                if user.id == target and version == self.revisions.get(target, 0):
                    await self.observe_user(user, source="poll")
            except Exception:
                # Private/unavailable profiles and Telegram errors do not stop other users.
                pass

    async def _run(self, client):
        while True:
            targets = set(self.targets())
            for target in set(self.profiles) - targets:
                self.forget(target)
            await asyncio.gather(*(self.refresh(client, target) for target in sorted(targets)))
            await asyncio.sleep(self.interval)

    def start(self, client, *, own_id=None):
        if self.task is None or self.task.done():
            self.own_id = own_id
            self.profiles.clear()
            self.revisions.clear()
            self.task = asyncio.create_task(self._run(client), name="melixsa-stalk-profiles")

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.profiles.clear()
        self.revisions.clear()
