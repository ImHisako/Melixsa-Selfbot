@echo off
cd /d "%~dp0"
if not exist "node_modules\vite" (
  node scripts\run.mjs install
  if errorlevel 1 goto :failed
)
echo Anteprima grafica: i dati Telegram sono disponibili nell'app desktop.
node scripts\run.mjs dev --open
if errorlevel 1 goto :failed
exit /b 0
:failed
echo.
echo Anteprima non riuscita. Leggi l'errore qui sopra.
pause
exit /b 1
