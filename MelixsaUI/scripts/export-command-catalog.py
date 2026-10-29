"""Rigenera il catalogo consultabile anche nell'anteprima senza Telegram."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from MelixsaUI.backend.commands import command_catalog


if __name__ == "__main__":
    destination = ROOT / "MelixsaUI/src/catalog/commands.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(command_catalog(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catalogo aggiornato: {destination.name}")
