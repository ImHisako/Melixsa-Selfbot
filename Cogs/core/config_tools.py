"""Carica e conserva le credenziali locali senza esporle nei log."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import MutableMapping
from pathlib import Path


CREDENTIAL_KEYS = ("TELEGRAM_API_ID", "TELEGRAM_API_HASH")
OPTIONAL_KEYS = ("WEBNOWPLAYING_PORT", "GEOSEEER_API_KEY", "LRCLIB_CLIENT_CONTACT", "OSINT_INCLUDE_ADULT")
CONFIG_KEYS = {*CREDENTIAL_KEYS, *OPTIONAL_KEYS}
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Z_][A-Z_0-9]*)\s*=\s*(.*?)\s*$")


def read_values(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        match = ASSIGNMENT.match(line)
        if match is None or match[1] not in CONFIG_KEYS:
            continue
        key, value = match.groups()
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end + 1:].strip() and not value[end + 1:].lstrip().startswith("#")):
                raise ValueError(f"Formato non valido per {key} nel file .env.")
            value = value[1:end]
        else:
            value = value.split(" #", 1)[0].strip()
        values[key] = value
    return values


def save_credentials(path: Path, original: str, credentials: dict[str, str]) -> None:
    lines = []
    written = set()
    for line in original.splitlines():
        match = ASSIGNMENT.match(line)
        if match is not None and match[1] in credentials:
            key = match[1]
            if key not in written:
                lines.append(f"{key}={credentials[key]}")
                written.add(key)
        else:
            lines.append(line)
    lines.extend(f"{key}={credentials[key]}" for key in CREDENTIAL_KEYS if key not in written)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".env.", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write("\n".join(lines) + "\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_credentials(path: Path, environ: MutableMapping[str, str] | None = None) -> tuple[int, str]:
    environment = os.environ if environ is None else environ
    original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    saved = read_values(original)
    credentials = {
        key: (environment.get(key) or saved.get(key, "")).strip()
        for key in CREDENTIAL_KEYS
    }
    if not all(credentials.values()):
        raise ValueError("Imposta TELEGRAM_API_ID e TELEGRAM_API_HASH una volta con set oppure nel file .env, poi avvia run.cmd.")
    api_id = credentials["TELEGRAM_API_ID"]
    api_hash = credentials["TELEGRAM_API_HASH"]
    if not re.fullmatch(r"[0-9]{1,10}", api_id) or not 0 < int(api_id) <= 2147483647:
        raise ValueError("TELEGRAM_API_ID deve essere l'ID numerico valido di my.telegram.org.")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        raise ValueError("TELEGRAM_API_HASH deve essere l'hash di 32 caratteri di my.telegram.org, non il valore di esempio.")
    # Non sostituire le credenziali salvate con valori incompleti o segnaposto.
    if any(saved.get(key) != credentials[key] for key in CREDENTIAL_KEYS):
        save_credentials(path, original, credentials)
    for key in OPTIONAL_KEYS:
        if not environment.get(key) and saved.get(key):
            environment[key] = saved[key]
    return int(api_id), api_hash
