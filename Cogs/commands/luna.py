"""Gestori dei comandi luna di Melixsa."""

from __future__ import annotations

from html import escape
from secrets import randbits

from pyrogram import Client, raw
from pyrogram.types import Message, MessageEntity


async def handle_luna_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .. import runtime

    title = f"MELIXSA / {command.upper()}"
    thread_id = getattr(message, "message_thread_id", None)
    if command in {entry[0] for entry in runtime.luna_tools.CATEGORIES["fun"]}:
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
    elif command in runtime.luna_tools.ANIMATIONS:
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
    elif command in {entry[0] for entry in runtime.luna_tools.CATEGORIES["text"]}:
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
    elif command in {"note", "editnote", "delnote", "shownote", "sendnote", "notes"}:
        async with runtime.notes_lock:
            result = await runtime.asyncio.to_thread(runtime.notes.execute, command, argument)
        await runtime.respond(message, result, title=title)
    elif command in {"poll", "cpoll"}:
        parts = [part.strip() for part in argument.split("|")]
        if not 3 <= len(parts) <= 11 or not all(parts) or len(parts[0]) > 300 or any(len(p) > 100 for p in parts[1:]):
            raise ValueError("Usa domanda | opzione | opzione (2-10 opzioni, massimo 100 caratteri ciascuna; domanda fino a 300).")
        if message.chat.type == runtime.enums.ChatType.PRIVATE and command == "cpoll":
            raise ValueError("Il sondaggio non anonimo richiede un gruppo.")
        sent = await client.send_poll(message.chat.id, parts[0], parts[1:], is_anonymous=command == "poll", message_thread_id=thread_id)
        if sent is not None:
            runtime.schedule_delete(sent)
        runtime.console_tools.event("Event", f"Sondaggio inviato | chat={runtime.chat_name(message)}")
    elif command == "calc":
        await runtime.respond(message, runtime.luna_tools.calculate(argument), title=title)
    elif command == "passgen":
        # Il contenuto generato non viene registrato nei log operativi.
        await runtime.respond(message, runtime.luna_tools.password(argument), title=title)
    elif command in {"name", "bio"}:
        if not argument:
            raise ValueError("Indica il nuovo valore del profilo.")
        if command == "name":
            parts = argument.split("|", 1)
            first, last = parts[0].strip(), parts[1].strip() if len(parts) == 2 else ""
            if not first or len(first) > 64 or len(last) > 64:
                raise ValueError("Nome obbligatorio, massimo 64 caratteri per nome e cognome.")
            await client.update_profile(first_name=first, last_name=last)
        else:
            if len(argument) > 70:
                raise ValueError("Biografia: massimo 70 caratteri.")
            await client.update_profile(bio=argument)
        await runtime.respond(message, "Profilo aggiornato.", title=title)
    elif command == "avatar":
        if argument or getattr(message, "reply_to_message", None):
            user = await runtime.resolve_user(client, message, argument)
        else:
            user = await client.get_me()
        async for photo in client.get_chat_photos(user.id, limit=1):
            sent = await client.send_photo(message.chat.id, photo.file_id, message_thread_id=thread_id)
            if sent is not None:
                runtime.schedule_delete(sent)
            runtime.console_tools.event("Message", f"Avatar inviato | chat={runtime.chat_name(message)} | user={user.id}")
            return
        await runtime.respond(message, "Nessuna foto profilo accessibile.", title=title)
    elif command in {entry[0] for entry in runtime.luna_tools.CATEGORIES["admin"]}:
        if message.chat.type not in {runtime.enums.ChatType.GROUP, runtime.enums.ChatType.SUPERGROUP}:
            raise ValueError("Usa questo comando in un gruppo con i permessi amministratore necessari.")
        if command == "guildname":
            if not argument or len(argument) > 128:
                raise ValueError("Titolo: da 1 a 128 caratteri.")
            await client.set_chat_title(message.chat.id, argument)
        elif command in {"slowmode", "removeslowmode"}:
            seconds = 0 if command == "removeslowmode" else int(argument)
            if seconds not in {0, 10, 30, 60, 300, 900, 3600}:
                raise ValueError("Valori consentiti: 0, 10, 30, 60, 300, 900, 3600 secondi.")
            await client.set_slow_mode(message.chat.id, seconds)
        else:
            user = await runtime.resolve_user(client, message, argument)
            if command in {"ban", "kick"}:
                await client.ban_chat_member(message.chat.id, user.id)
                if command == "kick":
                    await client.unban_chat_member(message.chat.id, user.id)
            elif command == "unban":
                await client.unban_chat_member(message.chat.id, user.id)
            else:
                permissions = runtime.ChatPermissions() if command == "mute" else (await client.get_chat(message.chat.id)).permissions
                if permissions is None:
                    raise ValueError("Permessi predefiniti del gruppo non disponibili.")
                await client.restrict_chat_member(message.chat.id, user.id, permissions)
        await runtime.respond(message, "Operazione Telegram completata.", title=title)
    elif command == "uptime":
        seconds = int(runtime.time.monotonic() - runtime.luna_tools.STARTED)
        await runtime.respond(message, f"Attività » {seconds // 3600}h {(seconds % 3600) // 60}m {seconds % 60}s", title=title)
    elif command == "ping":
        start = runtime.time.perf_counter()
        await client.invoke(raw.functions.Ping(ping_id=randbits(63)), retries=1, timeout=5, sleep_threshold=0)
        elapsed_ms = (runtime.time.perf_counter() - start) * 1000
        await runtime.respond(message, f"Pong!\nTelegram » {elapsed_ms:.2f} ms\nTempo di andata e ritorno al server.", title=title)
    elif command == "about":
        await runtime.respond(message, f"Melixsa Telegram Selfbot\nStile e comandi ispirati a Luna / Nas\nComandi e alias » {len(runtime.COMMANDS - runtime.CATEGORY_COMMANDS)}\nMenu » {runtime.state.prefix}help", title=title)

