"""Backup espliciti delle preferenze e delle note, senza sessioni o credenziali."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import uuid4

from . import persistence_tools


SETTINGS_FIELDS = (
    "prefix", "delete_after", "autoreact", "autoreact_emojis", "autoreact_count",
    "minimal_mode", "console", "log_max_bytes", "log_backups", "log_retention_days", "error_notify",
)
MAX_BACKUPS = 30
MAX_BYTES = 2_000_000


def settings_payload(state) -> dict:
    payload = {name: deepcopy(getattr(state, name)) for name in SETTINGS_FIELDS}
    payload["autoreact_emojis"] = list(payload["autoreact_emojis"])
    return payload


def validate_notes(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict) or len(raw) > 100 or any(
        not isinstance(name, str) or not 1 <= len(name) <= 64
        or not isinstance(text, str) or not 1 <= len(text) <= 3000
        for name, text in raw.items()
    ):
        raise ValueError("Note non valide: massimo 100, nomi di 1-64 caratteri e testi di 1-3000.")
    return raw.copy()


def read_json(path: Path) -> object:
    with path.open("rb") as source:
        content = source.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("File troppo grande (massimo 2 MB).")
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("File JSON non valido.") from exc


def read_notes(path: Path) -> dict[str, str]:
    try:
        return validate_notes(read_json(path))
    except FileNotFoundError:
        return {}


class BackupStore:
    def __init__(self, directory: Path, state_factory):
        self.directory = directory
        self.state_factory = state_factory

    def path(self, name: str) -> Path:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name) or re.fullmatch(
            r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", name
        ):
            raise ValueError("Nome backup: 1-64 lettere, cifre, _ o -, senza percorsi o nomi riservati.")
        path = self.directory / f"{name}.json"
        if path.is_symlink() or path.resolve().parent != self.directory.resolve():
            raise ValueError("Percorso backup non valido.")
        return path

    def names(self) -> list[str]:
        result = []
        for path in self.directory.glob("*.json"):
            try:
                if self.path(path.stem).is_file():
                    result.append(path.stem)
            except ValueError:
                continue
        return sorted(result)

    def validate(self, raw: object) -> dict:
        if not isinstance(raw, dict) or set(raw) != {"format", "version", "created_at", "settings", "notes"}:
            raise ValueError("Formato backup non valido.")
        if raw["format"] != "melixsa-preferences" or type(raw["version"]) is not int or raw["version"] != 1:
            raise ValueError("Versione backup non supportata.")
        try:
            created = datetime.fromisoformat(raw["created_at"])
            if created.tzinfo is None:
                raise ValueError("Timezone mancante")
        except (TypeError, ValueError) as exc:
            raise ValueError("Data backup non valida.") from exc
        settings = raw["settings"]
        if not isinstance(settings, dict) or set(settings) != set(SETTINGS_FIELDS):
            raise ValueError("Preferenze backup incomplete o non consentite.")
        normalized = settings_payload(self.state_factory(settings))
        # Il caricamento normale tollera vecchie impostazioni; un ripristino deve essere esatto.
        if json.dumps(normalized, sort_keys=True) != json.dumps(settings, sort_keys=True):
            raise ValueError("Preferenze backup non valide.")
        validate_notes(raw["notes"])
        return deepcopy(raw)

    def create(self, settings: dict, notes: dict, name: str = "") -> str:
        name = name or f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
        path = self.path(name)
        if path.exists():
            raise ValueError("Backup già esistente: scegli un altro nome.")
        if len(self.names()) >= MAX_BACKUPS:
            raise ValueError("Limite di 30 backup: elimina una copia con backup delete <nome>.")
        payload = self.validate({
            "format": "melixsa-preferences", "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "settings": settings, "notes": notes,
        })
        persistence_tools.atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return name

    def load(self, name: str) -> dict:
        try:
            return self.validate(read_json(self.path(name)))
        except FileNotFoundError as exc:
            raise ValueError("Backup inesistente.") from exc

    def delete(self, name: str) -> None:
        try:
            self.path(name).unlink()
        except FileNotFoundError as exc:
            raise ValueError("Backup inesistente.") from exc

    @staticmethod
    def summary(name: str, payload: dict) -> str:
        settings = payload["settings"]
        return "\n".join((f"Nome » {name}", f"Data UTC » {payload['created_at']}",
                          f"Prefisso » {settings['prefix']}", f"Timer » {settings['delete_after']} s",
                          f"Note » {len(payload['notes'])}",
                          "Contenuto » Preferenze generali e note locali"))
