# Дизайн: dropweb Sticker Studio Engine (УТВЕРЖДЁН)

Дата: 2026-06-07
Статус: УТВЕРЖДЁН пользователем («Апрув — пиши дизайн-док и строй»)

## Цель
Превратить существующую браузерную студию (`build/studio/`) в удобный движок
создания+редактирования+экспорта стикеров: от **промта для ИИ с генерацией
изображения** до конечного `.tgs`, где тюнятся все настройки. Сохранение —
обратно в `packs/dropweb` (источник истины). Анимации — оба набора: текущие
whole-glyph (40) И поэлементные (stagger/sequential/...).

## Что уже есть (не переписываем)
- `build/studio/index.html` — 3-колоночный UI (сетка эмодзи / большой плеер /
  панель тюнинга), live Lottie через lottie-web, экспорт .tgs/.zip в браузере
  (pako/jszip).
- `build/studio/studio.js` — `makeAnimX(base,opt)` + ~40 whole-glyph анимаций
  (CATS), recolor/rainbow/outline/drawon, рандом/crazy.
- `build/studio/bases.js` — `BASES`(Lottie-вектор каждого эмодзи), `ORDER`,
  `ANCHORS`, `DEFMAP`.
- Python-конвейер: `gen_icon.generate/generate_edit` (gpt-image@cliproxyapi),
  `build_emoji.mask_from_*`/`_fit_mask`, `vectorize.make_clean_svg` (potrace+
  picosvg), `lottie.parsers.svg.parse_svg_file`.

## Архитектура
Локальный Python-сервер (stdlib `http.server`, без новых зависимостей) отдаёт
студию (поднятую в исходник `studio/`) + JSON-API. Браузер = UI + Lottie/.tgs.
Бэкенд делает недоступное браузеру: gpt-image, potrace/picosvg-вектор,
SVG→Lottie-base, запись в пак.

## Компоненты
### Бэкенд
- `tools/svg2base.py` — `svg_to_base(svg_path) -> dict` (Lottie-base): тем же
  `parse_svg_file`, что родил `bases.js`; сериализует слои/шейпы в base-dict.
- `tools/studio_server.py` — `http.server`, роуты:
  - `GET /` + статика из `studio/`.
  - `GET /api/pack?name=dropweb` → `{order, anchors, defmap, bases, specs}`
    (читает `packs/<name>/pack.json` + `packs/<name>/bases.json`).
  - `POST /api/generate {prompt,id,color?,fit?,thr?}` → gen→маска→`_fit_mask`→
    `vectorize.make_clean_svg`→`svg_to_base` → `{id, base, anchor}`.
  - `POST /api/regenerate {id,prompt}` → `gen_icon.generate_edit` на текущем →
    new base.
  - `POST /api/upload {png_b64,id}` → маска→vectorize→base (офлайн, без ключа).
  - `POST /api/save {id, spec, cfg}` → пишет эмодзи в `packs/<name>/pack.json`
    (source/prompt/color/tgs+studio-cfg) и base в `packs/<name>/bases.json`.
- Запуск: `python -m tools.studio_server [--pack dropweb] [--port 8765]`;
  `./run.sh studio`.

### Фронтенд (`studio/`, поднят из `build/studio/`)
- Bases грузятся из `/api/pack` (не из статичного bases.js).
- Новая панель «＋ Создать из промта»: textarea промта, [Генерировать],
  прогресс/ошибка, опц. цвет/fit/thr; «Редактировать (regenerate)»; «Загрузить
  PNG». Новая иконка появляется в сетке, тюнится и экспортится как остальные.
- Кнопка «💾 Сохранить» → `/api/save`. Селектор пака.
- **Поэлементные kind'ы**: новая категория CATS «Поэлементно»:
  `el_stagger/el_sequential/el_type/el_pulse/el_lead/el_assemble/el_segment/
  el_orbit`. В `makeAnimX` для `el_*`: итерируем shape-группы бейса (path-
  элементы), сорт по bbox-x, на `tr` каждой группы вешаем стаггер-кейфреймы —
  JS-порт `tgs_anim.py` пресетов. Бесшовно (first==last), миксуется с
  whole-glyph.

## Поток данных (создание)
промт → `/api/generate` → (gpt-image → маска → vectorize → svg_to_base) →
иконка в сетке → тюнинг (whole-glyph и/или поэлементно) → live Lottie →
«Сохранить» → `pack.json`+`bases.json` → экспорт .tgs (браузер) либо
`build_tgs` (бэкенд, для паритета).

## Обработка ошибок
- Генерация требует `CLIPROXY_KEY` + cliproxyapi@`localhost:8317`. Нет ключа →
  `/api/generate` отдаёт 503 + понятное сообщение; UI показывает, остальное
  (готовые бейсы, upload PNG, тюнинг, экспорт) работает.
- potrace/picosvg обязательны (уже установлены) — иначе 500 с понятным текстом.
- Запись в пак атомарна (temp+rename), не рушит существующий `pack.json`.

## Тестирование / верификация
- `python -m tools.svg2base` самотест: `build/svgwrap/signal.svg` → base с N
  path-группами, валидно грузится lottie.
- Поднять сервер; Playwright-прогон студии: сетка из `/api/pack`, слайдеры
  меняют превью, поэлементный `el_stagger` на `signal` (бары стаггером),
  upload тест-PNG → иконка в сетке → «Сохранить» → проверить запись в
  `pack.json`/`bases.json` → экспорт .tgs валиден (re-parse). Скриншоты desktop.
- Генерация из промта проверяется при наличии ключа; иначе путь upload.

## Вне объёма (YAGNI v1)
Аккаунты/облако, мультиюзер, история версий, ручное редактирование путей,
авто-заливка в Telegram.

## Новые/изменённые файлы
Новые: `tools/svg2base.py`, `tools/studio_server.py`, `studio/` (из build/studio
+ правки), `packs/dropweb/bases.json`.
Изменённые: `studio/index.html`, `studio/studio.js` (create-панель, save, pack
load, el_* kinds), `run.sh` (подкоманда `studio`).
Без изменений: `tgs_anim.py`, `build_tgs.py`, `vectorize.py`, `gen_icon.py`,
`build_emoji.py`.
