@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente virtuale mancante.
    echo Crea .venv e installa le dipendenze seguendo README.md.
    exit /b 1
)

".venv\Scripts\python.exe" selfbot.py
exit /b %ERRORLEVEL%
