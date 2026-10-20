@echo off
setlocal
REM Véu Host — instalador Windows (contorna ExecutionPolicy)
REM Uso: install.cmd SEU_EXTENSION_ID

if "%~1"=="" (
  echo Uso: install.cmd ^<chrome-extension-id^>
  echo O ID aparece em chrome://extensions ^(Modo do desenvolvedor^) na Veu Host.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -ExtensionId "%~1"
exit /b %ERRORLEVEL%
