#!/usr/bin/env bash
# Сборщик эмодзи dropweb + канонический запуск студии.
#   ./run.sh studio [port]   # студия стикеров (сервер + API + открыть браузер)
#   ./run.sh render [pack]    # собрать весь пак в .tgs как в студии
#   ./run.sh --id db          # пилот (одно эмодзи)
#   ./run.sh                  # весь набор из 16
#   ./run.sh --id new         # текстовое эмодзи (генерация/ключ не нужны)
set -euo pipefail
cd "$(dirname "$0")"

# 1. python-зависимости в локальном venv (нужны всем подкомандам)
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

# 2. ключ cliproxyapi для генерации (берём из локального конфига, в гит не коммитим).
#    Хойстим ВЫШЕ диспетчера подкоманд, чтобы studio/render видели ключ.
#    Keyless-студия всё равно обслуживает upload/тюнинг — поэтому не валим скрипт.
if [ -z "${CLIPROXY_KEY:-}" ]; then
  CLIPROXY_KEY="$(grep -oE 'sk-[a-f0-9]{32,}' ~/.cli-proxy-api/cliproxyapi.conf.staged 2>/dev/null | head -1 || true)"
  if [ -z "$CLIPROXY_KEY" ]; then
    CLIPROXY_KEY="$(grep -oE 'sk-[a-f0-9]{32,}' /opt/homebrew/etc/cliproxyapi.conf 2>/dev/null | head -1 || true)"
  fi
  export CLIPROXY_KEY
fi

# 3. студия: ./run.sh studio [port] — канонический запуск (без дублей + браузер)
if [ "${1:-}" = "studio" ]; then
  shift
  PORT=8765
  if [ "${1:-}" ] && printf '%s' "$1" | grep -qE '^[0-9]+$'; then PORT="$1"; shift; fi
  if curl -sf -o /dev/null --max-time 1 "http://localhost:$PORT/api/packs" 2>/dev/null; then
    echo "dropweb studio уже запущена -> http://localhost:$PORT"
    exit 0
  fi
  if [ -n "${CLIPROXY_KEY:-}" ]; then KEYSTATE="есть"; else KEYSTATE="НЕТ — только upload/тюнинг"; fi
  echo "dropweb studio -> http://localhost:$PORT  (ключ генерации: $KEYSTATE)"
  ( sleep 1.6; command -v open >/dev/null && open "http://localhost:$PORT" >/dev/null 2>&1 || true ) &
  exec python3 -m tools.studio_server --port "$PORT"
fi

# 4. рендер всего пака в .tgs как в студии: ./run.sh render [pack]
if [ "${1:-}" = "render" ]; then shift; exec node tools/render_pack.cjs "${1:-dropweb}"; fi

# 5. сборка webm-пака (нужен ffmpeg только здесь)
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ">> ставлю ffmpeg через brew..."; brew install ffmpeg
fi
python3 -m tools.build_emoji "$@"
echo ">> результат в build/emoji/  (посмотри каждый .webm, затем залей через @stickers)"
