# dropweb-channel — студия анимированных стикеров

Среда для создания брендовых анимированных Telegram-стикеров/эмодзи dropweb:
**от промта для ИИ до готового `.tgs`**, с браузерной студией для тюнинга.
Неоново-зелёная плоская айдентика, вектор (Lottie/TGS), бесшовный луп, 120 BPM.

## Быстрый старт
```bash
dropweb-studio            # алиас: поднимает студию + открывает браузер (http://localhost:8765)
# или вручную:
./run.sh studio
```
Для генерации из промта нужен ключ `CLIPROXY_KEY` (берётся из env или
`~/.cli-proxy-api/cliproxyapi.conf.staged`, в репозиторий не коммитим).
Без ключа работает всё, кроме генерации из промта (upload PNG, тюнинг, экспорт).

## Студия (http://localhost:8765)
- **Создание**: промт → gpt-image-2, или 📎 **референс** (image-to-image), или ⬆ загрузка PNG.
- **Авто-стиль**: промты выправляются под плоскую неон-иконку + контроль сложности/размера ≤64КБ.
- **Тюнинг**: 40 whole-glyph анимаций + 8 поэлементных, микс 2-х слоёв, цвет/радуга/обводка,
  **фон-плитка** (тёмный скруглённый куб, регулируемые радиус и цвет).
- **Паки**: создание / переключение / переименование / удаление; удаление эмодзи.
- **Экспорт**: `.tgs` (одна) / `.zip` (весь пак) прямо в браузере.
- **Сохранение в пак** — источник истины; пак потом воспроизводимо собирается из CLI.

## Пайплайн (вектор TGS)
1. `gpt-image-2` (cliproxyapi `localhost:8317`) → иконка по промту/референсу, либо upload PNG.
2. Маска → `vectorize` (potrace + picosvg) → чистый SVG (каждый `<path>` = элемент).
3. SVG → Lottie-база (`svg2base`).
4. Анимация (`studio.js makeAnimX`): per-element keyframes + whole-glyph риги + опц. фон-плитка.
5. Экспорт gzip → `.tgs` (512 / 60fps / луп / 120 BPM, ≤64КБ). Заливка через @stickers.

## CLI
- `./run.sh studio [--port 8765]` — студия (сервер + API).
- `./run.sh render [pack]` — собрать **весь пак в `.tgs` как в студии** (node, → `build/<pack>/tgs/`).
- `python -m tools.build_tgs --pack <name> [--id X] [--bg]` — векторная сборка из спек (potrace → tgs).
- `python -m tools.studio_server --pack <name> --port N` — сервер студии напрямую.
- `./run.sh [--id X]` — legacy webm-сборка (`build_emoji`).

## Структура
- `studio/` — браузерная студия: `index.html` + `studio.js` (движок анимаций, работает и в браузере,
  и в node) + `bases.js`.
- `tools/` — `studio_server.py` (HTTP+API), `svg2base.py`, `vectorize.py`, `gen_icon.py`,
  `tgs_anim.py` (поэлементные пресеты), `build_tgs.py` (оркестратор), `build_emoji.py`
  (маски + legacy webm), `render_pack.cjs` (node-рендер пака как в студии).
- `packs/<name>/` — `pack.json` (спеки эмодзи + сохранённый тюнинг) + `bases.json` (Lottie-базы).
  Источник истины пака.
- `build/<pack>/tgs/` — готовые `.tgs`; `build/<pack>/preview/` — превью-кадры.
- `docs/` — `brand-tokens.md` (источник истины бренда), `plans/` (дизайн-доки),
  `animation-playbook.md`.

## API студии (локально)
`GET /api/pack[s]`, `POST /api/generate` (+ опц. `ref`), `/api/regenerate`, `/api/upload`,
`/api/save`, `/api/pack/create|rename|delete`, `/api/emoji/delete`.

Подробности бренда и рецепт — `docs/brand-tokens.md`.
