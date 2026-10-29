"""Catalogo di sola lettura condiviso con l'help del selfbot."""
from Cogs.core import catalog, luna_tools


CATEGORY_TITLES = {
    "admin": "Amministrazione", "abuse": "Invii e arresto", "animated": "Animazioni",
    "fun": "Divertimento", "text": "Testo", "misc": "Profilo e utilità",
    "mass surveillance": "Monitoraggio", "tools": "Strumenti", "osint": "OSINT",
    "soundcloud": "SoundCloud", "settings": "Impostazioni",
}


def command_catalog():
    aliases = {**luna_tools.ALIASES, "h": "help", "?": "help"}
    categories = []
    for category, entries in catalog.HELP_CATEGORIES.items():
        category_aliases = sorted(alias for alias, target in catalog.HELP_CATEGORY_ALIASES.items() if target == category)
        categories.append({
            "id": category, "title": CATEGORY_TITLES.get(category, category), "aliases": category_aliases,
            "shortcut": category_aliases[0] if " " in category else category,
            "commands": [{
                "name": name, "usage": usage, "description": description,
                "details": catalog.HELP_DETAILS.get(name, description),
                "aliases": sorted(alias for alias, target in aliases.items() if target == name),
            } for name, usage, description in entries],
        })
    return {"categories": categories}
