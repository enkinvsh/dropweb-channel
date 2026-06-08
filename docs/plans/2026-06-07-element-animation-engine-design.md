# Дизайн: dropweb v2 — поэлементная анимация + среда для паков

Дата: 2026-06-07
Статус: УТВЕРЖДЁН пользователем («делаем»)
Архитектура: подход **C** — гибрид: декларативное ядро элементов/сцены,
whole-glyph = частный случай (1 элемент), всё аддитивно и обратносовместимо.

## 1. Цель

1. Дать движку **поэлементную анимацию**: разбивать глиф на адресуемые части и
   двигать каждую часть по своему таймлайну (стаггер, вторичное действие,
   инерция) + навешиваемые **акцент-элементы** (искры, кольца, скан-бары) со
   своими таймлайнами.
2. Превратить проект в переиспользуемую **среду для создания паков**: отделить
   определение пака (набор + тема + бренд-токены) от кода движка.

Оба пункта делаются в одной итерации, но строго аддитивно: текущий пак dropweb
продолжает собираться без изменений.

## 2. Ограничение текущего движка (что чиним)

Весь движок держится на контракте `fn(mask, size, color, **kw) -> [RGBA]`, где
`mask` — одна монолитная L-маска-силуэт. Все ~60 эффектов
(`animate.py` + `animate2.py`) двигают её как одно тело (scale/warp/shift/
rotate/glow). `phosphor2` рендерит её как неон. Обратиться к «третьему бару
сигнала» или «зрачку» как к отдельному объекту нельзя.

Поэтому премиум-видение из `docs/animation-playbook.md` («4-pane stagger
light-on», «доли со стаггером», «бары один за другим», «pupil lead + eyelid
follow») сегодня вырождается в трюки на всём глифе (`signal` = вайп слева-направо,
`windows` = пульс всей иконки), а единственная честная декомпозиция
(`mushroom_anim`) — захардкоженный разовый код. Не хватает абстракции «сцены из
частей».

## 3. Архитектура (подход C)

### 3.1 Element (модель данных)

Одна часть глифа или акцент:

```
Element:
  id     : str        # "bar0" / "pupil" / "spark_field"
  mask   : PIL L      # маска части в рабочем hi-res (как сейчас 512)
  anchor : (fx, fy)   # пивот в нормированных [0,1] (дефолт = центроид части)
  z      : int        # порядок композита (меньше = глубже)
  blend  : "over"|"add"  # "over" для твёрдых частей, "add" для светящихся акцентов
  color  : str|None   # переопределение цвета (иначе цвет глифа)
  role   : str|None   # семантический тег для пресетов ("bar"/"pane"/"pupil")
```

### 3.2 Stage (компоновщик + раннер таймлайнов)

`stage.render(elements, motions, size, color, n, *, crt=...) -> [RGBA]`

На каждый кадр `i` (фаза `p = i/n`):
1. для каждого элемента в z-порядке: считаем трансформ на фазе `p` из его
   `Motion`, применяем аффинно к L-маске части, рендерим через
   `phosphor2(..., crt_post=False, scanlines=False)` в линейный буфер,
   композитим по `blend` (`raster.over` / `raster.add`);
2. после всех элементов — **один** глобальный CRT-проход:
   `crt.apply_crt(comp, phase=p, ...)` (barrel, хром. аберрация, бегущие
   скан-линии, виньетка, шум);
3. `raster.to_pil(comp)`.

Это ровно порядок рендера из `animation-playbook.md` (маска → ядро → bloom → …
→ CRT в самом конце) и ровно то, что уже делают `ember_breath`/`rocket_launch`
(per-layer рендер + один CRT в конце) — паттерн проверен.

### 3.3 Бесшовный луп со стаггером (инвариант)

Каждый `Motion` обязан давать `transform(p=0) == transform(p=1)`. Стаггер
реализуется как фазовый сдвиг ВНУТРИ зацикленной огибающей: локальная фаза
элемента `lp = (p - delay) mod 1`, которая гонит `loop_sin`/`ping_pong`. Так весь
кадр «закрывается» к концу лупа даже при разнесённых по времени частях.
Выносится в отдельный хелпер `stage.staggered_phase(p, index, count, stagger)` +
самотест на дельту кадр0↔кадрN.

### 3.4 Обратная совместимость

`build_emoji` ветвится по наличию блока `elements`/`motion` в спеке:
- нет блока → старый путь `animate.EFFECTS[anim]` ровно как сейчас (ноль
  изменений для v1, все 60 эффектов и текущий пак живы);
- есть блок → новый Stage-путь.

Фоллбэки: нет numpy → `phosphor2` уже деградирует на legacy; Stage в чистом виде
хочет numpy для линейного композита, но умеет деградировать на `alpha_composite`
PIL.

## 4. Извлечение элементов (гибрид)

