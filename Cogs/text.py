"""Trasformazioni del testo, codifiche, JSON e blocchi di codice."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message, MessageEntity


async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    title = f"MELIXSA / {command.upper()}"
    if command in {entry[0] for entry in runtime.luna_tools.CATEGORIES['text']}:
        text = runtime.luna_tools.input_text(message, argument)
        styles = {"bold": runtime.enums.MessageEntityType.BOLD, "italic": runtime.enums.MessageEntityType.ITALIC,
                  "underline": runtime.enums.MessageEntityType.UNDERLINE, "strike": runtime.enums.MessageEntityType.STRIKETHROUGH,
                  "spoiler": runtime.enums.MessageEntityType.SPOILER}
        if command in styles:
            sent = await message.answer(text, parse_mode=runtime.enums.ParseMode.DISABLED,
                                        entities=[MessageEntity(type=styles[command], offset=0, length=len(text.encode("utf-16-le")) // 2)])
            if sent is not None:
                runtime.schedule_delete(sent)
            runtime.console_tools.event("Message", f"Testo {command} | chat={runtime.chat_name(message)}")
        else:
            if command == "ascii":
                from pyfiglet import Figlet
                if len(text) > 60:
                    raise ValueError("ASCII: usa al massimo 60 caratteri.")
                result = Figlet(font="small", width=60).renderText(text)
            else:
                result = runtime.luna_tools.transform(command, text)
            await runtime.respond(message, result, title=title)
    elif command in {'codeblock', 'json'} | set(runtime.ghost_tools.CODE_LANGUAGES):
        reply = getattr(message, "reply_to_message", None)
        reply_text = (getattr(reply, "text", None) or getattr(reply, "caption", None) or "") if reply else ""
        language, text = runtime.ghost_tools.format_code(command, argument, reply_text)
        entity = runtime.pre_entity(text)
        entity.language = language
        sent = await message.answer(text, parse_mode=runtime.enums.ParseMode.DISABLED, entities=[entity])
        if sent is not None:
            runtime.schedule_delete(sent)
        runtime.console_tools.event("Message", f"Codice {language} | chat={runtime.chat_name(message)}")
        return
    elif command == 'shrug':
        if argument:
            raise ValueError(f"Uso: {runtime.state.prefix}shrug")
        result = r"¯\_(ツ)_/¯"
        await runtime.respond(message, result, title=title)
    elif command in runtime.ghost_tools.COMMANDS:
        result = runtime.ghost_tools.transform(command, runtime.luna_tools.input_text(message, argument))
        await runtime.respond(message, result, title=title)
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
