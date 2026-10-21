"""Reazioni automatiche ai nuovi messaggi del proprio account."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any
from . import console_tools


EMOJIS = ("🖤", "🦇")
MAX_REACTIONS = 3


def parse_emojis(value: str) -> tuple[str, ...]:
    emojis = tuple(value.split())
    if not 1 <= len(emojis) <= MAX_REACTIONS:
        raise ValueError("Scegli da 1 a 3 emoji separate da spazi.")
    if any(len(emoji) > 32 or not any(ord(char) > 127 for char in emoji)
           or any(char.isalpha() for char in emoji if ord(char) < 128)
           for emoji in emojis):
        raise ValueError("Inserisci solo emoji separate da spazi, per esempio: 👍 ❤️ 🔥.")
    if len({emoji.replace("\ufe0f", "") for emoji in emojis}) != len(emojis):
        raise ValueError("Scegli emoji diverse, senza duplicati.")
    return emojis


class ReactionSendError(ValueError):
    """Una o più reazioni sono state rifiutate da Telegram."""


class AutoReactor:
    def __init__(self) -> None:
        self.reactions: list[Any] | None = None
        self.resolved_emojis: tuple[str, ...] = ()
        self.last_error = ""
        self.retry_after = 0.0
        self.chat_retry_after: dict[int, float] = {}
        self._prepare_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()

    def _flood_wait(self, seconds: int) -> str:
        self.retry_after = time.monotonic() + seconds
        self.last_error = f"Telegram richiede una pausa di {seconds} secondi."
        return self.last_error

    async def prepare(self, client: Any, *, refresh: bool = False, emojis: tuple[str, ...] = EMOJIS) -> list[Any]:
        from pyrogram import raw
        from pyrogram.errors import FloodWait

        async with self._prepare_lock:
            if time.monotonic() < self.retry_after:
                raise ValueError(self.last_error)
            if self.reactions is not None and self.resolved_emojis == emojis and not refresh:
                return self.reactions
            try:
                available = await client.invoke(
                    raw.functions.messages.GetAvailableReactions(hash=0), sleep_threshold=0,
                )
                standard = {item.reaction.replace("\ufe0f", ""): item.reaction for item in available.reactions if not item.inactive}
                reactions = []
                for emoji in emojis:
                    canonical = emoji.replace("\ufe0f", "")
                    if canonical in standard:
                        reactions.append(raw.types.ReactionEmoji(emoticon=standard[canonical]))
                    else:
                        found = await client.invoke(
                            raw.functions.messages.SearchCustomEmoji(emoticon=emoji, hash=0),
                            sleep_threshold=0,
                        )
                        ids = getattr(found, "document_id", [])
                        if not ids:
                            raise ValueError(f"Telegram non ha trovato una reazione personalizzata per {emoji}. Riprova più tardi.")
                        reactions.append(raw.types.ReactionCustomEmoji(document_id=ids[0]))
                self.reactions = reactions
                self.resolved_emojis = emojis
                self.last_error = ""
                return reactions
            except FloodWait as exc:
                raise ValueError(self._flood_wait(int(exc.value))) from exc

    async def react(self, client: Any, message: Any, enabled: Callable[[], bool], *, emojis: tuple[str, ...] = EMOJIS, chat_label: str | None = None) -> None:
        from pyrogram import raw
        from pyrogram.errors import FloodWait, MessageNotModified, RPCError

        if getattr(message, "service", None) or getattr(message, "empty", False):
            return
        async with self._send_lock:
            now = time.monotonic()
            if not enabled() or now < self.retry_after or now < self.chat_retry_after.get(message.chat.id, 0):
                return
            try:
                reactions = await self.prepare(client, emojis=emojis)
                peer = await client.resolve_peer(message.chat.id)
                applied = []
                applied_emojis = []
                failures = []
                for emoji, reaction in zip(emojis, reactions):
                    if not enabled():
                        return
                    try:
                        # Telegram sostituisce l'intero elenco: conserva la prima
                        # reazione quando aggiungi la seconda, dopo la conferma.
                        await client.invoke(
                            raw.functions.messages.SendReaction(
                                peer=peer, msg_id=message.id, reaction=[*applied, reaction],
                            ),
                            sleep_threshold=0,
                        )
                    except FloodWait:
                        raise
                    except MessageNotModified:
                        pass  # Questo insieme di reazioni è già presente.
                    except RPCError as exc:
                        failures.append(f"{emoji}: {exc.ID}")
                        continue
                    applied.append(reaction)
                    applied_emojis.append(emoji)
                if failures:
                    raise ReactionSendError(
                        f"{'; '.join(failures)}. Confermate: {' '.join(applied_emojis) or 'nessuna'}."
                    )
            except MessageNotModified:
                return
            except FloodWait as exc:
                self._flood_wait(int(exc.value))
            except (RPCError, ReactionSendError) as exc:
                detail = exc.ID if isinstance(exc, RPCError) else str(exc)
                self.last_error = f"Chat {message.chat.id}: {detail}"
                sender = getattr(message, "from_user", None)
                if "PREMIUM_ACCOUNT_REQUIRED" in detail and getattr(sender, "id", None) == message.chat.id:
                    self.last_error += (
                        " Nei Messaggi salvati le nuove reazioni sono tag e richiedono Premium, "
                        "anche con una sola emoji standard. Prova in un'altra chat o in un gruppo con reazioni abilitate."
                    )
                # Una chat che rifiuta gli emoji non impedisce di reagire nelle altre.
                self.chat_retry_after = {chat: until for chat, until in self.chat_retry_after.items() if until > now}
                if len(self.chat_retry_after) >= 256:
                    self.chat_retry_after.pop(next(iter(self.chat_retry_after)))
                self.chat_retry_after[message.chat.id] = now + 60
            except Exception as exc:
                self.last_error = str(exc)
                self.retry_after = max(self.retry_after, now + 60)
            else:
                content = getattr(message, "text", None) or getattr(message, "caption", None)
                if not content:
                    media = getattr(message, "media", None)
                    content = f"[{getattr(media, 'value', media)}]" if media else "[messaggio senza testo]"
                console_tools.event(
                    "Event",
                    f"Autoreact | chat={chat_label or message.chat.id} | message={content} | confermate={len(applied)}",
                )
                return
            # Non modificare il messaggio dell'utente e non inviare risposte automatiche.
            console_tools.event("Error", f"Autoreact: {self.last_error}", error=True)