### 4.1 Стратегии `elements.split`

- `components` — `scipy.ndimage.label` по маске → связные блобы → сортировка по
  роли (`sort: x|y|dist`). Автоматом ловит бары сигнала, точки think, разнесённые
  панели.
- `grid:RxC` / `rows:N` / `cols:N` — режем bbox маски на части (4 окна =
  `grid:2x2`, строки монитора = `rows:N`).
- `procedural` — для `source: shape` функции рисунка (`mask_from_shape`)
  рефакторятся, чтобы по флагу отдавать части с ролями (бары/стрелка/
  предупреждение мы и так рисуем отдельными примитивами).
- `authored` — явный список регионов в JSON: `[{id, role, bbox|polygon, z,
  blend}]`, вырезающий части из общей маски.
- `layers` (gen, opt-in) — каждый элемент отдельной gen-картинкой через инфру
  `gen_states`. Дороже по API.

### 4.2 Дефолты по источнику

`shape` → `procedural`; `text`/`gen` → `components` (фоллбэк на identity, если
блоб один); `png` → identity, пока не переопределено.

### 4.3 Схема elements/motion (аддитивно, всё опционально)

```json
{
  "id": "signal", "source": "shape", "shape": "bars",
  "elements": { "split": "procedural", "sort": "x" },
  "motion": {
    "preset": "stagger_rise", "stagger": 0.12, "ease": "BRAND", "bpm": false,
    "accents": [ { "type": "spark", "at": "top", "rate": 6 } ]
  }
}
```

Для силовых кейсов вместо `preset` допускается явный `per_element` список
покадровых трансформов.

## 5. Модель движения

### 5.1 Motion на элемент

`delay` (или `stagger * index`), `ease` (BRAND/SNAP/overshoot), трансформы по
локальной фазе (`translate`, `scale`, `rotate` вокруг `anchor`), огибающие
`glow`/`alpha`, и `secondary` — инерция/догон (лаговая копия движения ведущего
элемента: веко догоняет зрачок, рукоятка ключа догоняет поворот).

### 5.2 Пресеты `tools/motion_presets.py`

Каждый — функция `(element, index, count, phase, params) -> transform`:
- `stagger_rise` — части встают/проявляются по очереди (бары сигнала, строки doc);
- `sequential_glow` — части загораются по очереди и держатся (4 окна, точки
  think 1→2→3);
- `pulse_offset` — каждая часть пульсирует со сдвигом фазы (доли мозга);
- `lead_follow` — один ведёт, другой догоняет (глаза зрачок/веко, поворот ключа);
- `assemble_in` — части слетаются на место из офсетов (db, doc, star);
- `type_in` — проявление слева-направо + курсор (terminal);
- `segment_rebuild` — вращающиеся сегменты (стрелки update);
- `orbit` — для акцентов: точки/искры по орбите.

### 5.3 Акцент-элементы

Те же `Element` с процедурно генерируемой по кадрам маской и `blend:"add"`, со
своим таймлайном: `spark`/`ember` (переиспользуем `particles.py`), `ring`
(shock), `scanbar`, `orbit_dot`, `secondary_glyph`.

### 5.4 BPM-синхрон

BPM-сетка (`_bpm_hit`, 120 BPM = 6 ударов/3с) остаётся доступной как драйвер —
элементы могут лочиться на бит, как весь нынешний пак (`motion.bpm: true`).

## 6. Среда для паков (минимально, по YAGNI)

### 6.1 Структура

Конвенция `packs/<name>/`:
```
packs/dropweb/
  pack.json        # бывший emoji_set.json (meta/theme_cycle/emoji)
  assets/          # логотип, шрифты, png-источники пака
  brand.md         # бренд-токены/тема пака (опционально)
```

### 6.2 build_emoji --pack

`tools/` становится пак-агностичным; `build_emoji` получает `--pack <name>`,
читает `packs/<name>/pack.json`, пути ассетов резолвятся относительно
`packs/<name>/`, вывод → `build/<pack>/emoji/`.

### 6.3 Миграция текущего набора

`emoji_set.json` → `packs/dropweb/pack.json`, ассеты → `packs/dropweb/assets/`.
Старый путь `emoji_set.json` оставляем как фоллбэк (`--pack` по умолчанию =
`dropweb`), чтобы ничего не сломать. Достаточно, чтобы завести второй пак; без
плагин-системы.

## 7. Пилот и охват

Поэлементная анимация окупается на **составных** глифах. Пилот (валидируем
end-to-end в Telegram до конверсии всего набора):
- `signal` — бары стаггером (`components`/`procedural` + `stagger_rise`);
- `windows` — 4 окна по очереди (`grid:2x2` + `sequential_glow`);
- `think` — точки как реальные элементы 1→2→3 (`components` + `sequential_glow`);
- `eyes` — зрачок ведёт, веко догоняет (`authored` + `lead_follow`).

