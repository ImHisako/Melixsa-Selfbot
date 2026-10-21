"""Gestori dei comandi soundcloud di Melixsa."""

from __future__ import annotations

from pyrogram.types import Message


async def handle_soundcloud_command(message: Message, command: str, argument: str) -> None:
    from .. import runtime

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

