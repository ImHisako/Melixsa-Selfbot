"""Pagine dei menu con limiti di righe e di lunghezza UTF-16."""
from __future__ import annotations

import re

MAX_ROWS = 12
MAX_UNITS = 3000


def is_page_argument(value: str) -> bool:
    return re.fullmatch(r"-?[0-9]+", value.strip()) is not None


def split_help_argument(value: str, prefix: str) -> tuple[str, int]:
    value = value.strip().removeprefix(prefix)
    parts = value.rsplit(maxsplit=1)
    page = 1
    if parts and is_page_argument(parts[-1]):
        if len(parts[-1]) > 6 or int(parts[-1]) < 1:
            raise ValueError("Pagina non valida: usa un numero intero da 1 in poi.")
        page = int(parts[-1])
        value = parts[0] if len(parts) == 2 else ""
    if len(value) > 100:
        raise ValueError("Voce del menu troppo lunga (massimo 100 caratteri).")
    return value, page


def paginate_lines(lines, *, max_rows: int = MAX_ROWS, max_units: int = MAX_UNITS) -> list[list[str]]:
    if max_rows < 1 or max_units < 2:
        raise ValueError("Limiti di paginazione non validi.")
    pages: list[list[str]] = [[]]
    size = 0
    for line in lines:
        # Una singola riga estesa viene spezzata senza tagliare un carattere Unicode.
        parts = []
        part, length = "", 0
        for character in line:
            units = len(character.encode("utf-16-le")) // 2
            if length + units > max_units:
                parts.append(part)
                part, length = "", 0
            part += character
            length += units
        parts.append(part)
        for part in parts:
            length = len(part.encode("utf-16-le")) // 2
            separator = bool(pages[-1])
            if pages[-1] and (len(pages[-1]) >= max_rows or size + separator + length > max_units):
                pages.append([])
                size, separator = 0, False
            pages[-1].append(part)
            size += separator + length
    return pages


def navigation(command: str, page: int, total: int) -> list[str]:
    links = []
    if page > 1:
        links.append(f"Precedente: {command} {page - 1}")
    if page < total:
        links.append(f"Successiva: {command} {page + 1}")
    return links
