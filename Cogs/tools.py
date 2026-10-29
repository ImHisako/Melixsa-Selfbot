"""Note, sondaggi, password, calcolatrice e ricerca dei comandi."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    title = f"MELIXSA / {command.upper()}"
    thread_id = getattr(message, "message_thread_id", None)
    if command in {'search', 'allcmds'}:
        page = 1
        query = argument.strip()
        if command == "allcmds":
            page, query = int(argument or "1"), ""
        elif not query:
            raise ValueError(f"Uso: {runtime.state.prefix}search <testo> [pagina]")
        else:
            parts = query.rsplit(maxsplit=1)
            if len(parts) == 2 and parts[1].lstrip("-").isdigit():
                query, page = parts[0], int(parts[1])
        restricted = runtime.shared_command_context.get()
        categories = {
            category: tuple(entry for entry in entries if not restricted or runtime.permitted_command(entry[0], ""))
            for category, entries in runtime.HELP_CATEGORIES.items()
        }
        result = runtime.ghost_tools.command_page(categories, runtime.luna_tools.ALIASES, runtime.state.prefix,
                                                query=query, page=page, minimal=runtime.state.minimal_mode)
        await runtime.respond(message, result, title=title)
    elif command in {'note', 'editnote', 'delnote', 'shownote', 'sendnote', 'notes'}:
        async with runtime.notes_lock:
            result = await runtime.asyncio.to_thread(runtime.notes.execute, command, argument)
        await runtime.respond(message, result, title=title)
    elif command in {'poll', 'cpoll'}:
        parts = [part.strip() for part in argument.split("|")]
        if not 3 <= len(parts) <= 11 or not all(parts) or len(parts[0]) > 300 or any(len(p) > 100 for p in parts[1:]):
            raise ValueError("Usa domanda | opzione | opzione (2-10 opzioni, massimo 100 caratteri ciascuna; domanda fino a 300).")
        if message.chat.type == runtime.enums.ChatType.PRIVATE and command == "cpoll":
            raise ValueError("Il sondaggio non anonimo richiede un gruppo.")
        sent = await client.send_poll(message.chat.id, parts[0], parts[1:], is_anonymous=command == "poll", message_thread_id=thread_id)
        if sent is not None:
            runtime.schedule_delete(sent)
        runtime.console_tools.event("Event", f"Sondaggio inviato | chat={runtime.chat_name(message)}")
    elif command == 'calc':
        await runtime.respond(message, runtime.luna_tools.calculate(argument), title=title)
    elif command == 'passgen':
        await runtime.respond(message, runtime.luna_tools.password(argument), title=title)
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
