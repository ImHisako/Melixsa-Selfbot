"""Analisi GeoSeeer su un media scelto esplicitamente tramite risposta."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import re
from urllib.parse import urlsplit


ENDPOINT = "https://geoseeer.com/api/v1/analyze"
MAX_MEDIA_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class GeoSintError(ValueError):
    """Errore presentabile senza includere credenziali o risposte HTTP grezze."""


def http_error_message(status: int, raw: bytes) -> str:
    body = raw.decode("utf-8", errors="replace").lower()
    # Classifica il problema senza inoltrare risposte grezze, chiavi o altri dati.
    if status == 403:
        if "browser's signature" in body or ("cloudflare" in body and "1010" in body):
            return (
                "GeoSeeer ha bloccato la firma del client (HTTP 403 / Cloudflare 1010). "
                "Non è una conferma che la chiave API sia errata. "
                "Contatta l'assistenza GeoSeeer per autorizzare l'accesso del client all'API."
            )
        if "cloudflare" in body and ("1020" in body or "challenge" in body or "access denied" in body):
            return "Accesso all'API bloccato dalla protezione Cloudflare (HTTP 403). Contatta l'assistenza GeoSeeer."
        return "GeoSeeer ha negato la richiesta (HTTP 403). Verifica piano e autorizzazioni API; il comando usa già la modalità fast."
    return {
        401: "Chiave GEOSEEER_API_KEY non valida.",
        402: "Credito GeoSeeer esaurito.",
        413: "Media troppo grande per GeoSeeer.",
        429: "Limite richieste GeoSeeer raggiunto; riprova più tardi.",
    }.get(status, f"GeoSeeer ha restituito HTTP {status}; analisi non completata.")


def read_response(response, limit: int) -> bytes:
    data = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        data.extend(chunk[:limit - len(data)])
        if len(data) >= limit:
            break
    return bytes(data)


def analyze(api_key: str, *, media: bytes | None = None, mime: str = "", url: str = "") -> dict:
    # Import locale: mantiene il riavvio automatico con .venv di selfbot.py.
    import requests

    headers = {"X-API-Key": api_key.strip(), "Accept": "application/json"}
    if media is not None:
        extension = mimetypes.guess_extension(mime) or ""
        # Il nome del file originale non viene inviato al servizio.
        payload = {"data": {"analysis_mode": "fast"}, "files": {"file": (f"media{extension}", media, mime)}}
    else:
        payload = {"json": {"url": url, "analysis_mode": "fast", "stream": False}}
    try:
        # Client dell'esempio ufficiale GeoSeeer, con le sue intestazioni standard.
        # Nessun retry automatico: una seconda richiesta potrebbe consumare altro credito.
        with requests.post(ENDPOINT, headers=headers, timeout=(15, 180),
                           allow_redirects=False, stream=True, **payload) as response:
            if not 200 <= response.status_code < 300:
                raise GeoSintError(http_error_message(response.status_code, read_response(response, 16384)))
            raw = read_response(response, MAX_RESPONSE_BYTES + 1)
    except (requests.RequestException, TimeoutError, OSError):
        raise GeoSintError("GeoSeeer non raggiungibile o tempo scaduto. Nessun nuovo tentativo automatico.") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise GeoSintError("Risposta GeoSeeer troppo grande da elaborare.")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise GeoSintError("GeoSeeer ha restituito una risposta JSON non valida.") from None
    if not isinstance(result, dict) or result.get("status") != "success" or not isinstance(result.get("locations"), list):
        raise GeoSintError("GeoSeeer non ha restituito un'analisi valida. Controlla media, chiave e credito.")
    return result


def media_url(message) -> str:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    urls = re.findall(r"https?://[^\s<>]+", text)
    for entity in (getattr(message, "entities", None) or getattr(message, "caption_entities", None) or []):
        if getattr(entity, "url", None):
            urls.append(entity.url)
    urls = list(dict.fromkeys(urls))
    if len(urls) != 1:
        raise GeoSintError("Rispondi a una foto, un video oppure un messaggio con un solo URL del media.")
    try:
        parsed = urlsplit(urls[0])
        valid = parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username and not parsed.password
    except ValueError:
        valid = False
    if not valid:
        raise GeoSintError("Il link del media deve essere un URL HTTP o HTTPS valido.")
    return urls[0]


async def analyze_reply(client, message, api_key: str) -> dict:
    reply = getattr(message, "reply_to_message", None)
    if reply is None and getattr(message, "reply_to_message_id", None):
        reply = await client.get_messages(message.chat.id, message.reply_to_message_id)
    if reply is None or getattr(reply, "empty", False):
        raise GeoSintError("Usa geosint rispondendo al messaggio da analizzare.")
    if not api_key.strip():
        raise GeoSintError("Aggiungi GEOSEEER_API_KEY=la_tua_chiave nel file .env e riavvia il selfbot.")
    media = None
    mime = ""
    for kind, default in (("photo", "image/jpeg"), ("video", "video/mp4"), ("animation", "video/mp4"), ("document", "")):
        candidate = getattr(reply, kind, None)
        if candidate is not None:
            media = candidate
            mime = getattr(candidate, "mime_type", None) or default
            break
    if media is None:
        return await asyncio.to_thread(analyze, api_key, url=media_url(reply))
    if not re.fullmatch(r"(?:image|video)/[A-Za-z0-9.+-]+", mime):
        raise GeoSintError("Formato non supportato: rispondi a un'immagine o un video.")
    size = getattr(media, "file_size", None)
    if not isinstance(size, int) or not 0 < size <= MAX_MEDIA_BYTES:
        raise GeoSintError("Il comando accetta media fino a 20 MiB con dimensione nota.")
    try:
        downloaded = await asyncio.wait_for(client.download_media(reply, in_memory=True), timeout=120)
    except TimeoutError:
        raise GeoSintError("Tempo scaduto durante il download del media da Telegram.") from None
    if downloaded is None:
        raise GeoSintError("Impossibile scaricare il media da Telegram.")
    try:
        downloaded.seek(0)
        content = downloaded.read(MAX_MEDIA_BYTES + 1)
    finally:
        downloaded.close()
    if not content or len(content) > MAX_MEDIA_BYTES:
        raise GeoSintError("Media vuoto o superiore al limite di 20 MiB.")
    return await asyncio.to_thread(analyze, api_key, media=content, mime=mime)


def result_chunks(result: dict) -> list[str]:
    # Conserva tutti i campi e tutti i candidati, compresi eventuali campi futuri.
    text = json.dumps(result, ensure_ascii=False, indent=2)
    chunks, start, units = [], 0, 0
    for index, character in enumerate(text):
        width = 2 if ord(character) > 0xFFFF else 1
        if units + width > 3600:
            chunks.append(text[start:index])
            start, units = index, 0
        units += width
    chunks.append(text[start:])
    return chunks
