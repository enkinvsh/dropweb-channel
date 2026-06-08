# План реализации: dropweb Sticker Studio Engine

> REQUIRED SUB-SKILL: executing-plans / subagent-driven-development.

**Goal:** Студия-движок: промт→gpt-image→вектор→Lottie-base→тюнинг(whole-glyph+
поэлементно)→.tgs, с сохранением обратно в `packs/dropweb`.

**Architecture:** Локальный stdlib `http.server` (`tools/studio_server.py`) отдаёт
`studio/` + JSON-API (generate/regenerate/upload/save/pack). `tools/svg2base.py`
конвертит SVG→Lottie-base. Браузерная студия (поднята из `build/studio/`) грузит
bases из API, добавлены панель создания, сохранение, поэлементные kind'ы.

**Tech:** Python 3.9 stdlib http.server, lottie 0.7.2, potrace/picosvg, существующий
gen_icon/vectorize/build_emoji. Фронт: vanilla JS + lottie-web/pako/jszip (CDN).
Соглашения: модульные `__main__` самотесты; без git-коммитов; всё аддитивно.

---

## Task S0: promote studio/ + baseline
- `cp -r build/studio studio` (исходник; build/studio остаётся).
- Verify: `.venv/bin/python3 -m tools.tgs_anim` зелёный; `ls studio/`.

## Task S1: tools/svg2base.py
- `svg_to_base(svg_path) -> dict`: `parse_svg_file(svg)` → `an.to_dict()` (или
  ручная сериализация layers/shapes) → вернуть {layers:[...]} в формате как в
  существующем bases.js (ty:4 слой с shapes-группами, fill #00DE52).
- Self-test: `build/svgwrap/signal.svg` → base, у base layers[0].shapes содержит
  >=1 группу с path; lottie может загрузить (re-import dict). Print `svg2base OK`.

## Task S2: tools/studio_server.py
- stdlib `http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler`.
- Static: `GET /` → studio/index.html; прочие пути → файлы из `studio/`.
- `GET /api/pack?name=` → JSON {order,anchors,defmap,bases,specs} из
  `packs/<name>/pack.json` (+ `packs/<name>/bases.json` если есть, иначе бейсы из
  build/studio/bases.js значения — но канон: bases.json).
- `POST /api/generate {prompt,id,color,fit,thr}` → gen_icon.generate(prompt,tmp)
  → mask (point threshold как build_emoji._gen_cached) → `_fit_mask` →
  vectorize.make_clean_svg → svg2base → {id,base,anchor:""}. Нет CLIPROXY_KEY →
  503 + сообщение.
- `POST /api/regenerate {id,prompt}` → generate_edit(prev,prompt) → base.
- `POST /api/upload {png_b64,id}` → decode → L mask → `_fit_mask` → vectorize →
  base (офлайн).
- `POST /api/save {pack,id,spec,cfg,base}` → атомарно (temp+rename) дописать/
  обновить эмодзи в `packs/<pack>/pack.json` (source/prompt/color/tgs+studioCfg) и
  base в `packs/<pack>/bases.json`; если id новый — добавить в order.
- CLI: `--pack dropweb --port 8765`. Печатает URL.
- Smoke (self-test/`__main__` или manual): запустить, `GET /api/pack` отдаёт
  order из 33; `POST /api/upload` с маленьким PNG возвращает base.

## Task S3: packs/dropweb/bases.json
- Сгенерить из существующих `build/svgwrap/*.svg` через svg2base для всех ORDER,
  собрать {id:base}; записать `packs/dropweb/bases.json`. (Однократный скрипт.)
- Verify: 33 ключа, каждый base загружается lottie.

## Task S4: фронтенд (studio/index.html + studio.js) — visual-engineering
- Грузить order/anchors/defmap/bases из `GET /api/pack` (async на старте), затем
  существующий рендер сетки.
- Панель «＋ Создать из промта»: textarea, [Генерировать]→POST /api/generate,
  спиннер/ошибка; [Загрузить PNG]→/api/upload; [Редактировать]→/api/regenerate.
  Новый base → BASES[id]=base; ORDER.push(id); renderCell; select(id).
- «💾 Сохранить» → POST /api/save {pack,id,spec(source/prompt/color/tgs),cfg,base}.
- Поэлементные kind'ы: добавить CATS «Поэлементно»
  [el_stagger,el_sequential,el_type,el_pulse,el_lead,el_assemble,el_segment,
  el_orbit]; в makeAnimX если kind.startsWith('el_') → итерировать
  icon-слой shape-группы (path-группы), сорт по bbox-x, на каждую группу .it[tr]
  навесить keyframes per JS-порт tgs_anim (stagger по index*stagger). Бесшовно.
- Сохранить фирменный flat-neon вид; не ломать существующий whole-glyph путь.

## Task S5: интеграция + QA
- `python -m tools.studio_server` (фон), Playwright: открыть localhost:8765,
  сетка грузится, слайдеры меняют превью, `el_stagger` на signal (бары
  стаггером), upload тест-PNG→иконка→Сохранить→проверить pack.json/bases.json→
  экспорт .tgs валиден. Скриншоты desktop. Остановить сервер.

## Файлы
Новые: tools/svg2base.py, tools/studio_server.py, studio/*, packs/dropweb/bases.json.
Изм.: studio/index.html, studio/studio.js, run.sh (подкоманда studio).
