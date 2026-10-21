"""Adattatore Melixsa per https://github.com/AbelXeon/OSINT-BOT."""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import io
from urllib.parse import urlsplit

COMMANDS = {"username", "email", "domain", "ip", "phone", "namesearch", "breach", "telegram", "dorks",
            "imageosint", "exif", "forwardinfo", "autoosint", "osintall"}
SUBCOMMANDS = {name: name for name in COMMANDS} | {
    "name": "namesearch", "tg": "telegram", "user": "username", "image": "imageosint",
    "forward": "forwardinfo", "auto": "autoosint", "all": "osintall",
}


class PlainReport(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs).get("href", ""))
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "a" and self.links:
            url = self.links.pop()
            if urlsplit(url).scheme in {"https", "http", "tg"}:
                self.parts.append(f" ({url})")

    def handle_data(self, text):
        self.parts.append(text)


def plain_result(result, prefix: str) -> str:
    parser = PlainReport()
    parser.feed(result.text)
    text = "".join(parser.parts).strip()
    if result.links:
        text += "\n\nLink\n" + "\n".join(f"{label} » {url}" for label, url in result.links)
    if result.actions:
        text += "\n\nApprofondisci\n" + "\n".join(
            f"{prefix}{SUBCOMMANDS.get(kind, kind)} {target}" for _, kind, target in result.actions)
    return text


def chunks(text: str, limit: int = 3400) -> list[str]:
    output, current, units = [], [], 0
    for char in text:
        size = 2 if ord(char) > 0xFFFF else 1
        if units + size > limit:
            output.append("".join(current))
            current, units = [], 0
        current.append(char)
        units += size
    if current:
        output.append("".join(current))
    return output or [""]


def forward_report(reply):
    from .osint_extras.queries import Result
    if reply is None:
        raise ValueError("Rispondi a un messaggio inoltrato.")
    user = getattr(reply, "forward_from", None)
    chat = getattr(reply, "forward_from_chat", None)
    hidden = getattr(reply, "forward_sender_name", None)
    if user:
        name = " ".join(filter(None, (user.first_name, user.last_name)))
        text = f"Inoltro da utente\nID: {user.id}\nNome: {name}\nUsername: @{user.username}" if user.username else f"Inoltro da utente\nID: {user.id}\nNome: {name}"
    elif chat:
        text = f"Inoltro da chat\nID: {chat.id}\nTitolo: {chat.title or '—'}\nUsername: {getattr(chat, 'username', None) or '—'}"
    elif hidden:
        text = f"Inoltro con autore nascosto\nNome mostrato: {hidden}\nTelegram non fornisce l'ID dell'autore."
    else:
        raise ValueError("Il messaggio non contiene informazioni di inoltro disponibili.")
    # Il testo generato localmente deve restare letterale durante la conversione HTML.
    from html import escape
    return Result(escape(text))


async def image_report(client, reply, command: str):
    from .osint_extras import queries as q
    if reply is None:
        raise ValueError("Rispondi a una foto o a un file immagine.")
    photo = getattr(reply, "photo", None)
    document = getattr(reply, "document", None)
    if photo and command == "imageosint":
        return q.photo_tip()
    if not photo and (not document or not str(document.mime_type or "").startswith("image/")):
        raise ValueError("Serve una foto oppure un documento immagine.")
    if client is None:
        raise ValueError("Client Telegram non disponibile per leggere l'immagine.")
    data = bytearray()
    # Un solo chunk Telegram (1 MiB): solo header/EXIF, niente file su disco.
    async for part in client.stream_media(reply, limit=1):
        data.extend(part[:1_048_576 - len(data)])
        if len(data) >= 1_048_576:
            break
    if not data:
        raise ValueError("Immagine non scaricabile.")
    return await asyncio.to_thread(q.exif_report, bytes(data))


async def lookup(command: str, argument: str, client=None, message=None):
    from .osint_extras import queries as q
    reply = getattr(message, "reply_to_message", None)
    if command in {"imageosint", "exif"}:
        return await image_report(client, reply, command)
    if command == "forwardinfo":
        return forward_report(reply)
    target = argument.strip() or (getattr(reply, "text", None) or getattr(reply, "caption", "") if reply else "")
    if len(target) > 300:
        raise ValueError("Usa un valore fino a 300 caratteri.")
    if command in {"autoosint", "osintall"}:
        if not target and reply:
            if any(getattr(reply, field, None) for field in ("forward_from", "forward_from_chat", "forward_sender_name")):
                return forward_report(reply)
            return await image_report(client, reply, "imageosint")
        if not target:
            raise ValueError("Indica un valore oppure rispondi a un messaggio.")
        kind = SUBCOMMANDS.get(q.detect(target), q.detect(target))
        if command == "autoosint":
            return await lookup(kind, target, client, message)
        primary = await lookup(kind, target, client, message)
        # L'email completa include già breach e registrazioni; evita richieste duplicate.
        additional = []
        if kind in {"email", "namesearch", "phone", "username", "telegram"}:
            additional.append(await q.dorks(target))
        if kind == "telegram":
            username = target.rstrip("/").split("/")[-1].lstrip("@")
            additional.append(await q.username(username))
        if kind == "namesearch":
            variants = q._variants(target)
            if variants:
                additional.append(await q.username(variants[0]))
        combined = [primary] + additional
        files = [result.file for result in combined if result.file]
        file = ("osint_report.txt", b"\n\n".join(content for _, content in files)) if files else None
        return q.Result("\n\n".join(result.text for result in combined),
                        links=[link for result in combined for link in result.links], file=file)
    if not target:
        raise ValueError(f"Indica un valore per {command}.")
    if command == "phone":
        parts = target.split(maxsplit=1)
        region = parts[0].upper() if len(parts) == 2 and len(parts[0]) == 2 and parts[0].isalpha() else None
        return await q.phone(parts[1] if region else target, region)
    operations = {"username": q.username, "email": q.email, "domain": q.domain, "ip": q.ip_lookup,
                  "breach": q.breach, "telegram": q.telegram, "namesearch": q.name_search, "dorks": q.dorks}
    return await operations[command](target)


async def send_report(client, message, result, command: str, prefix: str) -> None:
    from . import runtime
    if result.file and client is not None:
        filename, content = result.file
        document = io.BytesIO(content)
        document.name = filename
        sent = await client.send_document(message.chat.id, document, message_thread_id=getattr(message, "message_thread_id", None))
        if sent is not None:
            runtime.schedule_delete(sent)
    parts = chunks(plain_result(result, prefix))
    for index, part in enumerate(parts, 1):
        if index > 1:
            await asyncio.sleep(1)
        title = f"MELIXSA / OSINT / {command.upper()}"
        if len(parts) > 1:
            title += f" / {index} di {len(parts)}"
        await runtime.respond(message, part, title=title)
