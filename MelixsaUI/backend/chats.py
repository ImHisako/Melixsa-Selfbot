"""Lettura delle conversazioni Telegram e invio esplicito dal composer desktop."""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path
import re
from string import ascii_lowercase, ascii_uppercase

from pyrogram import enums

from MelixsaUI.backend.photos import MAX_BATCH, ProfilePhotos


STYLES = json.loads((Path(__file__).resolve().parents[1] / "src/catalog/text-styles.json").read_text(encoding="utf-8"))
STYLE_MAP = {style["id"]: style for style in STYLES}
LETTERS = ascii_lowercase + ascii_uppercase
DIALOG_PAGE = 60
HISTORY_PAGE = 50
MAX_MESSAGE_UNITS = 4096


def transform_text(value: str, style_id: str = "plain") -> str:
    if not isinstance(style_id, str) or style_id not in STYLE_MAP:
        raise ValueError("Stile del testo non valido.")
    style = STYLE_MAP[style_id]
    alphabet = dict(zip(LETTERS, style.get("lower", "") + style.get("upper", "")))
    suffix = style.get("suffix", "")
    return "".join(
        chr(ord(char) + 0xFEE0) if style.get("full_width") and 0x21 <= ord(char) <= 0x7E
        else alphabet.get(char, char) + (suffix if char in LETTERS else "")
        for char in value
    )


def chat_id(value) -> int:
    if isinstance(value, str) and re.fullmatch(r"-?[1-9][0-9]{0,18}", value):
        value = int(value)
    if type(value) is not int or not -(2**63) < value < 2**63 or value == 0:
        raise ValueError("ID chat non valido.")
    return value


def positive_offset(value) -> int:
    if type(value) is not int or not 0 <= value <= 2**31 - 1:
        raise ValueError("Posizione nella cronologia non valida.")
    return value


def name(entity) -> str:
    return (getattr(entity, "title", None) or " ".join(filter(None, (
        getattr(entity, "first_name", None), getattr(entity, "last_name", None),
    ))) or getattr(entity, "username", None) or str(getattr(entity, "id", "")))[:256]


def iso(value):
    return value.isoformat() if isinstance(value, datetime) else None


def message_data(message):
    sender = getattr(message, "from_user", None) or getattr(message, "sender_chat", None)
    media = getattr(message, "media", None)
    return {
        "id": message.id,
        "text": str(getattr(message, "text", None) or getattr(message, "caption", None) or ""),
        "sender": name(sender),
        "sender_id": str(sender.id) if sender else "",
        "outgoing": bool(getattr(message, "outgoing", False)),
        "date": iso(getattr(message, "date", None)),
        "edited": iso(getattr(message, "edit_date", None)),
        "media": str(getattr(media, "value", media) or ""),
        "service": bool(getattr(message, "service", None)),
        "reply_to_id": getattr(message, "reply_to_message_id", None),
    }


