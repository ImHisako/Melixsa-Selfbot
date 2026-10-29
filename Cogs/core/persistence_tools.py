"""Scritture atomiche e copie di recupero dei documenti JSON locali."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def save_json(path: Path, payload: dict, validate) -> None:
    """La copia di recupero contiene solo documenti precedenti validi."""
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    validate(payload)
    previous = None
    if path.exists():
        try:
            previous = path.read_text(encoding="utf-8")
            validate(json.loads(previous))
        except UnicodeError:
            import shutil
            shutil.copy2(path, path.with_name(f"{path.name}.corrupt-{time.time_ns()}"))
            previous = None
        except (ValueError, TypeError, KeyError):
            # Conserva l'originale danneggiato prima di ripararlo.
            if previous is not None:
                atomic_write(path.with_name(f"{path.name}.corrupt-{time.time_ns()}"), previous)
            previous = None
    backup = backup_path(path)
    if previous is not None:
        atomic_write(backup, previous)
    else:
        try:
            validate(json.loads(backup.read_text(encoding="utf-8")))
        except (FileNotFoundError, ValueError, TypeError, KeyError):
            atomic_write(backup, text)
    atomic_write(path, text)