Монолитные глифы (db, heart, star, shield) остаются на нынешних whole-body
эффектах — декомпозиция им не нужна.

## 8. Тестирование / верификация

По конвенции репо — `python -m tools.<mod>` самотест на каждый новый модуль:
- бесшовность лупа: дельта кадр0↔кадрN ниже порога;
- 100×100 RGBA, сохранение альфы (декод через libvpx-vp9);
- ≤256КБ после `encode.encode_webm`, бюджет времени рендера;
- сборка пилотных эмодзи в webm + просмотр крупным планом в `build/emoji_hires`.

## 9. Новые и изменённые файлы

Новые:
- `tools/elements.py` — извлечение (`components`/`grid`/`procedural`/`authored`/
  `layers`) → `list[Element]`.
- `tools/stage.py` — компоновщик + раннер таймлайнов + `staggered_phase`.
- `tools/motion_presets.py` — библиотека пресетов движения.

Изменённые (аддитивно):
- `tools/build_emoji.py` — ветка Stage при наличии `elements`/`motion`;
  `--pack`; рефактор `mask_from_shape` на отдачу частей.
- `emoji_set.json` → `packs/dropweb/pack.json` (+ блоки `elements`/`motion` для
  пилотных эмодзи).
- `requirements.txt` — без изменений (numpy/scipy уже есть).

Без изменений: `phosphor2.py`, `raster.py`, `bloom.py`, `crt.py`, `particles.py`,
`easing.py`, `encode.py`.

## 10. Риски и открытые вопросы

- Бесшовность при стаггере — самое тонкое место; закрываем хелпером + самотестом.
- `components` на связных глифах даёт 1 блоб → корректный фоллбэк на identity.
- Бюджет времени: per-element рендер × supersample может быть тяжёлым; кэшируем
  рендер статичных частей между кадрами, где элемент не меняет форму.
- Размер webm с акцентами/частицами — следим за ≤256КБ (crf/менее частиц/24fps).

---

## ADDENDUM (2026-06-07): ПИВОТ НА ВЕКТОР TGS

Решение пользователя: v2 поэлементной анимации делаем **вектором (.tgs / Lottie)**,
а не webm. Причина: для движения частей вектор — родная модель (каждый `<path>`
SVG уже отдельный элемент со своим keyframable `TransformShape`), размер ≤2КБ,
60fps, чёткость на любом масштабе. Глоу/CRT отброшены: rlottie их не рендерит,
принят **чистый плоский неон** (осознанный компромисс).

### Что заменяет растровый стек
- Растровые `tools/elements.py`, `tools/stage.py`, `tools/motion_presets.py` и
  webm-ветка в `build_emoji.py` — собраны и работают, но для этого направления
  **superseded** (оставлены аддитивно, без отката).
- Новый вектор-движок:
  - `tools/tgs_anim.py` — достаёт element-Группы из распарсенного SVG, 8 per-element
    keyframe-пресетов (stagger_rise/sequential_glow/pulse_offset/lead_follow/
    assemble_in/type_in/segment_rebuild/orbit), `build_elements_tgs(svg,out,preset,
    params,n)`, бесшовный луп (first==last keyframe), 120 BPM.
  - `tools/build_tgs.py` — оркестратор: pack-спека → маска (`mask_from_*` из
    build_emoji) → `vectorize.make_clean_svg` (potrace+picosvg) → `tgs_anim` →
    `build/<pack>/tgs/<id>.tgs`. CLI `--pack/--id`. Пресет берётся из `spec["tgs"]`
    (строка или {preset,params,n}), дефолт `pulse_offset`.

### Схема пака (вектор)
В спеку эмодзи добавлено опциональное поле:
```json
"tgs": { "preset": "stagger_rise", "params": {"stagger": 6, "rise": 60}, "n": 60 }
```

### Превью/QA
Растеризация для глаз: `export_svg` (per-frame) + `cairosvg` при
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (cairocffi на macOS иначе ищет
libcairo-2.dll). Полоски кадров → `build/<pack>/preview/<id>_motion.png`.
Истинный рендер — rlottie в Telegram (залив через @stickers).

### Пилот (подтверждён визуально)
- `signal` — 4 бара встают слева-направо (stagger_rise), 0.7КБ.
- `windows` — 4 панели по очереди (sequential_glow), 1.3КБ.
- `think` — точки 1→2→3 (type_in, маска из последнего text-состояния "• • •"), 0.9КБ.

### Открыто
Назначить tgs-пресет каждому из 33 эмодзи. Многопутёвые (signal/windows/think/
brain/palette/monitor...) → стаггер/sequential; однопутёвые (heart/star/shield/db)
→ pulse_offset/assemble_in как целое.
