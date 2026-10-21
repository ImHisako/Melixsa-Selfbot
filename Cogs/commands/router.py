"""Gestori dei comandi router di Melixsa."""

from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .. import runtime

    command = runtime.luna_tools.ALIASES.get(command, command)
    chat_id = message.chat.id
    is_group = message.chat.type in {runtime.enums.ChatType.GROUP, runtime.enums.ChatType.SUPERGROUP}
    if command in {"help", "h", "?"}:
        await runtime.send_help(client, message, argument)
    elif command in {"doctor", "errornotify", "logconfig"}:
        from .diagnostics import handle_diagnostics_command

        await handle_diagnostics_command(client, message, command, argument)
    elif command in {"osintjobs", "osintcancel"}:
        from .osint import handle_jobs_command

        await handle_jobs_command(message, command, argument)
    elif command == "access":
        from .access import handle_access_command

        await handle_access_command(client, message, argument)
    elif command in {"spam", "spamstop"}:
        from .abuse import handle_abuse_command

        await handle_abuse_command(client, message, command, argument)
    elif command == "osint" and argument:
        parts = argument.split(maxsplit=1)
        subcommand = runtime.osint_features.SUBCOMMANDS.get(parts[0].lower(), parts[0].lower())
        if subcommand not in runtime.OSINT_COMMANDS:
            await runtime.respond(message, f"Uso » {runtime.state.prefix}osint <comando> [valore]\nMenu » {runtime.state.prefix}osint", title="MELIXSA / OSINT")
            return
        await runtime.handle_osint_command(message, subcommand, parts[1] if len(parts) > 1 else "", client=client)
    elif command in {"soundcloud", "sc"} and argument:
        parts = argument.split(maxsplit=1)
        subcommand = parts[0].lower()
        if not subcommand.startswith("sc"):
            subcommand = f"sc{subcommand}"
        await runtime.handle_soundcloud_command(message, subcommand, parts[1] if len(parts) > 1 else "")
    elif command in runtime.CATEGORY_COMMANDS:
        await runtime.send_help(client, message, command)
    elif command in runtime.SOUNDCLOUD_COMMANDS or command == "sclyrics":
        await runtime.handle_soundcloud_command(message, command, argument)
    elif command in runtime.OSINT_COMMANDS:
        await runtime.handle_osint_command(message, command, argument, client=client)
    elif command == "geosint":
        await runtime.handle_geosint_command(client, message, argument)
    elif command == "autoreact":
        await runtime.handle_autoreact_command(client, message, argument)
    elif command == "anti-login":
        await runtime.handle_anti_login_command(client, message, argument)
    elif command in {"afk", "back", "afkstatus"}:
        await runtime.handle_afk_command(client, message, command, argument)
    elif command in runtime.luna_tools.COMMANDS:
        await runtime.handle_luna_command(client, message, command, argument)
    elif command == "minimal-mode":
        action = argument.lower()
        if action not in {"", "on", "off"}:
            raise ValueError(f"Uso: {runtime.state.prefix}minimal-mode on|off")
        if action:
            async with runtime.state_transaction():
                runtime.state.minimal_mode = action == "on"
        await runtime.respond(message, f"Minimal-mode {'on' if runtime.state.minimal_mode else 'off'}", title="MELIXSA / MINIMAL-MODE")
    elif command == "debug-mode":
        action = argument.lower()
        if action not in {"", "on", "off"}:
            raise ValueError(f"Uso: {runtime.state.prefix}debug-mode on|off")
        if action:
            async with runtime.state_transaction():
                runtime.state.console["debug_mode"] = action == "on"
            runtime.console_tools.configure(runtime.state.console)
        enabled = runtime.state.console.get("debug_mode", False)
        await runtime.respond(message, f"Debug-mode » {'on' if enabled else 'off'}", title="MELIXSA / DEBUG-MODE")
    elif command == "clear":
        if argument:
            raise ValueError(f"Uso: {runtime.state.prefix}clear")
        runtime.console_tools.clear()
        await runtime.respond(message, "Console pulita.", title="MELIXSA / CLEAR")
    elif command in {"console", "timestamp", "spacers", "pgradient", "lgradient"}:
        if command != "console":
            if argument.lower() not in {"on", "off"}:
                raise ValueError(f"Uso: {runtime.state.prefix}{command} on|off")
            async with runtime.state_transaction():
                runtime.state.console[command] = argument.lower() == "on"
            runtime.console_tools.configure(runtime.state.console)
        else:
            runtime.console_tools.banner(runtime.state.prefix, len(runtime.COMMANDS - runtime.CATEGORY_COMMANDS), runtime.state.delete_after)
        await runtime.respond(message, "\n".join(f"{key} » {'on' if value else 'off'}" for key, value in runtime.state.console.items()), title="MELIXSA / CONSOLE")
    elif command == "prefix":
        if not argument:
            await runtime.respond(message, f"Attuale » {runtime.state.prefix}\nCambia » {runtime.state.prefix}prefix !", title="MELIXSA / PREFIX")
            return
        if not runtime.valid_prefix(argument):
            await runtime.respond(message, "Errore » Scegli un solo simbolo stampabile: !, . oppure /.", title="MELIXSA / PREFIX", error=True)
            return
        async with runtime.state_transaction():
            runtime.state.prefix = argument
        await runtime.respond(message, f"Attuale » {runtime.state.prefix}\nMenu » {runtime.state.prefix}help", title="MELIXSA / PREFIX")
    elif command == "deleteafter":
        if not argument:
            await runtime.respond(message, f"Timer » {runtime.state.delete_after} s\nCambia » {runtime.state.prefix}deleteafter 40\nOff » {runtime.state.prefix}deleteafter 0", title="MELIXSA / DELETEAFTER")
            return
        try:
            delay = int(argument)
        except ValueError:
            delay = -1
        if not 0 <= delay <= runtime.MAX_DELETE_AFTER:
            await runtime.respond(message, f"Errore » Inserisci un intero da 0 a {runtime.MAX_DELETE_AFTER} secondi.", title="MELIXSA / DELETEAFTER", error=True)
            return
        async with runtime.state_transaction():
            runtime.state.delete_after = delay
        value = "off" if delay == 0 else f"{delay} s"
        await runtime.respond(message, f"Timer risposte » {value}\nComandi » cancellati subito", title="MELIXSA / DELETEAFTER")
    elif command in {"monitorlist", "stalklist", "sulist"}:
        from .monitoring import send_monitor_list

        await send_monitor_list(client, message, command, argument)
    elif command == "surveillance":
        if not is_group:
            await runtime.respond(message, f"Usa {runtime.state.prefix}surveillance in un gruppo.")
            return
        async with runtime.state_transaction():
            runtime.state.surveillance.add(chat_id)
        await runtime.respond(message, "Monitoraggio del gruppo attivo. Log in data/logs/.")
    elif command == "sustop":
        if not is_group:
            await runtime.respond(message, f"Usa {runtime.state.prefix}sustop in un gruppo.")
            return
        async with runtime.state_transaction():
            runtime.state.surveillance.discard(chat_id)
        await runtime.respond(message, "Monitoraggio del gruppo fermato.")
    elif command in {"stalk", "unstalk", "whois"}:
        user = await runtime.resolve_user(client, message, argument)
        if command == "whois":
            name = " ".join(filter(None, (user.first_name, user.last_name)))
            username = f"@{user.username}" if user.username else "—"
            await runtime.respond(message, f"ID » {user.id}\nNome » {name or '—'}\nUsername » {username}\nBot » {'sì' if user.is_bot else 'no'}", title="MELIXSA / WHOIS")
            return
        async with runtime.state_transaction():
            if command == "stalk":
                runtime.state.stalk.add(user.id)
            else:
                runtime.state.stalk.discard(user.id)
        action = "attivo" if command == "stalk" else "fermato"
        await runtime.respond(message, f"Monitoraggio di {user.id} {action} in tutti i gruppi visibili.")
    elif command == "chatinfo":
        if not is_group:
            await runtime.respond(message, f"Usa {runtime.state.prefix}chatinfo in un gruppo.")
            return
        chat = await client.get_chat(chat_id)
        username = f"@{chat.username}" if chat.username else "—"
        members_count = chat.members_count if chat.members_count is not None else "—"
        await runtime.respond(message, f"Gruppo » {chat.title}\nID » {chat.id}\nUsername » {username}\nMembri » {members_count}", title="MELIXSA / CHATINFO")
    elif command == "status":
        targets = ", ".join(str(user_id) for user_id in sorted(runtime.state.stalk)) or "nessuno"
        timing = "disattivata" if runtime.state.delete_after == 0 else f"{runtime.state.delete_after} secondi"
        if is_group:
            active = "attivo" if chat_id in runtime.state.surveillance else "fermo"
            await runtime.respond(message, f"Prefisso » {runtime.state.prefix}\nTimer » {timing}\nGruppo » {active}\nUtenti » {targets}\nAFK » {'attivo' if runtime.afk.active else 'off'}", title="MELIXSA / STATUS")
        else:
            await runtime.respond(message, f"Prefisso » {runtime.state.prefix}\nTimer » {timing}\nUtenti » {targets}\nAFK » {'attivo' if runtime.afk.active else 'off'}", title="MELIXSA / STATUS")

