#!/usr/bin/env bash
# Сборщик эмодзи dropweb. Запускать ПОСЛЕ того как утвердишь установку + генерацию.
#   ./run.sh --id db      # пилот (одно эмодзи)
#   ./run.sh              # весь набор из 16
#   ./run.sh --id new     # текстовое эмодзи (генерация/ключ не нужны)
set -euo pipefail
cd "$(dirname "$0")"

# 1. ffmpeg (нужен для кодирования webm)
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ">> ставлю ffmpeg через brew..."; brew install ffmpeg
fi

# 2. python-зависимости в локальном venv
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

# подкоманда студии: ./run.sh studio [--port 8765]
if [ "${1:-}" = "studio" ]; then shift; exec python3 -m tools.studio_server "$@"; fi

# рендер всего пака в .tgs как в студии: ./run.sh render [pack]
if [ "${1:-}" = "render" ]; then shift; exec node tools/render_pack.cjs "${1:-dropweb}"; fi

# 3. ключ cliproxyapi для gpt-image-2 (берём из локального конфига, в гит не коммитим)
if [ -z "${CLIPROXY_KEY:-}" ]; then
  export CLIPROXY_KEY="$(grep -oE 'sk-[a-f0-9]{32,}' ~/.cli-proxy-api/cliproxyapi.conf.staged | head -1)"
fi

# 4. сборка
python3 -m tools.build_emoji "$@"
echo ">> результат в build/emoji/  (посмотри каждый .webm, затем залей через @stickers)"
