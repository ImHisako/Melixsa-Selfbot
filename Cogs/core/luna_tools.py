"""Funzioni portabili di Luna riscritte per Telegram (nessun codice Discord eseguito)."""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import operator
from pathlib import Path
import random
import secrets
import string
import time
from urllib.parse import urlsplit
import requests

STARTED = time.monotonic()
RNG = random.SystemRandom()

CATEGORIES = {
    "fun": tuple((name, "[utente o risposta]", description) for name, description in {
        "hug": "Abbraccia", "kiss": "Bacia", "pat": "Accarezza", "slap": "Schiaffo scherzoso",
        "tickle": "Solletico", "feed": "Offri del cibo", "bite": "Morso scherzoso", "shoot": "Scena cartoon",
        "iq": "IQ casuale per gioco", "gay": "Percentuale casuale per gioco", "love": "Affinità casuale per gioco",
    }.items()) + (
        ("dick", "[utente o risposta]", "Dimensione ASCII"),
        ("boobs", "[utente o risposta]", "Dimensione ASCII"),
        ("8ball", "<domanda>", "Risposta della sfera magica"), ("slot", "", "Slot machine"),
        ("coinflip", "", "Testa o croce"), ("dice", "[facce]", "Lancia un dado"),
        ("choose", "<a | b | ...>", "Scegli un'opzione"), ("joke", "", "Battuta casuale"),
        ("dadjoke", "", "Freddura casuale"),
    ),
    "animated": tuple((name, "[testo]" if name == "cathi" else "", description) for name, description in {
        "cathi": "Gattino nel pacco", "flop": "Capriola", "poof": "Scomparsa", "boom": "Esplosione cartoon",
        "tableflip": "Rovescia il tavolo", "unflip": "Rimetti il tavolo", "warning": "Allarme simulato",
    }.items()),
    "text": tuple((name, "<testo o risposta>", description) for name, description in {
        "reverse": "Inverti testo", "vape": "Testo fullwidth", "zalgo": "Testo glitch",
        "ascii": "Banner ASCII", "bold": "Grassetto Telegram", "spoiler": "Spoiler Telegram",
        "underline": "Sottolineato Telegram", "strike": "Barrato Telegram", "italic": "Corsivo Telegram",
        "indent": "Rientra il testo", "indent_title": "Rientra la prima riga",
        "indent_footer": "Rientra l'ultima riga", "indent_all": "Rientra tutte le righe",
        "encode_base64": "Codifica Base64", "decode_base64": "Decodifica Base64",
        "encode_leet": "Testo leet", "decode_leet": "Decodifica leet",
        "encode_md5": "Digest MD5", "encode_sha1": "Digest SHA1", "encode_sha224": "Digest SHA224",
        "encode_sha256": "Digest SHA256", "encode_sha384": "Digest SHA384", "encode_sha512": "Digest SHA512",
    }.items()),
    "tools": (
        ("calc", "<espressione>", "Calcolatrice"), ("passgen", "[lunghezza]", "Password casuale"),
        ("note", "<nome> <testo>", "Salva nota locale"), ("editnote", "<nome> <testo>", "Modifica nota"),
        ("delnote", "<nome>", "Elimina nota"), ("shownote", "<nome>", "Mostra nota"),
        ("sendnote", "<nome>", "Invia nota nella chat"), ("notes", "", "Elenca note"),
        ("poll", "<domanda | opzione | opzione>", "Sondaggio Telegram"),
        ("cpoll", "<domanda | opzione | opzione>", "Sondaggio non anonimo"),
    ),
    "profile": (
        ("name", "<nome> [| cognome]", "Cambia nome Telegram"),
        ("bio", "<testo>", "Cambia biografia"), ("avatar", "[utente o risposta]", "Mostra foto profilo"),
    ),
    "misc": (("uptime", "", "Tempo di attività"), ("about", "", "Info Melixsa"),
             ("ping", "", "Latenza API Telegram")),
    "admin": (
        ("kick", "[utente o risposta]", "Espelli dal gruppo"), ("ban", "[utente o risposta]", "Banna dal gruppo"),
        ("unban", "<utente>", "Rimuovi ban"), ("mute", "[utente o risposta]", "Silenzia nel gruppo"),
        ("unmute", "[utente o risposta]", "Ripristina permessi della chat"),
        ("slowmode", "<secondi>", "Imposta modalità lenta"), ("removeslowmode", "", "Disattiva modalità lenta"),
        ("guildname", "<titolo>", "Rinomina gruppo Telegram"),
    ),
}
ALIASES = {"slots": "slot", "flip": "coinflip", "8b": "8ball", "leet": "encode_leet",
           "base64": "encode_base64", "encode": "encode_base64", "decode": "decode_base64",
           "deletetimer": "deleteafter", "userinfo": "whois", "guildinfo": "chatinfo", "iplookup": "ip",
           "setname": "name", "setbio": "bio"}
