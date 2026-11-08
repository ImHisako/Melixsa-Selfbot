"""Backup locale e ripristino del profilo Telegram del proprietario."""
from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import json
from pathlib import Path

from pyrogram import raw, types
from pyrogram.errors import AboutTooLong
from pyrogram.file_id import FileId

from .io_tools import local_io
from .persistence_tools import atomic_write


profile_lock = asyncio.Lock()
DETAIL_FIELDS = ("first_name", "last_name", "bio")


def profile_details(profile) -> dict[str, str]:
    if profile is None or not profile.first_name:
        raise ValueError("Nome del profilo Telegram non disponibile.")
    return {field: getattr(profile, field) or "" for field in DETAIL_FIELDS}


def photo_id(photo) -> int | None:
    return FileId.decode(photo.big_file_id).media_id if photo else None


async def download_photo(client, photo) -> bytes:
    image = await client.download_media(photo.big_file_id, in_memory=True)
    if image is not None:
        with image:
            data = image.getvalue()
        if data:
            return data
    raise ValueError("Impossibile scaricare la foto del profilo da Telegram.")


def photo_stream(image: bytes) -> BytesIO:
    stream = BytesIO(image)
    stream.name = "profilo.jpg"
    return stream


async def stage_photo(client, image: bytes):
    with photo_stream(image) as stream:
        uploaded = await client.save_file(stream)
    if uploaded is None:
        raise RuntimeError("Impossibile preparare la foto profilo per Telegram.")
    return uploaded


async def upload_photo(client, uploaded) -> int:
    result = await client.invoke(raw.functions.photos.UploadProfilePhoto(file=uploaded), retries=1)
    return result.photo.id


def save_backup(path: Path, backup: dict) -> None:
    atomic_write(path, json.dumps(backup, ensure_ascii=False, indent=2) + "\n")


def load_backup(path: Path, owner_id: int) -> tuple[dict, bytes | None]:
    try:
        backup = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("Nessun backup del profilo da ripristinare.") from exc
    except ValueError as exc:
        raise ValueError("Il backup del profilo è danneggiato.") from exc
    try:
        if backup["owner_id"] != owner_id:
            raise ValueError
        details = backup["details"]
        if set(details) != set(DETAIL_FIELDS) or not all(isinstance(value, str) for value in details.values()):
            raise ValueError
        if not details["first_name"]:
            raise ValueError
        for field in ("photo_id", "cloned_photo_id"):
            if backup[field] is not None and (type(backup[field]) is not int or not backup[field]):
                raise ValueError
        image = None if backup["photo"] is None else base64.b64decode(backup["photo"], validate=True)
        if (backup["photo_id"] is None and image is not None) or (backup["photo_id"] is not None and not image):
            raise ValueError
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Il backup del profilo è danneggiato o appartiene a un altro account.") from exc
    return backup, image


async def clone(client, owner, target, path: Path, restore_command: str) -> bool:
    if await local_io(path.exists):
        raise ValueError(f"C'è già un backup da ripristinare. Usa {restore_command} prima di clonare un altro profilo.")
    details = profile_details(target)
    target_photo = target.photo or target.public_photo
    if target_photo is None:
        raise ValueError("L'utente non ha una foto profilo accessibile.")
    image = await download_photo(client, target_photo)
    original = await download_photo(client, owner.photo) if owner.photo else None
    backup = {
        "owner_id": owner.id,
        "details": profile_details(owner),
        "photo_id": photo_id(owner.photo),
        "photo": base64.b64encode(original).decode("ascii") if original else None,
        "cloned_photo_id": None,
    }
    await local_io(save_backup, path, backup)
    bio_copied = True
    try:
        uploaded = await stage_photo(client, image)
        try:
            updated = await client.update_profile(**details)
        except AboutTooLong:
            details.pop("bio")
            updated = await client.update_profile(**details)
            bio_copied = False
        if not updated:
            raise RuntimeError("Telegram non ha confermato l'aggiornamento del profilo.")
        # Il risultato MTProto identifica la foto aggiunta anche se il profilo cambia di nuovo.
        backup["cloned_photo_id"] = await upload_photo(client, uploaded)
        await local_io(save_backup, path, backup)
    except Exception as exc:
        raise RuntimeError(f"Clonazione interrotta. Usa {restore_command} per recuperare il profilo. {exc}") from exc
    return bio_copied


async def find_photo(client, media_id: int):
    async for photo in client.get_chat_photos("me"):
        if photo_id(photo) == media_id:
            return photo
    return None


async def restore(client, owner, path: Path) -> None:
    backup, image = await local_io(load_backup, path, owner.id)
    if not await client.update_profile(**backup["details"]):
        raise RuntimeError("Telegram non ha confermato il ripristino di nome e biografia.")

    current = owner.photo
    cloned_id = backup["cloned_photo_id"]
    if cloned_id is not None:
        cloned = current if photo_id(current) == cloned_id else await find_photo(client, cloned_id)
        if cloned is not None:
            if not await client.delete_profile_photos(cloned.big_file_id):
                raise RuntimeError("Telegram non ha confermato la rimozione della foto clonata.")
            if cloned is current:
                refreshed = await client.get_chat("me")
                profile_details(refreshed)
                current = refreshed.photo

    original_id = backup["photo_id"]
    if photo_id(current) != original_id:
        if image is None:
            raise ValueError("Nome e bio ripristinati. Rimuovi la foto attuale da Telegram e ripeti il comando per completare il ripristino.")
        previous = await find_photo(client, original_id)
        if previous is not None:
            restored = await client.set_profile_photo(photo=types.InputChatPhotoPrevious(previous.big_file_id))
        else:
            with photo_stream(image) as stream:
                restored = await client.set_profile_photo(photo=types.InputChatPhotoStatic(stream))
        if not restored:
            raise RuntimeError("Telegram non ha confermato il ripristino della foto originale.")
    await local_io(path.unlink)
