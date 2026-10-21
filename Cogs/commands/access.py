"""Permessi per i comandi inviati da altri utenti Telegram."""

from __future__ import annotations

from pyrogram.errors import RPCError

OWNER_CATEGORIES = {"settings", "abuse"}


def access_user_label(user) -> str:
    name = " ".join(filter(None, (getattr(user, "first_name", None), getattr(user, "last_name", None))))
    name = " ".join(name.split()) or "Nome non disponibile"
    return f"{user.id} ({name})"


def default_shared_commands() -> set[str]:
    from ..catalog import HELP_CATEGORIES

    return {"help"} | {
        name for category, entries in HELP_CATEGORIES.items()
        if category not in OWNER_CATEGORIES | {"soundcloud", "misc"}
        for name, _, _ in entries
    }


def canonical_command(command: str) -> str:
    from .. import runtime

    command = command.lower().removeprefix(runtime.state.prefix)
    command = {"h": "help", "?": "help"}.get(command, command)
    return runtime.luna_tools.ALIASES.get(command, command)


def shareable_commands() -> set[str]:
    from .. import runtime

    reserved = {name for category in OWNER_CATEGORIES for name, _, _ in runtime.HELP_CATEGORIES[category]}
    return {canonical_command(name) for name in runtime.COMMANDS - runtime.CATEGORY_COMMANDS} - (reserved - {"help"})


def permitted_command(command: str, argument: str) -> bool:
    from .. import runtime

    command = canonical_command(command)
    if command == "help" and argument:
        return permitted_command(argument.strip().lower().removeprefix(runtime.state.prefix), "")
    category = runtime.HELP_CATEGORY_ALIASES.get(command, command)
    if category in OWNER_CATEGORIES:
        return False
    # I menu richiedono help e almeno un comando della categoria abilitato.
    if command == "osint" and argument:
        head = argument.split(maxsplit=1)[0].lower()
        command = runtime.osint_features.SUBCOMMANDS.get(head, head)
    elif command in {"soundcloud", "sc"} and argument:
        command = argument.split(maxsplit=1)[0].lower()
        if not command.startswith("sc"):
            command = f"sc{command}"
    elif command in runtime.CATEGORY_COMMANDS:
        return "help" in runtime.state.shared_commands and any(
            permitted_command(name, "") for name, _, _ in runtime.HELP_CATEGORIES[category]
        )
    return command in runtime.state.shared_commands and command in shareable_commands()


async def handle_access_command(client, message, argument: str) -> None:
    from .. import runtime

    parts = argument.split(maxsplit=1)
    action = parts[0].lower() if parts else ""
    value = parts[1] if len(parts) > 1 else ""
    prefix = runtime.state.prefix
    if action in {"", "list"} and not value:
        user_ids = sorted(runtime.state.command_users)
        labels = {user_id: f"{user_id} (Nome non disponibile)" for user_id in user_ids}
        for start in range(0, len(user_ids), 200):
            try:
                resolved = await client.get_users(user_ids[start:start + 200])
            except RPCError:
                break
            for user in resolved:
                if user.id in labels:
                    labels[user.id] = access_user_label(user)
        users = "\n".join(labels.values()) or "nessuno"
        command_count = len(runtime.state.shared_commands & shareable_commands())
        text = "\n".join((
            f"{prefix}access add <@utente|ID> » Autorizza una persona (anche in risposta)",
            f"{prefix}access remove <@utente|ID> » Revoca una persona (anche in risposta)",
            f"{prefix}access allow <comando|categoria> » Abilita comandi per le persone autorizzate",
            f"{prefix}access block <comando|categoria> » Disabilita comandi",
            f"{prefix}access list » Mostra permessi",
            f"Utenti » {users}", f"Comandi abilitati » {command_count}",
            "Menu disponibili solo per categorie abilitate. Settings e abuse riservati al proprietario.",
            "Base » Tutti i comandi tranne settings, abuse, soundcloud e misc (help incluso).",
        ))
        await runtime.respond(message, text, title="MELIXSA / ACCESS")
        return
    if action not in {"add", "remove", "allow", "block"}:
        raise ValueError(f"Uso: {prefix}access")
    if action in {"add", "remove"}:
        user = await runtime.resolve_user(client, message, value)
        if user.is_bot or user.id <= 0:
            raise ValueError("Scegli un utente Telegram, non un bot.")
        target = user.id
        targets = {target}
        field = "command_users"
    else:
        target = value.strip().lower().removeprefix(prefix)
        category = runtime.HELP_CATEGORY_ALIASES.get(target, target)
        if category in runtime.HELP_CATEGORIES:
            if category in OWNER_CATEGORIES:
                raise ValueError(f"La categoria {category} resta riservata al proprietario; puoi gestire help singolarmente.")
            targets = {canonical_command(name) for name, _, _ in runtime.HELP_CATEGORIES[category]} & shareable_commands()
        else:
            target = canonical_command(target)
            if not target or target not in shareable_commands():
                raise ValueError("Comando o categoria sconosciuti oppure riservati al proprietario.")
            targets = {target}
        field = "shared_commands"
    async with runtime.state_transaction():
        previous = getattr(runtime.state, field).copy()
        updated = previous.copy()
        if action in {"add", "allow"}:
            updated.update(targets)
        else:
            updated.difference_update(targets)
        setattr(runtime.state, field, updated)
    label = access_user_label(user) if action in {"add", "remove"} else target
    await runtime.respond(message, f"{'Abilitato' if action in {'add', 'allow'} else 'Revocato'} » {label}", title="MELIXSA / ACCESS")
