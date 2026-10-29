"""Controlli desktop per il monitoraggio dei gruppi e lettura limitata dei log."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from Cogs.core import runtime
from Cogs.core.instance_tools import InstanceLock


LOG_NAME = re.compile(r"group_(-[1-9][0-9]*)\.txt(?:\.([0-9]+))?\Z")
MAX_READ_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 100


def group_id(value) -> int:
    if type(value) is int:
        result = value
    elif isinstance(value, str) and re.fullmatch(r"-[1-9][0-9]{0,18}", value):
        result = int(value)
    else:
        raise ValueError("Inserisci un ID gruppo negativo valido, per esempio -1001234567890.")
    if not -(2**63) < result < 0:
        raise ValueError("ID gruppo non valido.")
    return result


def text(value, limit=256):
    return value[:limit] if isinstance(value, str) else ""


def log_files(directory: Path, *, pattern=LOG_NAME, parse_id=group_id):
    """Only recognised regular log files inside the configured log directory."""
    result = {}
    if not directory.exists():
        return result
    root = directory.resolve()
    for path in directory.iterdir():
        match = pattern.fullmatch(path.name)
        if not match or path.is_symlink() or path.resolve().parent != root or not path.is_file():
            continue
        try:
            stat = path.stat()
            chat_id = parse_id(match[1])
        except (OSError, ValueError):
            continue
        # Current log first, then closed archives in descending rotation order.
        order = (1, 0) if match[2] is None else (0, int(match[2]))
        result.setdefault(chat_id, []).append((order, path, stat))
    for files in result.values():
        files.sort(key=lambda item: item[0], reverse=True)
    return result


def read_records(files, target_id, *, identity_field="chat_id", limit=MAX_RECORDS, budget=MAX_READ_BYTES):
    """Read newest records first, including rotations, without loading entire files."""
    records = []
    skipped = 0
    remaining = budget
    limited = False
    for file_index, (_, path, _) in enumerate(files):
        try:
            with path.open("rb") as source:
                position = source.seek(0, 2)
                remainder = b""
                while position > 0 and remaining > 0 and len(records) < limit:
                    length = min(32768, position, remaining)
                    position -= length
                    source.seek(position)
                    chunk = source.read(length)
                    remaining -= length
                    lines = (chunk + remainder).split(b"\n")
                    remainder = lines.pop(0) if position else b""
                    for line in reversed(lines):
                        if not line.strip():
                            continue
                        try:
                            raw = json.loads(line)
                            if (not isinstance(raw, dict) or type(raw.get(identity_field)) is not int
                                    or raw[identity_field] != target_id):
                                raise ValueError("Invalid monitoring record")
                        except (ValueError, UnicodeError):
                            skipped += 1
                            continue
                        records.append({
                            "event": "edited" if raw.get("event") == "edited" else "new",
                            "date": text(raw.get("edit_date") or raw.get("date"), 64),
                            "message_id": str(raw["message_id"]) if type(raw.get("message_id")) is int else "",
                            "sender": text(raw.get("name") or raw.get("sender_chat_title") or raw.get("username")) or "Utente senza nome",
                            "username": text(raw.get("username"), 64),
                            "text": text(raw.get("text"), 8000),
                            "media": text(raw.get("media"), 64),
                            "chat_title": text(raw.get("chat_name") or raw.get("chat_title")),
                            "chat_id": str(raw["chat_id"]) if type(raw.get("chat_id")) is int else "",
                        })
                        if len(records) == limit:
                            limited = position > 0 or len(lines) > 1 or file_index < len(files) - 1
                            break
                if position > 0 and remaining == 0:
                    limited = True
        except FileNotFoundError:
            # Rotation can replace the file between listing it and opening it.
            continue
        if len(records) == limit or remaining == 0:
            break
    return {"records": records, "limited": limited, "skipped": skipped}


class SurveillanceService:
    def __init__(self, bridge):
        self.bridge = bridge
        self.metadata = {}
        self.log_labels = {}

    @property
    def connected(self):
        return self.bridge.connection == "connected" and self.bridge.client is not None

    def remember(self, chat):
        self.metadata[chat.id] = {
            "title": text(chat.title) or f"Gruppo {chat.id}",
            "username": text(chat.username, 64),
        }

    async def active_ids(self):
        if self.bridge.connection not in {"connected", "connecting"}:
            runtime.state = runtime.MonitorState.load()
        async with runtime.state_lock:
            return set(runtime.state.surveillance)

    async def overview(self):
        active = await self.active_ids()
        return await asyncio.to_thread(self._overview, active)

    def _overview(self, active):
        files = log_files(runtime.LOG_DIR)
        ids = active | set(files) | set(self.metadata)
        groups = []
        for chat_id in ids:
            logs = files.get(chat_id, [])
            last_update = max((item[2].st_mtime for item in logs), default=0)
            if logs and self.log_labels.get(chat_id, (None, ""))[0] != last_update:
                latest = read_records(logs, chat_id, limit=1, budget=65536)["records"]
                self.log_labels[chat_id] = (last_update, latest[0]["chat_title"] if latest else "")
            metadata = self.metadata.get(chat_id, {})
            title = metadata.get("title") or self.log_labels.get(chat_id, (None, ""))[1] or f"Gruppo {chat_id}"
            groups.append({
                "id": str(chat_id), "title": title, "username": metadata.get("username", ""),
                "enabled": chat_id in active,
                "log_bytes": sum(item[2].st_size for item in logs), "log_files": len(logs),
                "last_update": datetime.fromtimestamp(last_update, timezone.utc).isoformat() if last_update else None,
            })
        groups.sort(key=lambda item: (not item["enabled"], item["title"].casefold(), item["id"]))
        return {"groups": groups, "active_count": len(active), "log_bytes": sum(item["log_bytes"] for item in groups)}

    async def chats(self):
        if not self.connected:
            raise ValueError("Collega Telegram per caricare i tuoi gruppi.")
        groups = []

        async def collect():
            async for dialog in self.bridge.client.get_dialogs(limit=200):
                chat = dialog.chat
                if chat.type in {runtime.enums.ChatType.GROUP, runtime.enums.ChatType.SUPERGROUP}:
                    self.remember(chat)
                    groups.append({"id": str(chat.id), **self.metadata[chat.id]})

        await asyncio.wait_for(collect(), timeout=40)
        groups.sort(key=lambda item: item["title"].casefold())
        return {"chats": groups, "dialog_limit": 200}

    async def set_enabled(self, params):
        enabled = params.get("enabled")
        if type(enabled) is not bool:
            raise ValueError("Indica se attivare o fermare il monitoraggio.")
        query = params.get("chat")
        if enabled:
            if not self.connected:
                raise ValueError("Collega Telegram per attivare Surveillance.")
            if isinstance(query, str) and re.fullmatch(r"@[A-Za-z0-9_]{1,32}", query.strip()):
                target = query.strip()
            else:
                target = group_id(query)
            chat = await asyncio.wait_for(self.bridge.client.get_chat(target), timeout=15)
            if chat.type not in {runtime.enums.ChatType.GROUP, runtime.enums.ChatType.SUPERGROUP}:
                raise ValueError("Surveillance è disponibile soltanto per gruppi e supergruppi.")
            member = await asyncio.wait_for(self.bridge.client.get_chat_member(chat.id, "me"), timeout=15)
            if (member.status in {runtime.enums.ChatMemberStatus.LEFT, runtime.enums.ChatMemberStatus.BANNED}
                    or (member.status == runtime.enums.ChatMemberStatus.RESTRICTED and not getattr(member, "is_member", False))):
                raise ValueError("Il tuo account deve essere membro del gruppo da monitorare.")
            chat_id = group_id(chat.id)
            self.remember(chat)
        else:
            chat_id = group_id(query)

        async def save():
            async with runtime.state_transaction():
                if enabled:
                    runtime.state.surveillance.add(chat_id)
                else:
                    runtime.state.surveillance.discard(chat_id)

        if self.bridge.connection == "connected":
            await save()
        elif self.bridge.connection in {"connecting", "login_phone", "login_code", "login_password"}:
            raise ValueError("Completa o annulla il collegamento prima di modificare Surveillance.")
        else:
            with InstanceLock(runtime.DATA_DIR / "runtime.lock"):
                runtime.state = runtime.MonitorState.load()
                await save()
        action = "attivato" if enabled else "fermato"
        self.bridge.record(f"Monitoraggio del gruppo {chat_id} {action}.", "Surveillance")
        return {**await self.overview(), "changed_id": str(chat_id)}

    async def logs(self, params):
        chat_id = group_id(params.get("chat_id"))
        active = await self.active_ids()
        return await asyncio.to_thread(self._logs, chat_id, active)

    def _logs(self, chat_id, active):
        files = log_files(runtime.LOG_DIR)
        if chat_id not in active and chat_id not in files and chat_id not in self.metadata:
            raise ValueError("Questo gruppo non è presente in Surveillance.")
        result = read_records(files.get(chat_id, []), chat_id)
        return {"chat_id": str(chat_id), "limit": MAX_RECORDS, **result}