class ChatService:
    def __init__(self, bridge):
        self.bridge = bridge
        self.iterator = None
        self.client = None
        self.dialogs = []
        self.seen = set()
        self.exhausted = False
        self.photos = ProfilePhotos(bridge)

    def require_client(self):
        if self.bridge.connection != "connected" or self.bridge.client is None:
            raise ValueError("Collega Telegram per leggere e inviare messaggi.")
        return self.bridge.client

    async def close(self):
        await self.photos.close()
        await self._reset_dialogs()

    async def _reset_dialogs(self):
        if self.iterator is not None:
            await self.iterator.aclose()
        self.iterator = None
        self.client = None
        self.dialogs = []
        self.seen = set()
        self.exhausted = False

    async def _dialogs(self, client):
        # Include archived conversations as well as the main folder.
        for archived in (False, True):
            async for dialog in client.get_dialogs(from_archive=archived):
                yield dialog, archived

    async def _fill_dialogs(self, offset):
        while len(self.dialogs) <= offset + DIALOG_PAGE and not self.exhausted:
            try:
                dialog, archived = await anext(self.iterator)
            except StopAsyncIteration:
                self.exhausted = True
                break
            chat = dialog.chat
            if chat.id in self.seen:
                continue
            self.seen.add(chat.id)
            self.photos.remember(chat)
            latest = getattr(dialog, "top_message", None)
            kind = str(getattr(chat.type, "value", chat.type))
            self.dialogs.append({
                "id": str(chat.id), "title": name(chat), "username": getattr(chat, "username", None) or "",
                "kind": kind, "unread": getattr(dialog, "unread_messages_count", 0) or 0,
                "archived": archived,
                "preview": message_data(latest)["text"][:180] if latest else "",
                "date": iso(getattr(latest, "date", None)),
            })

    async def list_dialogs(self, params):
        client = self.require_client()
        offset = positive_offset(params.get("offset", 0))
        if offset == 0 or self.client is not client:
            if self.client is not None and self.client is not client:
                await self.photos.close()
            await self._reset_dialogs()
            self.client = client
            self.iterator = self._dialogs(client)
        if offset > len(self.dialogs):
            raise ValueError("Ricarica l’elenco delle chat.")
        try:
            await asyncio.wait_for(self._fill_dialogs(offset), timeout=25)
        except asyncio.TimeoutError:
            # A cancelled async generator cannot resume. Restart cleanly on refresh.
            await self._reset_dialogs()
            raise ValueError("Caricamento delle chat scaduto. Riprova.") from None
        except Exception:
            await self._reset_dialogs()
            raise
        rows = self.dialogs[offset:offset + DIALOG_PAGE]
        next_offset = offset + len(rows)
        return {"chats": rows, "next_offset": next_offset,
                "has_more": next_offset < len(self.dialogs) or not self.exhausted}

    async def history(self, params):
        client = self.require_client()
        target = chat_id(params.get("chat_id"))
        before = positive_offset(params.get("before", 0))

        async def collect():
            if before == 1:
                return []
            # Kurigram 2.2.26 ignores the deprecated offset_id. max_id is inclusive.
            return [message async for message in client.get_chat_history(
                target, limit=HISTORY_PAGE + 1, max_id=before - 1 if before else 0,
            )]
        try:
            rows = await asyncio.wait_for(collect(), timeout=20)
        except asyncio.TimeoutError:
            raise ValueError("Caricamento dei messaggi scaduto. Riprova.") from None
        page = rows[:HISTORY_PAGE]
        for message in page:
            self.photos.remember(getattr(message, "chat", None))
            self.photos.remember(getattr(message, "from_user", None))
            self.photos.remember(getattr(message, "sender_chat", None))
        return {"chat_id": str(target), "messages": [message_data(item) for item in reversed(page)],
                "has_more": len(rows) > HISTORY_PAGE, "next_before": page[-1].id if page else None}

    async def send(self, params):
        client = self.require_client()
        target = chat_id(params.get("chat_id"))
        value = params.get("text")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Scrivi un messaggio prima di inviarlo.")
        if len(value) > MAX_MESSAGE_UNITS:
            raise ValueError("Il messaggio supera il limite di 4096 caratteri dopo la trasformazione.")
        transformed = transform_text(value, params.get("style", "plain"))
        try:
            units = len(transformed.encode("utf-16-le")) // 2
        except UnicodeError:
            raise ValueError("Il messaggio contiene caratteri non validi.") from None
        if units > MAX_MESSAGE_UNITS:
            raise ValueError("Il messaggio supera il limite di 4096 caratteri dopo la trasformazione.")
        # Disable Markdown/HTML parsing so the preview and delivered text match.
        # A failed send is never repeated automatically by this service.
        sent = await client.send_message(target, transformed, parse_mode=enums.ParseMode.DISABLED)
        if not sent or getattr(sent, "empty", False):
            raise ValueError("Telegram non ha confermato l’invio. Controlla la chat prima di riprovare.")
        self.photos.remember(getattr(sent, "from_user", None))
        self.photos.remember(getattr(sent, "sender_chat", None))
        return {"chat_id": str(target), "message": message_data(sent)}

    async def profile_photos(self, params):
        self.require_client()
        values = params.get("ids")
        known = params.get("known", {})
        if not isinstance(values, list) or len(values) > MAX_BATCH:
            raise ValueError("Elenco delle foto profilo non valido.")
        targets = list(dict.fromkeys(chat_id(value) for value in values))
        if not isinstance(known, dict) or len(known) > MAX_BATCH or any(
            key not in {str(target) for target in targets} or type(value) is not int or value < 0
            for key, value in known.items()
        ):
            raise ValueError("Elenco delle foto profilo non valido.")
        return self.photos.snapshot(targets, known)

    async def profile_photo(self, params):
        self.require_client()
        return await self.photos.preview(chat_id(params.get("chat_id")))
