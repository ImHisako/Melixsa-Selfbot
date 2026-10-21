"""Protezione dei nuovi accessi con la sessione Kurigram di Melixsa."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import re
import time

from pyrogram import enums, raw
from pyrogram.errors import FloodWait
from pyrogram.types import MessageEntity

from . import console_tools

# Codici associati esplicitamente a un accesso, mai numeri presi da date/telefoni.
CODE_RE = re.compile(
    r"(?:login\s+code|sign[ -]?in\s+code|codice\s+di\s+accesso|"
    r"c[oó]digo\s+de\s+inicio\s+de\s+sesi[oó]n|код\s+для\s+входа)"
    r"[^\d]{0,40}(?<!\d)([0-9]{4,8})(?!\d)", re.IGNORECASE,
)
POLL_INTERVAL = 30
MIN_RESET_INTERVAL = 3


class AntiLoginController:
    def __init__(self, enabled: Callable[[], bool], *, save_reset: Callable[[float], Awaitable[None]] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.enabled = enabled
        self.save_reset = save_reset
        self.clock = clock
        self.trusted: set[int] | None = None
        self.last_error = ""
        self.retry_after = 0.0
        self.next_scan = 0.0
        self.lock = asyncio.Lock()
        self.wakeup = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.reported: set[str] = set()

    async def notify(self, client, text: str) -> None:
        panel = f"[ MELIXSA / ANTI-LOGIN ]\n{text}"
        try:
            await client.send_message("me", panel, parse_mode=enums.ParseMode.DISABLED, entities=[
                MessageEntity(type=enums.MessageEntityType.PRE, offset=0,
                              length=len(panel.encode("utf-16-le")) // 2, language="ini")])
        except Exception as exc:
            if isinstance(exc, FloodWait):
                self.retry_after = max(self.retry_after, self.clock() + int(exc.value))
            # Non includere dati della richiesta, codici o identificatori sessione.
            console_tools.event("Error", f"Anti-login: avviso non inviato ({type(exc).__name__})", error=True)

    async def problem(self, client, phase: str, exc: Exception) -> None:
        kind = getattr(exc, "ID", None) or type(exc).__name__
        if isinstance(exc, FloodWait):
            self.retry_after = max(self.retry_after, self.clock() + int(exc.value))
            detail = f"Telegram richiede una pausa di {exc.value} secondi."
        elif kind == "FRESH_RESET_AUTHORISATION_FORBIDDEN":
            detail = "Telegram non consente di chiudere altre sessioni nelle prime 24 ore di questa sessione."
        else:
            detail = f"Richiesta non completata ({kind})."
        self.last_error = f"{phase}: {detail}"
        key = f"{phase}:{kind}"
        if key not in self.reported:
            self.reported.add(key)
            console_tools.event("Error", f"Anti-login | {self.last_error}", error=True)

    async def authorizations(self, client):
        result = await client.invoke(raw.functions.account.GetAuthorizations(), sleep_threshold=0)
        sessions = getattr(result, "authorizations", None)
        if not isinstance(sessions, (list, tuple)) or not any(getattr(item, "current", False) for item in sessions):
            raise ValueError("Incomplete authorization list")
        return sessions

    async def initialize(self, client) -> bool:
        async with self.lock:
            if self.trusted is not None:
                return True
            if self.clock() < self.retry_after:
                return False
            try:
                sessions = await self.authorizations(client)
                hashes = {int(item.hash) for item in sessions}
            except Exception as exc:
                await self.problem(client, "Lettura sessioni iniziali", exc)
                return False
            self.trusted = hashes
            self.last_error = ""
            console_tools.event("Event", f"Anti-login: elenco iniziale pronto ({len(hashes)} sessioni)", debug=True)
            return True

    async def start(self, client) -> None:
        await self.initialize(client)
        if self.task is None:
            self.task = asyncio.create_task(self.run(client))

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def run(self, client) -> None:
        while True:
            try:
                await asyncio.wait_for(self.wakeup.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass
            self.wakeup.clear()
            await self.scan(client)

    async def scan(self, client) -> None:
        async with self.lock:
            if not self.enabled() or self.trusted is None or self.clock() < self.retry_after:
                return
            remaining = self.next_scan - self.clock()
            if remaining > 0:
                await asyncio.sleep(remaining)
            if not self.enabled() or self.clock() < self.retry_after:
                return
            self.next_scan = self.clock() + MIN_RESET_INTERVAL
            try:
                sessions = await self.authorizations(client)
            except Exception as exc:
                await self.problem(client, "Controllo sessioni", exc)
                return
            for session in sessions:
                # Proteggi sempre questa sessione, indipendentemente dalla whitelist.
                if getattr(session, "current", False) or session.hash == 0 or session.hash in self.trusted:
                    continue
                if not self.enabled() or self.clock() < self.retry_after:
                    break
                try:
                    result = await client.invoke(raw.functions.account.ResetAuthorization(hash=session.hash), sleep_threshold=0)
                    if not result:
                        raise ValueError("Reset not confirmed")
                except Exception as exc:
                    await self.problem(client, "Chiusura nuova sessione", exc)
                    if isinstance(exc, FloodWait):
                        break
                else:
                    console_tools.event("Event", "Anti-login: nuova sessione chiusa")
                    await self.notify(client, "Una nuova sessione Telegram è stata chiusa.")
                    if self.save_reset is not None:
                        try:
                            await self.save_reset(time.time())
                        except Exception as exc:
                            await self.problem(client, "Salvataggio ultimo blocco", exc)
            # Nessun aggiornamento automatico della whitelist: i reset falliti
            # restano sconosciuti e verranno ricontrollati.

    async def handle_message(self, client, message) -> None:
        user = getattr(message, "from_user", None)
        if (not self.enabled() or message.chat.type != enums.ChatType.PRIVATE
                or message.chat.id != 777000 or not user or user.id != 777000
                or getattr(message, "outgoing", False)):
            return
        codes = list(dict.fromkeys(CODE_RE.findall(getattr(message, "text", None) or "")))
        if not codes or self.clock() < self.retry_after:
            return
        async with self.lock:
            if not self.enabled() or self.clock() < self.retry_after:
                return
            try:
                result = await client.invoke(raw.functions.account.InvalidateSignInCodes(codes=codes), sleep_threshold=0)
                if not result:
                    raise ValueError("Invalidation not confirmed")
            except Exception as exc:
                await self.problem(client, "Invalidazione codice di accesso", exc)
            else:
                console_tools.event("Event", "Anti-login: codice di accesso invalidato")
                await self.notify(client, "Codice di accesso ricevuto e invalidato.")
        self.wakeup.set()
