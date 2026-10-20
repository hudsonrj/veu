# Instala Native Messaging host com.veu.host (Windows)
# Preferir: install.cmd SEU_ID
# Ou: powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -ExtensionId SEU_ID
param(
  [Parameter(Mandatory = $true)]
  [string]$ExtensionId
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcPy = Join-Path $Root "veu_host.py"

# Pasta estável (não depende de Downloads)
$InstallDir = Join-Path $env:LOCALAPPDATA "veu\host"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$HostPy = Join-Path $InstallDir "veu_host.py"
$Launcher = Join-Path $InstallDir "veu_host_launcher.bat"
Copy-Item -Force $SrcPy $HostPy

# Resolve caminho absoluto do Python (Chrome não herda o PATH do seu terminal às vezes)
$PythonExe = $null
foreach ($cmd in @("python", "py")) {
  $c = Get-Command $cmd -ErrorAction SilentlyContinue
  if ($c) {
    if ($cmd -eq "py") { $PythonExe = "$($c.Source) -3" } else { $PythonExe = $c.Source }
    break
  }
}
if (-not $PythonExe) {
  Write-Host "Instale Python 3 (https://python.org) e marque Add to PATH, depois rode de novo."
  exit 1
}

if ($PythonExe -like "*py.exe*") {
  $LaunchBody = @"
@echo off
"$($PythonExe.Split(' ')[0])" -3 -u "$HostPy"
exit /b %ERRORLEVEL%
"@
} else {
  $LaunchBody = @"
@echo off
"$PythonExe" -u "$HostPy"
exit /b %ERRORLEVEL%
"@
}
Set-Content -Path $Launcher -Value $LaunchBody -Encoding ASCII

$ManifestDir = Join-Path $env:LOCALAPPDATA "veu\NativeMessagingHosts"
New-Item -ItemType Directory -Force -Path $ManifestDir | Out-Null
$ManifestPath = Join-Path $ManifestDir "com.veu.host.json"

# JSON sem BOM — Chrome é chato com BOM
$LauncherJson = $Launcher.Replace('\', '\\')
$manifestObj = [ordered]@{
  name = "com.veu.host"
  description = "Veu Native Host"
  path = $Launcher
  type = "stdio"
  allowed_origins = @("chrome-extension://$ExtensionId/")
}
$json = $manifestObj | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($ManifestPath, $json, (New-Object System.Text.UTF8Encoding $false))

$keys = @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.veu.host",
  "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.veu.host"
)
foreach ($key in $keys) {
  New-Item -Path $key -Force | Out-Null
  New-ItemProperty -Path $key -Name "(default)" -Value $ManifestPath -Force | Out-Null
  Write-Host "ok -> $key"
}

Write-Host ""
Write-Host "Python: $PythonExe"
Write-Host "Host:   $HostPy"
Write-Host "Manifest: $ManifestPath"
Write-Host "allowed_origins: chrome-extension://$ExtensionId/"
Write-Host ""
Write-Host "Agora: 1) chrome://extensions -> Recarregar Veu Host 0.3.3"
Write-Host "       2) FECHE o Chrome por completo (todas as janelas) e abra de novo"
Write-Host "       3) https://veu.ch8ai.com.br -> Arquivos -> redetectar"
