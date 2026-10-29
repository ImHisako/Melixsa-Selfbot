"""Giochi, interazioni e reazioni automatiche."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message, MessageEntity


async def handle_autoreact_command(client: Client, message: Message, argument: str) -> None:
    from .core import runtime

    parts = argument.split(maxsplit=1)
    action = parts[0].lower() if parts else ""
    value = parts[1] if len(parts) == 2 else ""
    if action not in {"", "status", "on", "off", "emoji", "count"} or (value and action not in {"emoji", "count"}):
        await runtime.respond(message, f"Uso » {runtime.state.prefix}autoreact on|off\nEmoji » {runtime.state.prefix}autoreact emoji 👍 ❤️ 🔥\nQuantità » {runtime.state.prefix}autoreact count 1|2|3", title="MELIXSA / AUTOREACT")
        return
    if action in {"on", "off", "emoji", "count"}:
        async with runtime.state_transaction():
            enabled, emojis, count = runtime.state.autoreact, runtime.state.autoreact_emojis, runtime.state.autoreact_count
            if action == "emoji":
                emojis = runtime.autoreact_tools.parse_emojis(value)
                count = min(count, len(emojis))
                # Risolvi la nuova lista prima di salvarla, anche se autoreact è spento.
                await runtime.auto_reactor.prepare(client, refresh=True, emojis=emojis)
            elif action == "count":
                if value not in {"1", "2", "3"} or int(value) > len(emojis):
                    raise ValueError(f"Scegli una quantità da 1 a {len(emojis)}. Per usarne di più, aggiungi prima le emoji alla lista.")
                count = int(value)
                if enabled:
                    await runtime.auto_reactor.prepare(client, refresh=True, emojis=emojis[:count])
            else:
                enabled = action == "on"
                if enabled:
                    await runtime.auto_reactor.prepare(client, refresh=True, emojis=emojis[:count])
            runtime.state.autoreact, runtime.state.autoreact_emojis, runtime.state.autoreact_count = enabled, emojis, count
        runtime.auto_reactor.chat_retry_after.clear()
        runtime.auto_reactor.last_error = ""
    text = (
        f"Stato » {'attivo' if runtime.state.autoreact else 'off'}\n"
        f"Lista emoji » {' '.join(runtime.state.autoreact_emojis)}\n"
        f"Quantità » {runtime.state.autoreact_count}\n"
        f"Reazioni per messaggio » {' '.join(runtime.state.autoreact_emojis[:runtime.state.autoreact_count])}\n"
        f"Scegli emoji » {runtime.state.prefix}autoreact emoji 👍 ❤️ 🔥\n"
        f"Scegli quantità » {runtime.state.prefix}autoreact count 1|2|3\n"
        f"Attiva / ferma » {runtime.state.prefix}autoreact on|off\n"
        "Limiti » Telegram decide quali reazioni e quante consente nella chat."
    )
    if runtime.auto_reactor.last_error:
        text += f"\nUltimo problema » {runtime.auto_reactor.last_error}"
    await runtime.respond(message, text, title="MELIXSA / AUTOREACT")

async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    title = f"MELIXSA / {command.upper()}"
    thread_id = getattr(message, "message_thread_id", None)
    if command == "autoreact":
        await runtime.handle_autoreact_command(client, message, argument)
    elif command == "rps":
        await runtime.respond(message, runtime.ghost_tools.rps(argument), title=title)
    elif command in {entry[0] for entry in runtime.luna_tools.CATEGORIES['fun']}:
        reply = getattr(message, "reply_to_message", None)
        user = getattr(reply, "from_user", None) if reply else None
        target = argument or (getattr(user, "first_name", "") if user else "") or "te"
        if command in runtime.luna_tools.GIF_COMMANDS | {"iq", "gay", "love", "dick", "boobs"}:
            if command in {"dick", "boobs"} or argument.startswith("@") or argument.lstrip("-").isdigit():
                user = await runtime.resolve_user(client, message, argument)
            elif argument:
                user = None
            elif user is None:
                user = getattr(message, "from_user", None)
            if user is not None:
                target = runtime.user_label(user)
        else:
            user = None
        if len(target) > 1500:
            raise ValueError("Usa al massimo 1500 caratteri.")
        result = runtime.luna_tools.fun_result(command, argument, target)
        if command in runtime.luna_tools.GIF_COMMANDS:
            try:
                url, _ = await runtime.asyncio.to_thread(runtime.luna_tools.reaction_gif, command)
            except ValueError as exc:
                runtime.console_tools.event("Error", f"{command} | {exc}", error=True)
                await runtime.respond(message, result + "\nGIF non disponibile.", title=title, mention_user=user)
                return
            # Caption Telegram <= 1024 unità UTF-16; non troncare surrogate pairs.
            caption = result[:300]
            caption_entities = []
            if user is not None:
                start = caption.find(target)
                if start >= 0:
                    caption_entities.append(MessageEntity(
                        type=runtime.enums.MessageEntityType.TEXT_MENTION,
                        offset=len(caption[:start].encode("utf-16-le")) // 2,
                        length=len(target.encode("utf-16-le")) // 2, user=user,
                    ))
            sent = await client.send_animation(message.chat.id, url, caption=caption,
                                                caption_entities=caption_entities,
                                                parse_mode=runtime.enums.ParseMode.DISABLED, message_thread_id=thread_id)
            if sent is not None:
                runtime.schedule_delete(sent)
            runtime.console_tools.event("Message", f"GIF {command} | chat={runtime.chat_name(message)}")
        else:
            await runtime.respond(message, result, title=title, mention_user=user)
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
