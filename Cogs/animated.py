"""Animazioni dei messaggi Telegram."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message
from html import escape

async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    title = f"MELIXSA / {command.upper()}"
    if command in runtime.luna_tools.ANIMATIONS:
        if message.chat.id in runtime.animation_chats:
            raise ValueError("Un'animazione è già attiva in questa chat.")
        if len(argument) > 200:
            raise ValueError("Testo del gatto: massimo 200 caratteri.")
        runtime.animation_chats.add(message.chat.id)
        try:
            frames = runtime.luna_tools.ANIMATIONS[command]
            panel = f"[ {title} ]\n{frames[0].format(text=argument or 'Ciao!')}"
            sent = await message.answer(panel, parse_mode=runtime.enums.ParseMode.DISABLED, entities=[runtime.pre_entity(panel)])
            if sent is None:
                raise RuntimeError("Telegram non ha confermato l'animazione.")
            try:
                for frame in frames[1:]:
                    await runtime.asyncio.sleep(2)
                    panel = f"[ {title} ]\n{frame.format(text=argument or 'Ciao!')}"
                    # Kurigram azzera le entità esplicite in edit_message_text:
                    # ricrea il PRE dal markup a ogni modifica. Escape conserva
                    # letterali il testo utente e i simboli delle animazioni.
                    await sent.edit_text(
                        f'<pre language="ini">{escape(panel)}</pre>',
                        parse_mode=runtime.enums.ParseMode.HTML,
                    )
            finally:
                runtime.schedule_delete(sent)
            runtime.console_tools.event("Event", f"Animazione {command} | chat={runtime.chat_name(message)} | completata")
        finally:
            runtime.animation_chats.discard(message.chat.id)
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