COMMANDS = {name for entries in CATEGORIES.values() for name, _, _ in entries}
ANIMATIONS = {
    "cathi": ("Un pacco!\n  ______\n |      |\n |______|", "  /\\_/\\\n ( o.o )\n  > ^ <\n{text}"),
    "flop": ("( °-°) ('-' )", "(╯°□°)╯ ('-' )", "(╯°□°)╯︵( .o.)"),
    "poof": ("( ' - ')", "' - ')", "- ')", ")", "*poof*"),
    "boom": ("Esplosione cartoon: 3", "Esplosione cartoon: 2", "Esplosione cartoon: 1", "💣", "💥"),
    "tableflip": ("( °-°) ┬─┬", "(╯°□°)╯", "(╯°□°)╯︵ ┻━┻"),
    "unflip": ("┻━┻", "┬─┬ ノ( ゜-゜ノ)"),
    "warning": (
        "LOAD !! WARNING !! SYSTEM OVER",
        "OAD !! WARNING !! SYSTEM OVERL",
        "AD !! WARNING !! SYSTEM OVERLO",
        "D !! WARNING !! SYSTEM OVERLOA",
        "! WARNING !! SYSTEM OVERLOAD !",
        "WARNING !! SYSTEM OVERLOAD !!",
        "ARNING !! SYSTEM OVERLOAD !! W",
        "RNING !! SYSTEM OVERLOAD !! WA",
        "NING !! SYSTEM OVERLOAD !! WAR",
        "ING !! SYSTEM OVERLOAD !! WARN",
        "NG !! SYSTEM OVERLOAD !! WARNI",
        "G !! SYSTEM OVERLOAD !! WARNIN",
        "!! SYSTEM OVERLOAD !! WARNING",
        "! SYSTEM OVERLOAD !! WARNING !",
        "SYSTEM OVERLOAD !! WARNING !!",
        "IMMINENT SHUT-DOWN IN 0.5 SEC!",
        "WARNING !! SYSTEM OVERLOAD !!",
        "IMMINENT SHUT-DOWN IN 0.2 SEC!",
        "SYSTEM OVERLOAD !! WARNING !!",
        "IMMINENT SHUT-DOWN IN 0.01 SEC!",
        r"SHUT-DOWN EXIT ERROR ¯\(｡･益･)/¯",
        "CTRL + R FOR MANUAL OVERRIDE..",
    ),
}
GIF_COMMANDS = {"hug", "kiss", "pat", "slap", "tickle", "feed", "bite", "shoot"}


def reaction_gif(command: str) -> tuple[str, str]:
    if command not in GIF_COMMANDS:
        raise ValueError("GIF sconosciuta.")
    try:
        response = requests.get(f"https://nekos.best/api/v2/{command}",
                                headers={"User-Agent": "MelixsaSelfbot/1.0 (https://github.com/ImHisako)", "Accept": "application/json"}, timeout=(5, 15))
        response.raise_for_status()
        if "application/json" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("Risposta GIF non valida.")
        item = response.json()["results"][0]
        url = item["url"]
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "nekos.best" or not parsed.path.endswith(".gif"):
            raise ValueError("URL GIF non valido.")
        return url, str(item.get("anime_name", ""))[:150]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("Servizio GIF non disponibile.") from exc


def input_text(message, argument: str) -> str:
    reply = getattr(message, "reply_to_message", None)
    value = argument or (getattr(reply, "text", None) or getattr(reply, "caption", "") if reply else "")
    if not value:
        raise ValueError("Indica il testo oppure rispondi a un messaggio.")
    if len(value) > 1500:
        raise ValueError("Usa al massimo 1500 caratteri.")
    return value


def calculate(expression: str) -> str:
    if not expression or len(expression) > 200:
        raise ValueError("Inserisci un'espressione fino a 200 caratteri.")
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                  ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Esponente troppo grande.")
            value = operations[type(node.op)](left, right)
        else:
            raise ValueError("Sono consentiti numeri, parentesi e + - * / // % **.")
        if type(value) not in (int, float) or abs(value) > 10**100:
            raise ValueError("Risultato troppo grande o non reale.")
        return value
    try:
        return str(visit(ast.parse(expression, mode="eval").body))
    except (SyntaxError, ZeroDivisionError, OverflowError, RecursionError) as exc:
        raise ValueError("Espressione non valida o fuori dai limiti.") from exc


