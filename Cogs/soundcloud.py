"""Controllo SoundCloud e testi sincronizzati."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


async def handle_soundcloud_command(message: Message, command: str, argument: str) -> None:
    from .core import runtime

    if command == "sclyrics":
        await runtime.handle_lyrics_command(message, argument)
        return
    try:
        result = await runtime.soundcloud.execute(command, argument, runtime.state.prefix)
    except runtime.soundcloud_tools.SoundCloudError as exc:
        runtime.log_command_error(message, exc, title="MELIXSA / SOUNDCLOUD")
        return
    except Exception as exc:
        runtime.console_tools.event("Error", f"SoundCloud {command}: {exc}", error=True)
        return
    await runtime.respond(message, result, title="MELIXSA / SOUNDCLOUD")

async def handle_lyrics_command(message: Message, argument: str) -> None:
    from .core import runtime

    action = argument.strip().lower()
    title = "MELIXSA / SOUNDCLOUD LYRICS"
    if action not in {"", "status", "on", "off"}:
        await runtime.respond(message, f"Uso » {runtime.state.prefix}sclyrics on|off|status", title=title)
        return
    async def send_line(text):
        # L'intestazione impedisce di interpretare il testo esterno come comando.
        await runtime.respond(message, text, title="MELIXSA / LYRICS")
    async def notify(text):
        await runtime.respond(message, text, title=title)
    async with runtime.lyrics.lock:
        if action == "on":
            try:
                runtime.lyrics_tools.client_user_agent()
                await runtime.soundcloud.start()
                destination = (message.chat.id, getattr(message, "message_thread_id", None))
                await runtime.lyrics.start(destination, send_line, notify)
            except (runtime.soundcloud_tools.SoundCloudError, runtime.lyrics_tools.LyricsError) as exc:
                if not runtime.lyrics.running:
                    runtime.lyrics.status = f"fermo: {exc}"
                runtime.log_command_error(message, exc, title=title)
                return
        elif action == "off":
            await runtime.lyrics.stop()
        destination = runtime.lyrics.destination[0] if runtime.lyrics.destination else "—"
        try:
            runtime.soundcloud.active_player()
            player_status = "collegato"
        except runtime.soundcloud_tools.SoundCloudError as exc:
            player_status = str(exc)
        status = runtime.lyrics.status
        if not runtime.lyrics.running and status != "off":
            status = f"fermo\nUltimo esito » {status}"
        next_action = f"Ferma » {runtime.state.prefix}sclyrics off" if runtime.lyrics.running else f"Avvia » {runtime.state.prefix}sclyrics on"
        await notify(f"Stato » {status}\nPlayer » {player_status}\nChat » {destination}\n{next_action}")

async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    if command in {"soundcloud", "sc"}:
        parts = argument.split(maxsplit=1)
        subcommand = parts[0].lower()
        if not subcommand.startswith("sc"):
            subcommand = f"sc{subcommand}"
        await runtime.handle_soundcloud_command(message, subcommand, parts[1] if len(parts) > 1 else "")
    elif command in runtime.SOUNDCLOUD_COMMANDS or command == "sclyrics":
        await runtime.handle_soundcloud_command(message, command, argument)
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
