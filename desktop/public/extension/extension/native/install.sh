#!/usr/bin/env bash
# Instala Native Messaging host com.veu.host (Linux / macOS)
set -euo pipefail

EXT_ID="${1:-}"
if [[ -z "$EXT_ID" ]]; then
  echo "Uso: ./install.sh <chrome-extension-id>"
  echo "O ID aparece em chrome://extensions (Modo do desenvolvedor) na Véu Host."
  exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
HOST_PY="$ROOT/veu_host.py"
chmod +x "$HOST_PY"

# Garante python3
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 não encontrado"
  exit 1
fi

NAME="com.veu.host.json"
MANIFEST_BODY=$(cat <<EOF
{
  "name": "com.veu.host",
  "description": "Véu Native Host",
  "path": "$HOST_PY",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://$EXT_ID/"
  ]
}
EOF
)

install_one() {
  local dir="$1"
  mkdir -p "$dir"
  printf '%s\n' "$MANIFEST_BODY" > "$dir/$NAME"
  echo "ok → $dir/$NAME"
}

# Chrome / Chromium / Edge
install_one "${HOME}/.config/google-chrome/NativeMessagingHosts"
install_one "${HOME}/.config/chromium/NativeMessagingHosts"
install_one "${HOME}/.config/microsoft-edge/NativeMessagingHosts"
# macOS Chrome
if [[ "$(uname -s)" == "Darwin" ]]; then
  install_one "${HOME}/Library/Application Support/Google/Chrome/NativeMessagingHosts"
  install_one "${HOME}/Library/Application Support/Microsoft Edge/NativeMessagingHosts"
fi

echo
echo "Pronto. Recarregue a extensão Véu Host e teste «abrir terminal» no SO."
