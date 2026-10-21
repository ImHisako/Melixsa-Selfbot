"""Testi LRCLIB sincronizzati al player SoundCloud, attivati su richiesta."""

from __future__ import annotations
from . import console_tools

import bisect
import asyncio
import json
import math
import os
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from . import soundcloud_tools


TIMESTAMP = re.compile(r"\[(\d{1,3}):([0-5]\d)(?:[.:](\d{1,3}))?\]")
MAX_RESPONSE = 1024 * 1024
MIN_INTERVAL = 3.0
REQUEST_INTERVAL = 0.3
_request_lock = threading.Lock()
_next_request_at = 0.0


class LyricsError(ValueError):
    pass


class TemporaryLyricsError(LyricsError):
    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


def retry_after_seconds(value: str | None) -> float:
    if not isinstance(value, str):
        return 0
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = date.timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            return 0
    return max(0, seconds) if math.isfinite(seconds) else 0


def client_user_agent() -> str:
    contact = os.environ.get("LRCLIB_CLIENT_CONTACT", "").strip()
    valid = bool(re.fullmatch(r"[^\s@()]+@[^\s@()]+\.[^\s@()]+", contact))
    if contact.startswith(("https://", "http://")):
        try:
            parsed = urlsplit(contact)
            valid = bool(parsed.hostname and not parsed.username and not parsed.password)
        except ValueError:
            valid = False
    if not valid or not contact.isascii() or len(contact) > 300 or any(c.isspace() or c in "()" for c in contact):
        raise LyricsError("Imposta LRCLIB_CLIENT_CONTACT in .env con un link del progetto o un'email di contatto, poi riavvia.")
    return f"MelixsaSelfbot/1.0 ({contact})"


def parse_lrc(text: str) -> list[tuple[float, str]]:
    offset = re.search(r"\[offset:([+-]?\d+)\]", text, re.IGNORECASE)
    shift = int(offset[1]) / 1000 if offset else 0
    lines = {}
    for raw in text.splitlines():
        stamps = list(TIMESTAMP.finditer(raw))
        if not stamps or raw[:stamps[0].start()].strip():
            continue
        content = raw[stamps[-1].end():].strip()
        content = re.sub(r"<\d{1,3}:[0-5]\d(?:[.:]\d{1,3})?>", "", content)
        if len(content.encode("utf-16-le")) // 2 > 3000:
            raise LyricsError("Il testo contiene una riga troppo lunga per Telegram.")
        for stamp in stamps:
            fraction = float("0." + stamp[3]) if stamp[3] else 0
            seconds = max(0, int(stamp[1]) * 60 + int(stamp[2]) + fraction - shift)
            # Le righe vuote delimitano le pause strumentali.
            if seconds not in lines or not lines[seconds]:
                lines[seconds] = content
    return sorted(lines.items())


def current_line(lines: list[tuple[float, str]], position: float) -> tuple[int, str] | None:
    index = bisect.bisect_right([seconds for seconds, _ in lines], position) - 1
    if index < 0:
        return None
    timestamp, text = lines[index]
    if not text or position - timestamp > 4:
        return None
    return index, text


@dataclass(frozen=True)
class Track:
    player_id: int
    title: str
    artist: str
    album: str
    duration: int

    @classmethod
    def from_player(cls, player):
        return cls(player.local_id, str(player.values.get("title", "")).strip(),
                   str(player.values.get("artist", "")).strip(),
                   str(player.values.get("album", "")).strip(), player.number("duration"))


