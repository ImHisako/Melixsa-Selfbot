"""Punto d'avvio di Melixsa; comandi e servizi sono nel package Cogs."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run() -> None:
    if os.name == "nt":
        os.system("cls")
    elif sys.stdout.isatty():
        print("\033[2J\033[H", end="", flush=True)
    try:
        from Cogs.core.runtime import main
    except ModuleNotFoundError as exc:
        if exc.name not in {"pyrogram", "requests", "websockets", "pyfiglet"}:
            raise
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if venv_python.is_file() and Path(sys.executable).resolve() != venv_python.resolve():
            raise SystemExit(subprocess.call([str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])) from exc
        raise SystemExit("Dipendenze mancanti. Esegui: .venv\\Scripts\\python.exe -m pip install -r requirements.txt") from exc
    # Pyrogram può stampare l'avviso TgCrypto durante l'import:
    # pulisci di nuovo prima dell'avvio e del banner di Melixsa.
    from Cogs.core.console_tools import clear
    clear()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
