"""Gestori dei comandi geosint di Melixsa."""

from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


async def handle_geosint_command(client: Client, message: Message, argument: str) -> None:
    from .. import runtime

    title = "MELIXSA / GEOSINT"
    if argument:
        await runtime.respond(message, f"Uso » {runtime.state.prefix}geosint in risposta a una foto, video o URL del media.", title=title)
        return
    try:
        result = await runtime.geosint_tools.analyze_reply(client, message, runtime.os.environ.get("GEOSEEER_API_KEY", ""))
        chunks = runtime.geosint_tools.result_chunks(result)
    except runtime.geosint_tools.GeoSintError as exc:
        runtime.log_command_error(message, exc, title=title)
        return
    except Exception as exc:
        runtime.log_command_error(message, exc, title=title)
        return
    for index, chunk in enumerate(chunks, 1):
        part_title = title if len(chunks) == 1 else f"{title} / {index} di {len(chunks)}"
        await runtime.respond(message, chunk, title=part_title, auto_delete=False)