def lookup_tracks(track: Track) -> list[Track]:
    candidates = [track] if track.title and track.artist else []
    # Su SoundCloud l'artista può essere l'uploader. Prova anche il formato
    # esplicito "Artista - Titolo", conservando remix e versioni alternative.
    parts = re.split(r"\s+[-–—]\s+", track.title, maxsplit=1)
    if len(parts) == 2 and all(part.strip() for part in parts):
        artist, title = (part.strip() for part in parts)
        title = re.sub(r"\s*\((?:original|official audio)\)\s*$", "", title, flags=re.IGNORECASE).strip()
        if title:
            candidate = Track(track.player_id, title, artist, track.album, track.duration)
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def fetch_lyrics(track: Track) -> list[tuple[float, str]]:
    global _next_request_at

    candidates = lookup_tracks(track)
    if not candidates:
        return []
    user_agent = client_user_agent()
    # Il lock comprende la richiesta: un worker ancora in esecuzione dopo off
    # non si sovrappone a una nuova richiesta.
    with _request_lock:
        for candidate in candidates:
            remaining = _next_request_at - time.monotonic()
            if remaining > REQUEST_INTERVAL + 0.05:
                raise TemporaryLyricsError("LRCLIB: attesa richiesta dal servizio.", remaining)
            if remaining > 0:
                time.sleep(remaining)
            try:
                lines = _fetch_lyrics(candidate, user_agent)
                if lines:
                    return lines
            except TemporaryLyricsError as exc:
                if exc.retry_after > 0:
                    _next_request_at = time.monotonic() + exc.retry_after
                raise
            finally:
                _next_request_at = max(_next_request_at, time.monotonic() + REQUEST_INTERVAL)
    return []


def _fetch_lyrics(track: Track, user_agent: str) -> list[tuple[float, str]]:
    import requests

    if not track.title or not track.artist:
        return []
    params = {"track_name": track.title, "artist_name": track.artist}
    if track.album:
        params["album_name"] = track.album
    if 1 <= track.duration <= 3600:
        params["duration"] = track.duration
    try:
        with requests.get("https://lrclib.net/api/get", params=params,
                          headers={"User-Agent": user_agent, "Accept": "application/json"},
                          timeout=(10, 20), stream=True, allow_redirects=False) as response:
            if response.status_code == 404:
                return []
            if response.status_code in {429, 500, 502, 503, 504}:
                if response.headers.get("cf-mitigated") == "challenge":
                    raise LyricsError("LRCLIB richiede una verifica del client. Invio fermato; accesso API non disponibile.")
                detail = "limite richieste raggiunto" if response.status_code == 429 else "servizio temporaneamente non disponibile"
                raise TemporaryLyricsError(
                    f"LRCLIB: {detail} (HTTP {response.status_code}).",
                    retry_after_seconds(response.headers.get("Retry-After")),
                )
            if response.status_code != 200:
                if response.status_code == 400:
                    raise LyricsError("LRCLIB ha rifiutato i parametri del brano (HTTP 400). Controlla titolo, artista e durata.")
                raise LyricsError(f"LRCLIB non disponibile (HTTP {response.status_code}).")
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise LyricsError("LRCLIB ha restituito un contenuto non JSON; impossibile leggere il testo.")
            data = bytearray()
            for chunk in response.iter_content(8192):
                data.extend(chunk)
                if len(data) > MAX_RESPONSE:
                    raise LyricsError("Risposta LRCLIB troppo grande.")
    except requests.exceptions.SSLError:
        raise LyricsError("Impossibile verificare la connessione sicura a LRCLIB.") from None
    except requests.RequestException:
        raise TemporaryLyricsError("Connessione a LRCLIB interrotta o tempo scaduto.") from None
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError):
        raise LyricsError("Risposta LRCLIB non valida.") from None
    if not isinstance(result, dict):
        raise LyricsError("Risposta LRCLIB non valida.")
    lrc = result.get("syncedLyrics")
    if result.get("instrumental") or not isinstance(lrc, str):
        return []
    duration = result.get("duration")
    if track.duration and isinstance(duration, (int, float)) and abs(duration - track.duration) > 2:
        return []  # Una versione di durata diversa non garantisce la sincronizzazione.
    return parse_lrc(lrc)


