"""Gestori dei comandi help di Melixsa."""

from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


def help_text(prefix: str, topic: str = "") -> str:
    """Crea il menu testuale in stile Luna con i soli comandi di Melixsa."""
    from .. import runtime

    minimal = runtime.state.minimal_mode
    def menu_line(syntax: str, description: str) -> str:
        return syntax if minimal else f"{syntax} » {description}"

    topic = topic.strip().lower()
    topic = topic.removeprefix(prefix)
    topic = {"h": "help", "?": "help"}.get(topic, topic)
    topic = runtime.HELP_CATEGORY_ALIASES.get(topic, topic)
    topic = runtime.luna_tools.ALIASES.get(topic, topic)
    restricted = runtime.shared_command_context.get()
    categories = {
        category: tuple(entry for entry in entries if not restricted or runtime.permitted_command(entry[0], ""))
        for category, entries in runtime.HELP_CATEGORIES.items()
        if not restricted or runtime.permitted_command(category, "")
    }
    if restricted and topic and not runtime.permitted_command(topic, ""):
        return "[ MELIXSA / HELP ]\nVoce non disponibile."
    if not topic:
        lines = ["[ MELIXSA ]"] + [menu_line(
            f"{prefix}{'mass' if category == 'mass surveillance' else category}",
            {"soundcloud": "SoundCloud", "osint": "OSINT"}.get(category, category.title()),
        ) for category in categories] + [menu_line(f"{prefix}help [comando]", "Dettagli")]
    elif topic in runtime.HELP_CATEGORIES:
        lines = [f"[ MELIXSA / {topic.upper()} ]"]
        if not categories[topic]:
            lines.append("Nessun comando disponibile")
        else:
            for name, usage, description in categories[topic]:
                syntax = f"{prefix}{name} {usage}".rstrip()
                lines.append(menu_line(syntax, description))
    else:
        entry = next(
            ((category, name, usage, description)
             for category, entries in categories.items()
             for name, usage, description in entries if name == topic),
            None,
        )
        if entry is None:
            return f"[ MELIXSA / HELP ]\nVoce sconosciuta: {topic}\n{menu_line(f'{prefix}help', 'Menu')}"
        _, name, usage, description = entry
        syntax = f"{prefix}{name} {usage}".rstrip()
        lines = [
            f"[ MELIXSA / {name.upper()} ]",
            menu_line(syntax, description),
        ]
        if not minimal:
            lines.append(runtime.HELP_DETAILS[name])
    return "\n".join(lines)


async def send_help(client: Client, message: Message, topic: str = "") -> None:
    from .. import runtime

    text = runtime.help_text(runtime.state.prefix, topic)
    header, _, commands = text.partition("\n")
    text = f"{header}\n{commands}"
    header_entity = runtime.pre_entity(header)
    header_entity.language = "lua"
    commands_entity = runtime.pre_entity(commands)
    commands_entity.offset = len(f"{header}\n".encode("utf-16-le")) // 2
    sent = await client.send_message(
        message.chat.id,
        text,
        parse_mode=runtime.enums.ParseMode.DISABLED,
        entities=[header_entity, commands_entity],
        message_thread_id=message.message_thread_id,
    )
    if sent is None:
        raise RuntimeError("Telegram non ha confermato l'invio del menu.")
    runtime.schedule_delete(sent)