def transform(command: str, text: str) -> str:
    if command == "reverse": return text[::-1]
    if command == "vape": return "".join(chr(ord(c) + 65248) if "!" <= c <= "~" else "　" if c == " " else c for c in text)
    if command == "zalgo": return "".join(c + "\u0301\u0336" if not c.isspace() else c for c in text)[:3000]
    if command.startswith("indent"):
        lines = text.splitlines()
        return "\n".join("    " + line if command in {"indent", "indent_all"} or
                         (command == "indent_title" and i == 0) or
                         (command == "indent_footer" and i == len(lines)-1) else line for i, line in enumerate(lines))
    if command == "encode_base64": return base64.b64encode(text.encode()).decode()
    if command == "decode_base64":
        try: return base64.b64decode(text, validate=True).decode("utf-8")
        except (ValueError, UnicodeError) as exc: raise ValueError("Base64 UTF-8 non valido.") from exc
    if command == "encode_leet": return text.translate(str.maketrans("aAeEiIoOsStT", "443311005577"))
    if command == "decode_leet": return text.translate(str.maketrans("431057", "aeiost"))
    if command.startswith("encode_"): return hashlib.new(command.removeprefix("encode_"), text.encode()).hexdigest()
    raise ValueError("Trasformazione sconosciuta.")


def fun_result(command: str, argument: str, target: str) -> str:
    if command == "dick":
        return f"{target}'s dick\n8{'=' * RNG.randint(1, 13)}D"
    if command == "boobs":
        padding = ' ' * RNG.randint(0, 13)
        shape = f"({padding}.{padding})"
        return f"{target}'s boobs\n{shape} {shape}"
    actions = {"hug": "abbraccia", "kiss": "bacia", "pat": "accarezza", "slap": "dà uno schiaffo scherzoso a",
               "tickle": "fa il solletico a", "feed": "offre del cibo a", "bite": "mordicchia",
               "shoot": "lancia una torta cartoon a"}
    if command in actions: return f"Melixsa {actions[command]} {target} ✨"
    if command in {"iq", "gay", "love"}:
        return f"{target} » {RNG.randint(1, 120 if command == 'iq' else 100)}{' IQ' if command == 'iq' else '%'}"
    if command == "8ball":
        if not argument: raise ValueError("Scrivi una domanda per la sfera magica.")
        return f"Domanda » {argument}\nRisposta » {RNG.choice(('Sì!', 'No.', 'Forse.', 'Riprova più tardi.', 'Molto probabile.', 'Poco probabile.'))}"
    if command == "slot":
        fruits = [RNG.choice("🍎🍊🍐🍋🍉🍇🍓🍒") for _ in range(3)]
        return " | ".join(fruits) + "\n" + ("Jackpot!" if len(set(fruits)) == 1 else "Due uguali!" if len(set(fruits)) == 2 else "Riprova!")
    if command == "coinflip": return f"Moneta » {RNG.choice(('Testa', 'Croce'))}"
    if command == "dice":
        faces = int(argument or 6)
        if not 2 <= faces <= 1000: raise ValueError("Scegli da 2 a 1000 facce.")
        return f"Dado d{faces} » {RNG.randint(1, faces)}"
    if command == "choose":
        options = [part.strip() for part in argument.split("|") if part.strip()]
        if not 2 <= len(options) <= 20: raise ValueError("Separa da 2 a 20 opzioni con |.")
        return f"Scelta » {RNG.choice(options)}"
    return RNG.choice(("Perché il computer ha freddo? Ha lasciato Windows aperto.",
                       "Un bit all'altro: ci vediamo al bus!", "Ho una battuta su UDP, ma potresti non riceverla."))


class Notes:
    def __init__(self, path: Path): self.path = path

    def execute(self, command: str, argument: str) -> str:
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        if command == "notes": return "Note » " + (", ".join(sorted(data)) or "nessuna")
        parts = argument.split(maxsplit=1)
        if not parts or not 1 <= len(parts[0]) <= 64:
            raise ValueError("Indica un nome di nota fino a 64 caratteri.")
        name = parts[0]
        if command in {"note", "editnote"}:
            if len(parts) != 2 or len(parts[1]) > 3000: raise ValueError("Indica nome e testo (massimo 3000 caratteri).")
            if command == "note" and name in data: raise ValueError("Nota esistente: usa editnote.")
            if command == "editnote" and name not in data: raise ValueError("Nota inesistente.")
            if name not in data and len(data) >= 100: raise ValueError("Limite di 100 note raggiunto.")
            data[name] = parts[1]
        elif name not in data: raise ValueError("Nota inesistente.")
        elif command in {"shownote", "sendnote"}: return data[name]
        else: del data[name]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
        return f"Nota {name} » {'eliminata' if command == 'delnote' else 'salvata'}"


def password(argument: str) -> str:
    length = int(argument or 20)
    if not 8 <= length <= 128: raise ValueError("Lunghezza da 8 a 128.")
    alphabet = string.ascii_letters + string.digits + "!@#$%&*+-_"
    while True:
        result = "".join(secrets.choice(alphabet) for _ in range(length))
        if all(any(c in group for c in result) for group in (string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%&*+-_")):
            return result
