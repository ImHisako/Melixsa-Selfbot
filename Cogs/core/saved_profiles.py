"""Profili Telegram con nome, salvati localmente per account."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import unicodedata

from pyrogram.types import InputChatPhotoPrevious

from . import profile_tools
from .io_tools import local_io


def profile_name(value: object) -> str:
    name = unicodedata.normalize("NFC", value.strip()) if isinstance(value, str) else ""
    if not 1 <= len(name) <= 64 or not name.isprintable():
        raise ValueError("Usa un nome profilo da 1 a 64 caratteri stampabili.")
    return name


class SavedProfiles:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "saved-profiles.sqlite3"

    def names(self, account_id: int) -> list[str]:
        if not self.path.is_file():
            return []
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT name FROM profiles WHERE account_id = ? ORDER BY name_key", (account_id,))
            return [name for (name,) in rows]

    def get(self, account_id: int, name: str) -> dict:
        if self.path.is_file():
            with closing(sqlite3.connect(self.path)) as db:
                db.row_factory = sqlite3.Row
                row = db.execute(
                    "SELECT name, first_name, last_name, bio, photo_id, photo FROM profiles "
                    "WHERE account_id = ? AND name_key = ?", (account_id, name.casefold()),
                ).fetchone()
                if row is not None:
                    return dict(row)
        raise ValueError("Profilo salvato inesistente.")

    def _insert(self, account_id: int, name: str, details: dict, media_id: int | None, image: bytes | None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS profiles (
                account_id INTEGER NOT NULL, name_key TEXT NOT NULL, name TEXT NOT NULL,
                first_name TEXT NOT NULL, last_name TEXT NOT NULL, bio TEXT NOT NULL,
                photo_id INTEGER, photo BLOB, PRIMARY KEY (account_id, name_key)
            )""")
            result = db.execute(
                "INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (account_id, name.casefold(), name, details["first_name"], details["last_name"],
                 details["bio"], media_id, image),
            )
            if not result.rowcount:
                raise ValueError("Esiste già un profilo salvato con questo nome.")

    def _update_photo_id(self, account_id: int, name: str, media_id: int) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE profiles SET photo_id = ? WHERE account_id = ? AND name_key = ?",
                       (media_id, account_id, name.casefold()))

    async def save(self, client, value: object) -> str:
        name = profile_name(value)
        async with profile_tools.profile_lock:
            owner = await client.get_chat("me")
            details = profile_tools.profile_details(owner)
            image = await profile_tools.download_photo(client, owner.photo) if owner.photo else None
            await local_io(self._insert, owner.id, name, details, profile_tools.photo_id(owner.photo), image)
        return name

    async def load(self, client, value: object) -> dict:
        name = profile_name(value)
        async with profile_tools.profile_lock:
            owner = await client.get_chat("me")
            current = profile_tools.profile_details(owner)
            saved = await local_io(self.get, owner.id, name)
            details = {field: saved[field] for field in profile_tools.DETAIL_FIELDS}
            previous = uploaded = None
            if saved["photo"] and saved["photo_id"] != profile_tools.photo_id(owner.photo):
                previous = await profile_tools.find_photo(client, saved["photo_id"])
                if previous is None:
                    uploaded = await profile_tools.stage_photo(client, saved["photo"])
            if details != current and not await client.update_profile(**details):
                raise RuntimeError("Telegram non ha confermato l'aggiornamento del profilo.")
            try:
                if previous is not None:
                    photo = InputChatPhotoPrevious(previous.big_file_id)
                    if not await client.set_profile_photo(photo=photo):
                        raise RuntimeError("Telegram non ha confermato la foto profilo.")
                elif uploaded is not None:
                    media_id = await profile_tools.upload_photo(client, uploaded)
                    await local_io(self._update_photo_id, owner.id, name, media_id)
            except Exception as exc:
                raise RuntimeError("Nome e bio applicati. Riprova il caricamento per completare la foto.") from exc
        return saved
