from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from pyrogram import enums
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import MessageEntity

from . import console_tools

REPLY_INTERVAL = 6 * 3600
DEFAULT_MESSAGE = "Al momento sono AFK. Tornerò appena possibile. Lascia un messaggio o il motivo per cui mi cerchi."
GIF_URL = "https://i.pinimg.com/1200x/6e/65/8e/6e658e917d89264d63ea1538eb4f5151.jpg"


class AFKController:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.active = False
        self.started: float | None = None
        self.message = DEFAULT_MESSAGE
        self.replied: dict[int, float] = {}
        self.retry_after = 0.0
        self.last_error = ""
        self.generation = 0
        self.send_lock = asyncio.Lock()

    def enable(self, text: str = "") -> None:
        if len(text.encode("utf-16-le")) // 2 > 3000:
            raise ValueError("Messaggio AFK: massimo 3000 caratteri UTF-16.")
        self.generation += 1
        self.active = True
        self.started = self.clock()
        self.message = text or DEFAULT_MESSAGE
        self.replied.clear()
        self.last_error = ""

    def duration(self) -> str:
        elapsed = max(0, int(self.clock() - self.started)) if self.started is not None else 0
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def disable(self) -> str:
        duration = self.duration()
        self.generation += 1
        self.active = False
        self.started = None
        self.replied.clear()
        return duration

    async def _send_text(self, client, chat_id: int, panel: str) -> None:
        entity = MessageEntity(type=enums.MessageEntityType.PRE, offset=0,
                               length=len(panel.encode("utf-16-le")) // 2, language="ini")
        await client.send_message(chat_id, panel, parse_mode=enums.ParseMode.DISABLED, entities=[entity])

    async def reply(self, client, message, chat_label: str) -> None:
        user = getattr(message, "from_user", None)
        if (not self.active or message.chat.type != enums.ChatType.PRIVATE or not user
                or getattr(user, "is_bot", False) or getattr(user, "is_self", False)
                or user.id == 777000 or getattr(message, "outgoing", False)
                or getattr(message, "service", None) or getattr(message, "empty", False)):
            return
        generation = self.generation
        async with self.send_lock:
            now = self.clock()
            if not self.active or generation != self.generation or now < self.retry_after:
                return
            previous = self.replied.get(user.id)
            if previous is not None and now - previous < REPLY_INTERVAL:
                return
            self.replied = {key: timestamp for key, timestamp in self.replied.items() if now - timestamp < REPLY_INTERVAL}
            if len(self.replied) >= 4096:
                return
            # Prenota la risposta prima dell'invio, evitando duplicati concorrenti.
            self.replied[user.id] = now
            panel = f"[ MELIXSA / AFK ]\n{self.message}"
            short = len(panel.encode("utf-16-le")) // 2 <= 1024
            try:
                try:
                    entity = MessageEntity(type=enums.MessageEntityType.PRE, offset=0,
                                           length=len(panel.encode("utf-16-le")) // 2, language="ini")
                    await client.send_animation(message.chat.id, GIF_URL, caption=panel if short else "",
                                                parse_mode=enums.ParseMode.DISABLED,
                                                caption_entities=[entity] if short else None)
                except FloodWait:
                    raise
                except RPCError as exc:
                    console_tools.event("Error", f"AFK GIF | chat={chat_label} | {exc}", error=True)
                    await self._send_text(client, message.chat.id, panel)
                else:
                    if not short:
                        await self._send_text(client, message.chat.id, panel)
            except FloodWait as exc:
                self.retry_after = max(self.retry_after, self.clock() + int(exc.value))
                self.last_error = f"Telegram richiede una pausa di {exc.value} secondi."
                if generation == self.generation:
                    self.replied.pop(user.id, None)
                console_tools.event("Error", f"AFK | chat={chat_label} | {self.last_error}", error=True)
            except Exception as exc:
                self.last_error = str(exc)
                if generation == self.generation:
                    self.replied[user.id] = self.clock() - REPLY_INTERVAL + 60
                console_tools.event("Error", f"AFK | chat={chat_label} | {exc}", error=True)
            else:
                console_tools.event("Message", f"AFK | chat={chat_label} | risposta automatica inviata")