class LyricsController:
    def __init__(self, adapter):
        self.adapter = adapter
        self.clock = time.monotonic
        self.task = None
        self.destination = None
        self.status = "off"
        self.track = None
        self.lines = []
        self.last_index = -1
        self.last_position = None
        self.last_sent = float("-inf")
        self.retry_after = 0.0
        self.lookup_retry_after = 0.0
        self.lookup_failures = 0
        self.cache = {}
        self.lock = asyncio.Lock()

    @property
    def running(self):
        return self.task is not None and not self.task.done()

    async def stop(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
        self.destination = None
        self.status = "off"

    async def start(self, destination, send_line, notify):
        if self.clock() < self.retry_after:
            seconds = max(1, int(self.retry_after - self.clock()) + 1)
            raise LyricsError(f"Telegram richiede ancora {seconds} secondi di pausa.")
        if self.running and self.destination == destination:
            return
        was_running = self.running
        status = "ricerca testo sincronizzato"
        try:
            self.adapter.active_player()
        except soundcloud_tools.SoundCloudError as exc:
            if was_running or getattr(self.adapter, "error", ""):
                raise  # Conserva la destinazione già attiva se il cambio non è valido.
            status = f"in attesa del player SoundCloud: {exc}"
        await self.stop()
        if not was_running:
            self.lookup_failures = 0
        self.destination = destination
        self.track = None
        self.status = status
        self.task = asyncio.create_task(self.run(send_line, notify))

    async def tick(self, send_line, notify):
        try:
            player = self.adapter.active_player()
        except soundcloud_tools.SoundCloudError as exc:
            self.status = f"in attesa del player SoundCloud: {exc}"
            return
        track = Track.from_player(player)
        if track != self.track:
            self.status = "ricerca testo sincronizzato"
            if track not in self.cache:
                if self.clock() < self.lookup_retry_after:
                    seconds = math.ceil(self.lookup_retry_after - self.clock())
                    self.status = f"in attesa di LRCLIB: nuovo tentativo tra {seconds} s"
                    return
                try:
                    lines = await asyncio.to_thread(fetch_lyrics, track)
                except TemporaryLyricsError as exc:
                    self.lookup_failures += 1
                    # Retry-After indica l'attesa minima: valori brevi non devono
                    # esaurire tutti i tentativi mentre il server è sovraccarico.
                    backoff = 30 * 2 ** min(self.lookup_failures - 1, 2)
                    delay = max(backoff, exc.retry_after)
                    delay += random.uniform(0, min(5, delay * 0.2))
                    self.lookup_retry_after = self.clock() + delay
                    if self.lookup_failures > 3:
                        raise LyricsError(f"{exc} Lyrics fermate dopo 4 tentativi. Riprova più tardi con sclyrics on.") from None
                    self.status = f"{exc} Nuovo tentativo tra {math.ceil(delay)} s ({self.lookup_failures}/3)."
                    if self.lookup_failures == 1:
                        console_tools.event("Error", f"Lyrics: {self.status}", error=True)
                    return
                self.lookup_failures = 0
                self.lookup_retry_after = 0.0
                if len(self.cache) >= 32:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[track] = lines
            # Il brano può cambiare mentre la ricerca è in corso.
            try:
                player = self.adapter.active_player()
            except soundcloud_tools.SoundCloudError:
                return
            if Track.from_player(player) != track:
                return
            self.track = track
            self.lines = self.cache[track]
            self.last_index = -1
            self.last_position = None
            if not any(text for _, text in self.lines):
                await notify("Testo sincronizzato non trovato per questo brano. Attendo la prossima canzone.")
        if not any(text for _, text in self.lines):
            self.status = "testo sincronizzato non disponibile"
            return
        if player.number("state") != 0:
            self.status = "in pausa"
            return
        position = player.number("position")
        if self.last_position is not None and position < self.last_position:
            self.last_index = -1  # Seek indietro o ripetizione del brano.
        self.last_position = position
        self.status = "attivo"
        due = current_line(self.lines, position)
        if due is None or due[0] == self.last_index:
            return
        if self.clock() - self.last_sent < MIN_INTERVAL:
            return
        await send_line(due[1])
        self.last_index = due[0]
        self.last_sent = self.clock()

    async def run(self, send_line, notify):
        from pyrogram.errors import FloodWait

        try:
            while True:
                await self.tick(send_line, notify)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except FloodWait as exc:
            self.retry_after = self.clock() + int(exc.value)
            self.status = f"fermo: Telegram richiede una pausa di {exc.value} secondi"
            console_tools.event("Error", f"Lyrics: {self.status}", error=True)
        except LyricsError as exc:
            self.status = str(exc)
            console_tools.event("Error", f"Lyrics: {self.status}", error=True)
        except Exception:
            self.status = "fermo: impossibile inviare le lyrics in questa chat"
            console_tools.event("Error", f"Lyrics: {self.status}", error=True)
