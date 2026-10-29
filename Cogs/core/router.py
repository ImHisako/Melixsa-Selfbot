"""Instrada i comandi alla sezione definita dal catalogo dell'help."""
from __future__ import annotations

from importlib import import_module

from .. import SECTION_MODULES
from .pagination import is_page_argument
from .catalog import COMMAND_CATEGORIES

SECTIONS = {category: import_module(f"..{name}", __package__)
            for category, name in SECTION_MODULES.items()}


async def handle_command(client, message, command: str, argument: str) -> None:
    from . import runtime

    command = runtime.luna_tools.ALIASES.get(command, command)
    if command in {"help", "h", "?"}:
        await SECTIONS["settings"].handle_command(client, message, command, argument)
    elif command == "osint" and argument and not is_page_argument(argument):
        await SECTIONS["osint"].handle_command(client, message, command, argument)
    elif command in {"soundcloud", "sc"} and argument and not is_page_argument(argument):
        await SECTIONS["soundcloud"].handle_command(client, message, command, argument)
    elif command in runtime.CATEGORY_COMMANDS:
        topic = f"{command} {argument}".rstrip()
        await runtime.send_help(client, message, topic)
    elif command in COMMAND_CATEGORIES:
        section = SECTIONS[COMMAND_CATEGORIES[command]]
        await section.handle_command(client, message, command, argument)
    else:
        raise ValueError(f"Comando sconosciuto: {command}")
