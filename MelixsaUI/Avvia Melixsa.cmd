@echo off
cd /d "%~dp0"
if not exist "node_modules\@tauri-apps\cli" (
  node scripts\run.mjs install
  if errorlevel 1 goto :failed
)
node scripts\run.mjs desktop
if errorlevel 1 goto :failed
exit /b 0
:failed
echo.
echo Avvio non riuscito. Leggi l'errore qui sopra.
pause
exit /b 1
