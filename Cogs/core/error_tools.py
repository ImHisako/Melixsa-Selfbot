"""Avvisi generici e limitati nel tempo, esclusivamente nei Messaggi salvati."""
from __future__ import annotations

import asyncio
import time

from pyrogram import enums
from pyrogram.errors import FloodWait

from . import console_tools


class ErrorNotifier:
    def __init__(self, client, enabled, *, interval=60):
        self.client, self.enabled, self.interval = client, enabled, interval
        self.loop = asyncio.get_running_loop()
        self.event = asyncio.Event()
        self.count = 0
        self.next_send = 0.0
        self.last_error = ""
        self.task = asyncio.create_task(self._run(), name="melixsa-error-notify")

    def signal(self):
        # I log possono arrivare anche dal thread di scrittura.
        try:
            self.loop.call_soon_threadsafe(self._signal)
        except RuntimeError:
            pass  # Il loop può chiudersi fra l'ultimo errore e la notifica.

    def _signal(self):
        if self.enabled() and not self.task.done():
            self.count = min(9999, self.count + 1)
            self.event.set()

    async def _run(self):
        while True:
            await self.event.wait()
            await asyncio.sleep(max(0, self.next_send - time.monotonic()))
            count, self.count = self.count, 0
            self.event.clear()
            if not self.enabled() or not count:
                continue
            self.next_send = time.monotonic() + self.interval
            try:
                await self.client.send_message("me", f"[ MELIXSA / ERRORI ]\nErrori rilevati » {count}\nUsa doctor con il prefisso corrente per la diagnostica.", parse_mode=enums.ParseMode.DISABLED)
                self.last_error = ""
            except Exception as exc:
                if isinstance(exc, FloodWait):
                    self.next_send = max(self.next_send, time.monotonic() + int(exc.value))
                self.last_error = type(exc).__name__
                # Evita che l'errore dell'avviso generi altri avvisi.
                console_tools.logger.warning("Avviso errori non inviato (%s)", self.last_error)

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
