"""Utilità ispirate alle funzioni di Ghost, implementate per Melixsa/Telegram."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import random
import re
from urllib.parse import quote_plus

from . import pagination


CODE_LANGUAGES = {
    "python": "python", "js": "javascript", "html": "html", "css": "css",
    "java": "java", "c": "c", "cpp": "cpp", "php": "php", "lua": "lua",
}
CATEGORIES = {
    "tools": (
        ("search", "<testo> [pagina]", "Cerca comandi, descrizioni e alias"),
        ("allcmds", "[pagina]", "Elenco completo dei comandi disponibili"),
    ),
    "settings": (
        ("commandhistory", "[1-50|clear]", "Cronologia locale senza argomenti"),
        ("backup", "[create|view|restore|delete]", "Backup locali di preferenze e note"),
        ("backups", "", "Elenca i backup locali"),
    ),
    "text": (
        ("encodemorsecode", "<testo o risposta>", "Codifica in Morse"),
        ("decodemorsecode", "<Morse o risposta>", "Decodifica Morse"),
        ("regional", "<testo o risposta>", "Lettere in emoji regionali"),
        ("randomcase", "<testo o risposta>", "Maiuscole e minuscole casuali"),
        ("shrug", "", "Invia una scrollata di spalle"),
        ("lmgtfy", "<ricerca o risposta>", "Crea un link di ricerca"),
        ("codeblock", "<linguaggio> [testo o risposta]", "Blocco di codice Telegram"),
        ("json", "<JSON o risposta>", "Valida e formatta JSON"),
    ) + tuple((name, "<codice o risposta>", f"Blocco di codice {language}")
              for name, language in CODE_LANGUAGES.items()),
    "fun": (("rps", "<sasso|carta|forbici>", "Gioca a sasso, carta, forbici"),),
}
COMMANDS = {name for entries in CATEGORIES.values() for name, _, _ in entries}
ALIASES = {
    "cmdhistory": "commandhistory", "morsecode": "encodemorsecode", "morse": "encodemorsecode",
    "morsecodedecode": "decodemorsecode", "unmorse": "decodemorsecode",
    "block": "codeblock", "jblock": "json", "javascript": "js",
    **{f"{name}block": name for name in CODE_LANGUAGES},
    "pyblock": "python", "letmegooglethatforyou": "lmgtfy", "aesthetic": "vape",
    "passwordgen": "passgen", "genpassword": "passgen", "clearconsole": "clear",
    "latency": "ping", "av": "avatar", "ui": "whois", "serverinfo": "chatinfo",
    "si": "chatinfo", "cf": "coinflip", "roll": "dice",
}

_MORSE = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,?!:;'\"-_/()=+@&",
    (".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - "
     "..- ...- .-- -..- -.-- --.. ----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----. "
     ".-.-.- --..-- ..--.. -.-.-- ---... -.-.-. .----. .-..-. -....- ..--.- -..-. -.--. -.--.- "
     "-...- .-.-. .--.-. .-...").split(), strict=True,
))
_FROM_MORSE = {code: letter for letter, code in _MORSE.items()}
_RNG = random.SystemRandom()


def telegram_text(text: str) -> str:
    if not text or len(text.encode("utf-16-le")) // 2 > 4000:
        raise ValueError("Risultato vuoto o troppo lungo per Telegram (massimo 4000 unità UTF-16).")
    return text


def transform(command: str, text: str) -> str:
    if command == "encodemorsecode":
        unsupported = set(text.upper()) - set(_MORSE) - set(" \t\r\n")
        if unsupported:
            raise ValueError("Morse: usa lettere A-Z, cifre e punteggiatura standard, senza accenti o emoji.")
        result = " / ".join(" ".join(_MORSE[c] for c in word) for word in text.upper().split())
    elif command == "decodemorsecode":
        if not text.strip() or any(c not in ".-/ \t\r\n" for c in text):
            raise ValueError("Morse: separa le lettere con spazi e le parole con /.")
        try:
            words = [word.split() for word in text.strip().split("/")]
            if not all(words):
                raise KeyError("parola vuota")
            result = " ".join("".join(_FROM_MORSE[code] for code in word) for word in words)
        except KeyError as exc:
            raise ValueError("Sequenza Morse non riconosciuta.") from exc
    elif command == "regional":
        result = " ".join(chr(0x1F1E6 + ord(c.lower()) - ord("a")) if c.isascii() and c.isalpha() else c
                          for c in text)
    elif command == "randomcase":
        result = "".join(_RNG.choice((c.lower(), c.upper())) for c in text)
    elif command == "lmgtfy":
        result = "https://www.google.com/search?q=" + quote_plus(text)
    else:
        raise ValueError("Trasformazione sconosciuta.")
    return telegram_text(result)


def format_code(command: str, argument: str, reply_text: str = "") -> tuple[str, str]:
    if command == "codeblock":
        parts = argument.split(maxsplit=1)
        if not parts or not re.fullmatch(r"[a-zA-Z0-9_+#.-]{1,32}", parts[0]):
            raise ValueError("Indica un linguaggio fino a 32 caratteri, poi il codice oppure una risposta.")
        language = parts[0].lower()
        text = parts[1] if len(parts) == 2 else reply_text
    else:
        language = "json" if command == "json" else CODE_LANGUAGES[command]
        text = argument or reply_text
    if not text or len(text) > 1500:
        raise ValueError("Indica codice o rispondi a un messaggio (massimo 1500 caratteri).")
    if command == "json":
        def reject_constant(_value):
            raise ValueError("Costante JSON non valida.")
        try:
            text = json.dumps(json.loads(text, parse_constant=reject_constant), ensure_ascii=False, indent=2)
        except (ValueError, RecursionError) as exc:
            raise ValueError("JSON non valido.") from exc
    return language, telegram_text(text)


def command_page(categories, aliases, prefix: str, *, query: str = "", page: int = 1, minimal: bool = False) -> str:
    if page < 1 or len(query) > 100:
        raise ValueError("Pagina da 1 in poi; ricerca fino a 100 caratteri.")
    query = query.casefold().removeprefix(prefix)
    lines = []
    for category, entries in categories.items():
        for name, usage, description in entries:
            names = [alias for alias, target in aliases.items() if target == name]
            if query and query not in " ".join((name, category, description, *names)).casefold():
                continue
            syntax = f"{prefix}{name} {usage}".rstrip()
            lines.append((name, syntax if minimal else f"{syntax} » {description}"))
    pages = pagination.paginate_lines(line for _, line in sorted(lines))
    if page > len(pages):
        raise ValueError(f"Pagina non disponibile: scegli da 1 a {len(pages)}.")
    command = f"{prefix}search {query}" if query else f"{prefix}allcmds"
    links = pagination.navigation(command, page, len(pages))
    return "\n".join((f"Risultati » {len(lines)} | Pagina {page}/{len(pages)}",
                       *(pages[page - 1] or ["Nessun comando trovato."]),
                       *(["", *links] if len(pages) > 1 else [])))


def rps(argument: str) -> str:
    choices = {"sasso": 0, "carta": 1, "forbici": 2, "rock": 0, "paper": 1, "scissors": 2}
    if argument.lower() not in choices:
        raise ValueError("Scegli sasso, carta o forbici.")
    player, computer = choices[argument.lower()], _RNG.randrange(3)
    names = ("sasso", "carta", "forbici")
    result = ("Pareggio!", "Hai vinto!", "Ha vinto Melixsa!")[(player - computer) % 3]
    return f"Tu » {names[player]}\nMelixsa » {names[computer]}\n{result}"


@dataclass(frozen=True)
class CommandRecord:
    date: datetime
    command: str
    success: bool
    elapsed: float


class CommandHistory:
    """Solo nomi ed esito; nessun argomento, messaggio, destinatario o file su disco."""

    def __init__(self):
        self.records: deque[CommandRecord] = deque(maxlen=50)

    def add(self, command: str, success: bool, elapsed: float) -> None:
        self.records.append(CommandRecord(datetime.now(timezone.utc), command, success, elapsed))

    def render(self, count: int = 10) -> str:
        if not 1 <= count <= 50:
            raise ValueError("Scegli da 1 a 50 elementi.")
        return "\n".join(
            f"{item.date.astimezone():%H:%M:%S} | {item.command} | {'ok' if item.success else 'errore'} | {item.elapsed:.2f}s"
            for item in list(self.records)[-count:]
        ) or "Nessun comando in cronologia."
