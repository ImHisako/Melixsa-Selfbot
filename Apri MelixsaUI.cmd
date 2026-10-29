@echo off
setlocal
cd /d "%~dp0"
if not exist "Cogs\core\runtime.py" (
  echo Estrai tutto lo ZIP nella cartella principale di Melixsa, accanto a Cogs e selfbot.py.
  pause
  exit /b 1
)
if not exist "MelixsaUI\backend\bridge.py" (
  echo La cartella MelixsaUI del progetto e' mancante o incompleta. Aggiorna il progetto.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python non trovato. Prepara .venv e requirements.txt come indicato nel README di Melixsa.
  pause
  exit /b 1
)
if not exist "melixsa-ui.exe" (
  echo Eseguibile non trovato. Estrai anche melixsa-ui.exe dallo ZIP della build.
  pause
  exit /b 1
)
set "MELIXSA_ROOT=%CD%"
start "" "%~dp0melixsa-ui.exe"
