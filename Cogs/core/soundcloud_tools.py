"""Adattatore locale WebNowPlaying per i player SoundCloud nel browser.

Protocollo: https://github.com/keifufu/WebNowPlaying/blob/main/src/extension/sw/socket.ts
Eventi: https://github.com/keifufu/WebNowPlaying-Library/blob/main/src/internal.h
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any
from . import console_tools


DEFAULT_PORT = 8976
ADDON_URL = "https://addons.mozilla.org/en-US/firefox/addon/webnowplaying/"
# Ordine e valori del protocollo WebNowPlaying revision 3 (socket.ts).
FIELDS = (
    "id", "name", "title", "artist", "album", "cover", "state", "position",
    "duration", "volume", "rating", "repeat", "shuffle", "rating_system",
    "available_repeat", "can_set_state", "can_skip_previous", "can_skip_next",
    "can_set_position", "can_set_volume", "can_set_rating", "can_set_repeat",
    "can_set_shuffle", "created_at", "updated_at", "active_at",
)
STRING_FIELDS = {"name", "title", "artist", "album", "cover"}
EVENTS = {
    "state": (0, "can_set_state"),
    "previous": (1, "can_skip_previous"),
    "next": (2, "can_skip_next"),
    "position": (3, "can_set_position"),
    "volume": (4, "can_set_volume"),
    "rating": (5, "can_set_rating"),
    "repeat": (6, "can_set_repeat"),
    "shuffle": (7, "can_set_shuffle"),
}
COMMANDS = {
    "scnp", "scplay", "scpause", "sctoggle", "scnext", "scprev", "scvolume",
    "scseek", "screpeat", "scshuffle", "sclike", "scplayers", "scselect", "scconnect",
}


class SoundCloudError(ValueError):
    """Errore leggibile nei pannelli Telegram."""


def parse_player_data(payload: str) -> dict[str, str | int]:
    parts = re.split(r"(?<!\\)\|", payload)
    if len(parts) != len(FIELDS) + 1 or parts[-1] != "":
        raise ValueError("Dati player incompleti")
    values: dict[str, str | int] = {}
    for name, value in zip(FIELDS, parts):
        if not value:
            continue  # I campi vuoti sono delta, non valori da cancellare.
        if name in STRING_FIELDS:
            values[name] = "" if value == "\x01" else value.replace(r"\|", "|")[:2048]
        else:
            number = int(value)
            if number < 0:
                raise ValueError("Valore player negativo")
            values[name] = number
    return values


def format_time(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def parse_position(value: str) -> int:
    if not re.fullmatch(r"\d+(?::[0-5]\d){0,2}", value):
        raise SoundCloudError("Indica secondi, mm:ss o hh:mm:ss, per esempio 90 o 1:30.")
    seconds = 0
    for part in value.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def toggle_value(argument: str, current: int) -> int:
    value = argument.lower()
    if value in {"", "toggle"}:
        return 0 if current else 1
    if value in {"on", "1"}:
        return 1
    if value in {"off", "0"}:
        return 0
    raise SoundCloudError("Usa on, off oppure toggle.")


def panel_value(value: object, limit: int = 500) -> str:
    text = " ".join(str(value).split()) or "—"
    encoded = text.encode("utf-16-le")
    if len(encoded) <= limit * 2:
        return text
    return encoded[:(limit - 1) * 2].decode("utf-16-le", errors="ignore") + "…"


@dataclass
class Player:
    local_id: int
    remote_id: int
    connection: Any
    values: dict[str, str | int] = field(default_factory=dict)

    def number(self, name: str) -> int:
        value = self.values.get(name, 0)
        return value if isinstance(value, int) else 0

    @property
    def is_soundcloud(self) -> bool:
        return str(self.values.get("name", "")).casefold() == "soundcloud"


class SoundCloudAdapter:
    def __init__(self, port: int | None = None, *, event_timeout: float = 5) -> None:
        self.port = port if port is not None else DEFAULT_PORT
        self.event_timeout = event_timeout
        self.server: Any = None
        self.error = ""
        self.connections: set[Any] = set()
        self.players: dict[int, Player] = {}
        self.selected_id: int | None = None
        self.pending: dict[tuple[Any, int], asyncio.Future[bool]] = {}
        self._next_player_id = 1
        self._next_event_id = 1
        self._start_lock = asyncio.Lock()
        self._read_port_env = port is None

    async def start(self) -> None:
        async with self._start_lock:
            if self.server is not None:
                return
            try:
                if self._read_port_env:
                    self.port = int(os.environ.get("WEBNOWPLAYING_PORT", str(DEFAULT_PORT)))
                if not 1024 <= self.port <= 65535:
                    raise ValueError
            except ValueError:
                self.error = "WEBNOWPLAYING_PORT deve essere un intero tra 1024 e 65535."
                return
            try:
                from websockets.asyncio.server import serve
            except ImportError:
                self.error = "Installa le dipendenze: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
                return
            try:
                self.server = await serve(
                    self._handle_socket, "127.0.0.1", self.port,
                    max_size=8 * 1024 * 1024, max_queue=16,
                )
            except OSError:
                self.error = f"Porta {self.port} occupata o non disponibile. Cambia WEBNOWPLAYING_PORT e riavvia."
                return
            self.error = ""
            console_tools.event("Event", f"WebNowPlaying in ascolto su 127.0.0.1:{self.port}", debug=True)

    async def close(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def _handle_socket(self, connection: Any) -> None:
        from websockets.exceptions import ConnectionClosed

        self.connections.add(connection)
        console_tools.event("Event", "WebNowPlaying collegato", debug=True)
        try:
            await connection.send("ADAPTER_VERSION 3.0.0;WNPLIB_REVISION 3")
            async for message in connection:
                if not isinstance(message, str):
                    continue  # Le copertine binarie non servono al pannello testuale.
                try:
                    self._receive(connection, message)
                except (ValueError, KeyError):
                    continue
        except ConnectionClosed:
            pass
        finally:
            self.connections.discard(connection)
            console_tools.event("Event", "WebNowPlaying disconnesso", debug=True)
            for local_id, player in list(self.players.items()):
                if player.connection is connection:
                    self._remove_player(local_id)
            for key, future in list(self.pending.items()):
                if key[0] is connection and not future.done():
                    future.set_exception(SoundCloudError("WebNowPlaying disconnesso. Ricollega l'estensione e riprova."))

    def _remove_player(self, local_id: int) -> None:
        self.players.pop(local_id, None)
        if self.selected_id == local_id:
            self.selected_id = None

    def _receive(self, connection: Any, message: str) -> None:
        kind, data = message.split(" ", 1)
        if kind == "3":
            event_id, result = data.split(" ", 1)
            future = self.pending.get((connection, int(event_id)))
            if future is not None and not future.done() and result in {"1", "2"}:
                future.set_result(result == "1")
            return
        if kind == "4":
            return  # Nessun player desktop: questa categoria riguarda SoundCloud web.
        if kind not in {"0", "1", "2"}:
            return
        remote_id_text, _, payload = data.partition(" ")
        remote_id = int(remote_id_text)
        if remote_id < 0:
            return
        player = next((p for p in self.players.values()
                       if p.connection is connection and p.remote_id == remote_id), None)
        if kind == "2":
            if player is not None:
                self._remove_player(player.local_id)
            return
        values = parse_player_data(payload)
        if "id" in values and values["id"] != remote_id:
            return
        if player is None:
            if kind != "0" or len(self.players) >= 64:
                return
            player = Player(self._next_player_id, remote_id, connection)
            self._next_player_id += 1
            self.players[player.local_id] = player
        player.values.update(values)

    def soundcloud_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.is_soundcloud]

    def active_player(self) -> Player:
        if self.server is None:
            raise SoundCloudError(self.error or "Adattatore fermo. Usa scconnect per avviarlo.")
        if not self.connections:
            raise SoundCloudError(f"WebNowPlaying non collegato. Aggiungi un Custom Adapter con porta {self.port} nell'estensione.")
        players = self.soundcloud_players()
        if not players:
            raise SoundCloudError("Nessun player SoundCloud. Apri soundcloud.com nel browser con WebNowPlaying e avvia un brano.")
        if self.selected_id is not None:
            selected = next((p for p in players if p.local_id == self.selected_id), None)
            if selected is not None:
                return selected
            self.selected_id = None
        return max(players, key=lambda p: (p.number("state") == 0 and p.number("volume") > 0, p.number("active_at"), p.local_id))

    def setup_text(self, prefix: str) -> str:
        status = self.error or ("collegato" if self.connections else "in attesa dell'estensione")
        return (
            f"Adattatore » {status}\nPorta locale » {self.port}\n"
            f"Estensione » {ADDON_URL}\n"
            "1. Installa WebNowPlaying nel browser su questo PC.\n"
            f"2. Nell'estensione: Add custom adapter, porta {self.port}, abilitalo.\n"
            "3. Apri soundcloud.com e avvia una canzone.\n"
            f"Brano » {prefix}scnp\nSchede » {len(self.soundcloud_players())}"
        )

    def now_playing(self, player: Player) -> str:
        value = player.values
        state = {0: "in riproduzione", 1: "in pausa", 2: "fermo"}.get(player.number("state"), "—")
        return (
            f"Brano » {panel_value(value.get('title', ''))}\n"
            f"Artista » {panel_value(value.get('artist', ''))}\n"
            f"Album » {panel_value(value.get('album', ''))}\n"
            f"Stato » {state}\n"
            f"Tempo » {format_time(player.number('position'))} / {format_time(player.number('duration'))}\n"
            f"Volume » {player.number('volume')}%"
        )

    async def _send_event(self, player: Player, action: str, value: int = 0) -> None:
        event, capability = EVENTS[action]
        if not player.number(capability):
            raise SoundCloudError("Questo controllo non è disponibile nel player SoundCloud corrente.")
        event_id = self._next_event_id
        self._next_event_id += 1
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        key = (player.connection, event_id)
        self.pending[key] = future
        try:
            await player.connection.send(f"{player.remote_id} {event_id} {event} {value}")
            if not await asyncio.wait_for(future, timeout=self.event_timeout):
                raise SoundCloudError("SoundCloud non ha eseguito il comando. Controlla la scheda e riprova.")
        except asyncio.TimeoutError as exc:
            raise SoundCloudError("Nessuna conferma da WebNowPlaying. Controlla la scheda SoundCloud prima di riprovare.") from exc
        finally:
            self.pending.pop(key, None)
            if not future.done():
                future.cancel()

    async def execute(self, command: str, argument: str, prefix: str = "/") -> str:
        argument = argument.strip()
        if command == "scconnect":
            if argument:
                raise SoundCloudError(f"Uso: {prefix}scconnect")
            await self.start()
            return self.setup_text(prefix)
        if command == "scselect":
            if argument.lower() == "auto":
                self.selected_id = None
                return "Scheda » selezione automatica"
            if not argument.isdecimal():
                raise SoundCloudError(f"Usa {prefix}scselect <ID> oppure auto. ID da {prefix}scplayers.")
            player = self.players.get(int(argument))
            if player is None or not player.is_soundcloud:
                raise SoundCloudError(f"Scheda SoundCloud non disponibile. Usa {prefix}scplayers.")
            self.selected_id = player.local_id
            return f"Scheda » {player.local_id}\nBrano » {panel_value(player.values.get('title', ''))}"
        if command == "scplayers":
            if argument:
                raise SoundCloudError(f"Uso: {prefix}scplayers")
            active = self.active_player()
            lines = [f"Selezione » {'automatica' if self.selected_id is None else 'manuale'}"]
            players = self.soundcloud_players()
            # Budget in unità UTF-16, incluso l'header aggiunto da respond().
            row_budget = 3500 // len(players)
            for player in players:
                mark = " *" if player is active else ""
                label = f"{player.values.get('title', '')} / {player.values.get('artist', '')}"
                limit = max(1, row_budget - len(str(player.local_id)) - len(mark) - 4)
                lines.append(f"{player.local_id}{mark} » {panel_value(label, limit)}")
            lines.append(f"Scegli » {prefix}scselect <ID|auto>")
            return "\n".join(lines)
        if command not in COMMANDS:
            raise SoundCloudError(f"Comando sconosciuto. Usa {prefix}soundcloud.")
        if command in {"scnp", "scplay", "scpause", "sctoggle", "scnext", "scprev"} and argument:
            raise SoundCloudError(f"Uso: {prefix}{command}. Per cambiare brano usa scnext o scprev nella coda SoundCloud.")
        player = self.active_player()
        if command == "scnp":
            return self.now_playing(player)
        if command in {"scplay", "scpause", "sctoggle"}:
            target = 0 if command == "scplay" else 1
            if command == "sctoggle":
                target = 1 if player.number("state") == 0 else 0
            await self._send_event(player, "state", target)
            return "Riproduzione » avviata" if target == 0 else "Riproduzione » in pausa"
        if command in {"scnext", "scprev"}:
            await self._send_event(player, "next" if command == "scnext" else "previous")
            return f"Brano » {'successivo' if command == 'scnext' else 'precedente'}\nAggiorna » {prefix}scnp"
        if command == "scvolume":
            if not argument:
                return f"Volume » {player.number('volume')}%\nCambia » {prefix}scvolume 50"
            if not argument.isdecimal() or not 0 <= int(argument) <= 100:
                raise SoundCloudError("Inserisci un volume intero da 0 a 100.")
            volume = int(argument)
            await self._send_event(player, "volume", volume)
            return f"Volume » {volume}%"
        if command == "scseek":
            position = parse_position(argument)
            if not player.number("duration") or position > player.number("duration"):
                raise SoundCloudError("La posizione deve rientrare nella durata del brano disponibile.")
            await self._send_event(player, "position", position)
            return f"Posizione » {format_time(position)}"
        if command == "screpeat":
            repeats = {"off": 1, "all": 2, "one": 4}
            if argument.lower() not in repeats:
                raise SoundCloudError(f"Usa {prefix}screpeat off|all|one.")
            repeat = repeats[argument.lower()]
            if not player.number("available_repeat") & repeat:
                raise SoundCloudError("Questa modalità di ripetizione non è disponibile.")
            await self._send_event(player, "repeat", repeat)
            return f"Repeat » {argument.lower()}"
        if command in {"scshuffle", "sclike"}:
            rating = command == "sclike"
            current = player.number("rating") == 5 if rating else player.number("shuffle")
            enabled = toggle_value(argument, int(current))
            if rating and player.number("rating_system") not in {1, 2}:
                raise SoundCloudError("Il player corrente non supporta i like.")
            await self._send_event(player, "rating" if rating else "shuffle", enabled * 5 if rating else enabled)
            return f"{'Like' if rating else 'Shuffle'} » {'on' if enabled else 'off'}"
        raise SoundCloudError(f"Comando sconosciuto. Usa {prefix}soundcloud.")
