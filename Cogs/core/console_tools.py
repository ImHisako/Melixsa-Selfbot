"""Console Melixsa: palette Luna, log centralizzati e file rotanti."""
from __future__ import annotations

import ctypes
from collections import deque
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import sys

LOGO = r"""
  __  __      _ _                 
 |  \/  | ___| (_)_  _____  __ _  
 | |\/| |/ _ \ | \ \/ / __|/ _` | 
 | |  | |  __/ | |>  <\__ \ (_| | 
 |_|  |_|\___|_|_/_/\_\___/\__,_| 
"""
logger = logging.getLogger("melixsa")
logger.addHandler(logging.NullHandler())
logger.setLevel(logging.INFO)
_secrets: list[str] = []
recent_errors = deque(maxlen=10)
error_callback = None
CONSOLE_DEFAULTS = dict(timestamp=True, spacers=True, pgradient=True, lgradient=True, debug_mode=False)
_settings = CONSOLE_DEFAULTS.copy()


def _enable_virtual_terminal() -> bool:
    """Abilita i controlli del terminale anche quando i colori sono disattivati."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                    and kernel32.SetConsoleMode(handle, mode.value | 4))
    except (AttributeError, OSError):
        return False


def clear() -> None:
    """Pulisce schermo e cronologia, poi riporta il cursore in alto."""
    if not sys.stdout.isatty():
        return
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt" and not _enable_virtual_terminal():
        os.system("cls")
        return
    # 2J può spostare il contenuto nella cronologia: 3J deve seguirlo.
    print("\033[2J\033[3J\033[H", end="", flush=True)


def clean(value: object) -> str:
    text = str(value)
    for secret in _secrets:
        text = text.replace(secret, "[redacted]")
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)


def gradient(text: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    result = []
    for index, char in enumerate(text):
        fraction = index / max(1, len(text) - 1)
        rgb = tuple(round(a + (b - a) * fraction) for a, b in zip((137, 142, 255), (205, 160, 255)))
        result.append(f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{char}")
    return "".join(result) + "\033[0m"


class ConsoleFormatter(logging.Formatter):
    def __init__(self, colors: bool = False, *, console: bool = True):
        super().__init__(datefmt="%H:%M:%S")
        self.colors = colors
        self.console = console

    def format(self, record: logging.LogRecord) -> str:
        category = clean(getattr(record, "category", "Error" if record.levelno >= logging.ERROR else "Event"))
        colors = self.colors and _settings["pgradient"]
        label = gradient(f"{category:<9}", colors)
        if record.levelno >= logging.ERROR and colors:
            label = f"\033[38;2;255;100;120m{category:<9}\033[0m"
        # I file mantengono sempre timestamp e separatori, anche se nascosti nella UI.
        settings = _settings if self.console else dict(timestamp=True, spacers=True)
        spacer = " | " if settings["spacers"] else " "
        timestamp = self.formatTime(record, self.datefmt) + spacer if settings["timestamp"] else ""
        return f"{timestamp}{label}{spacer}{clean(record.getMessage())}"


class DebugModeFilter(logging.Filter):
    """Nasconde i dettagli tecnici senza nascondere comandi e problemi."""
    def filter(self, record: logging.LogRecord) -> bool:
        technical = getattr(record, "debug_only", False) or record.name.split(".", 1)[0] in {"pyrogram", "websockets"}
        return record.levelno >= logging.WARNING or not technical or _settings.get("debug_mode", False)


def record_error(message: object) -> None:
    recent_errors.append((datetime.now().astimezone().isoformat(timespec="seconds"), clean(message)[:500]))
    if error_callback is not None:
        error_callback()


class RecentErrorHandler(logging.Handler):
    def emit(self, record):
        # Gli eventi Melixsa sono già raccolti da event(), anche prima del setup.
        if record.name != "melixsa":
            record_error(record.getMessage())


def event(category: str, message: object, *, error: bool = False, debug: bool = False) -> None:
    if error:
        record_error(message)
    logger.log(logging.ERROR if error else logging.INFO, str(message), extra={"category": category, "debug_only": debug})


def configure(settings: dict[str, bool]) -> None:
    _settings.update(settings)


def setup(log_dir: Path, *, secrets=()) -> None:
    global _secrets
    _secrets = [value for key, value in os.environ.items()
                if any(word in key.upper() for word in ("API_HASH", "API_KEY", "TOKEN", "PASSWORD")) and len(value) >= 6]
    _secrets.extend(value for value in secrets if value and len(value) >= 6)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    colors = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    if os.name == "nt" and colors:
        colors = _enable_virtual_terminal()
        try:
            ctypes.windll.kernel32.SetConsoleTitleW("Melixsa | Telegram Selfbot")
        except (AttributeError, OSError):
            colors = False
    log_dir.mkdir(parents=True, exist_ok=True)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter(colors))
    console.addFilter(DebugModeFilter())
    file = RotatingFileHandler(log_dir / "melixsa.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file.setFormatter(ConsoleFormatter(False, console=False))
    file.addFilter(DebugModeFilter())
    # Le librerie e i task in background passano dallo stesso formatter.
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file)
    root.addHandler(RecentErrorHandler(level=logging.ERROR))


def logo_lines(width: int) -> list[str]:
    """Cielo ASCII irregolare con stelle e pianeta, nello stile Luna."""
    logo = [line.rstrip() for line in LOGO.strip("\n").splitlines()]
    logo_width = max(map(len, logo))
    width = max(width, logo_width)
    rows = [[" "] * width for _ in range(11)]
    reserved: set[tuple[int, int]] = set()

    def put(row: int, column: int, text: str) -> None:
        for offset, char in enumerate(text):
            target = column + offset
            if char != " " and 0 <= target < width and rows[row][target] == " " and (row, target) not in reserved:
                rows[row][target] = char

    logo_start = (width - logo_width) // 2
    for index, line in enumerate(logo):
        put(3 + index, logo_start, line)

    planet = (
        '  .-.,="``"=.',
        "  `=/_       \\" ,
        "    |  '=._   |",
        r"    \\     `=./`,",
        "      `=.__.=` `=`",
    )
    
    planet_start = logo_start + logo_width + 3
    if planet_start + max(map(len, planet)) <= width:
        for index, line in enumerate(planet):
            put(3 + index, planet_start, line)
        reserved.update((row, column) for row in range(3, 3 + len(planet))
                        for column in range(planet_start, planet_start + max(map(len, planet))))

    # Coordinate volutamente irregolari, anziche' file di simboli equidistanti.
    stars = (
        (0, .03, "*"), (0, .32, "o"), (0, .47, "+"), (0, .74, "*"), (0, .94, "."),
        (1, .08, "O"), (1, .25, "."), (1, .40, "."), (1, .68, "."), (1, .91, "*"),
        (2, .16, "."), (3, .02, "."), (3, .22, "*"), (5, .86, "."),
        (6, .26, "+"), (7, .06, "*"), (7, .96, "O"),
        (8, .77, "*"), (9, .30, "."), (9, .50, "o"), (9, .72, "."), (9, .93, "+"),
    )
    if logo_start >= 9:
        for row, column in ((6, round(width * .12)), (2, width - 4)):
            if any((y, x) in reserved for y in range(row, row + 3) for x in range(column - 2, column + 3)):
                continue
            put(row, column, "|")
            put(row + 1, column - 2, "- o -")
            put(row + 2, column, "|")
    for row, fraction, symbol in stars:
        put(row, round(fraction * (width - 1)), symbol)
    return ["".join(row) for row in rows]


def banner(prefix: str, count: int, timer: int) -> None:
    width = min(shutil.get_terminal_size((80, 24)).columns, 110)
    colors = _settings["lgradient"] and any(isinstance(handler.formatter, ConsoleFormatter) and handler.formatter.colors
                                           for handler in logging.getLogger().handlers)
    for line in logo_lines(width):
        print(gradient(line, colors))
    print(gradient("Telegram Selfbot | Melixsa".center(width), colors))
    print(gradient("Made By Hisako".center(width), colors))
    print(gradient("=" * width, colors))
    event("Selfbot", f"Prefisso: {prefix} | Comandi: {count} | Timer risposte: {timer}s")
    event("Selfbot", f"Menu: {prefix}help | Uscita: Ctrl+C")
