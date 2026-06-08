# План реализации: dropweb v2 — поэлементная анимация + среда для паков

> **For Claude:** REQUIRED SUB-SKILL: используйте superpowers:executing-plans
> (или subagent-driven-development) для выполнения плана задача-за-задачей.

**Goal:** Дать движку поэлементную анимацию (декомпозиция глифа на части + акцент-
элементы, каждый со своим таймлайном) и отделить определение пака от кода, не сломав
текущий пак dropweb.

**Architecture:** Подход C (гибрид). Новые `tools/elements.py` (извлечение частей →
`list[Element]`), `tools/stage.py` (компоновщик: per-element рендер через `phosphor2`
с `crt_post=False`, линейный композит `raster.over`/`add`, один общий CRT-проход в
конце), `tools/motion_presets.py` (пресеты движения). `build_emoji` ветвится: есть
блок `elements`/`motion` → Stage-путь, нет → старый `animate.EFFECTS` без изменений.

**Tech Stack:** Python 3.9, Pillow 11, numpy 2.0, scipy 1.13, ffmpeg/libvpx-vp9.
Источник истины по дизайну: `docs/plans/2026-06-07-element-animation-engine-design.md`.

---

## Соглашения этого плана (важно)

- **Тесты = модульные `__main__`-самотесты** (assert-based, печатают `<mod> OK ...`),
  запуск `.venv/bin/python3 -m tools.<mod>`. Pytest в репо НЕТ — не вводим.
- **TDD-адаптация:** сначала пишем скелет модуля с `__main__`-ассертами и телами
  `raise NotImplementedError`, запускаем (видим провал), затем реализуем, запускаем
  снова (видим `OK`).
- **Git не инициализирован** (`fatal: not a git repository`). Шаги «Checkpoint»
  опциональны: выполните после `git init` либо используйте как точки самопроверки.
  Не делать `git init` без согласия пользователя.
- Все команды запускать из корня репо `/Users/mac/Documents/projects/dropweb-channel`.
- Рабочее hi-res масок — как сейчас (512). Выходной размер — `size` (100).

---

## Task 0: Baseline

**Step 1:** Запустить существующие самотесты, убедиться что зелёные.

Run:
```bash
.venv/bin/python3 -m tools.easing
.venv/bin/python3 -m tools.phosphor2
.venv/bin/python3 -m tools.animate2
```
Expected: `easing OK ...`, `phosphor2 OK numpy=True ...`, и список эффектов `... OK`.

**Step 2:** Зафиксировать, что numpy/scipy доступны:
```bash
.venv/bin/python3 -c "import numpy,scipy;print(numpy.__version__,scipy.__version__)"
```
Expected: `2.0.2 1.13.1`.

---

## Task 1: tools/elements.py — Element + extract (identity, components)

**Files:**
- Create: `tools/elements.py`

**Step 1: Написать скелет + самотест (провальный).**

```python
"""elements — декомпозиция L-маски на адресуемые части (Element).

Контракт: extract(mask, spec) -> list[Element], где spec — dict из блока
emoji["elements"] (или None). Стратегии: identity | components | grid | rows |
cols | authored. Procedural обрабатывается в build_emoji (mask_from_shape).
"""
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image

try:
    import numpy as np
    from scipy import ndimage
    _NUMPY = True
except Exception:
    _NUMPY = False


@dataclass
class Element:
    id: str
    mask: Image.Image            # L, размер = hi-res рабочей маски
    anchor: tuple = (0.5, 0.5)   # пивот в норм. [0,1]
    z: int = 0
    blend: str = "over"          # "over" | "add"
    color: Optional[str] = None
    role: Optional[str] = None


def _centroid(mask):
    """Нормированный центроид непустой L-маски ([0,1],[0,1])."""
    raise NotImplementedError


def _mask_from_array(arr, size):
    raise NotImplementedError


def extract(mask, spec=None):
    """mask: PIL L. spec: dict|None. Возвращает list[Element] (>=1)."""
    raise NotImplementedError


if __name__ == "__main__":
    from PIL import ImageDraw
    hi = 256
    # identity: одна сплошная маска -> один элемент
    m = Image.new("L", (hi, hi), 0)
    ImageDraw.Draw(m).ellipse([60, 60, 196, 196], fill=255)
    els = extract(m, None)
    assert len(els) == 1 and els[0].mask.size == (hi, hi)
    # components: 3 разнесённых бара -> 3 элемента, отсортированы по x
    m2 = Image.new("L", (hi, hi), 0)
    d = ImageDraw.Draw(m2)
    for k, x in enumerate((40, 110, 180)):
        d.rectangle([x, 120 - k * 20, x + 30, 200], fill=255)
    els2 = extract(m2, {"split": "components", "sort": "x"})
    assert len(els2) == 3, len(els2)
    xs = [e.anchor[0] for e in els2]
    assert xs == sorted(xs)
    print("elements OK  identity=%d components=%d" % (len(els), len(els2)))
```

**Step 2: Запустить — убедиться что падает.**
Run: `.venv/bin/python3 -m tools.elements`
Expected: `NotImplementedError`.

**Step 3: Реализовать `_centroid`, `_mask_from_array`, `extract` (identity + components).**

```python
def _centroid(mask):
    a = np.asarray(mask, dtype=np.float32)
    s = a.sum()
    if s <= 0:
        return (0.5, 0.5)
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    cx = float((xs * a).sum() / s) / (a.shape[1] - 1)
    cy = float((ys * a).sum() / s) / (a.shape[0] - 1)
    return (cx, cy)


def _mask_from_array(arr, size):
    out = Image.new("L", (size, size), 0)
    out.putdata(arr.astype("uint8").flatten())
    return out


def _identity(mask):
    return [Element(id="glyph", mask=mask, anchor=_centroid(mask), z=0)]


def _components(mask, sort="x", min_area=12):
    if not _NUMPY:
        return _identity(mask)
    a = np.asarray(mask)
    lbl, n = ndimage.label(a > 40)
    if n <= 1:
        return _identity(mask)
    els = []
    for i in range(1, n + 1):
        comp = (lbl == i)
        if comp.sum() < min_area:
            continue
        part = np.where(comp, a, 0)
        pm = _mask_from_array(part, mask.size[0])
        els.append(Element(id="c%d" % i, mask=pm, anchor=_centroid(pm), z=0,
                           role="component"))
    key = {"x": lambda e: e.anchor[0], "y": lambda e: e.anchor[1],
           "dist": lambda e: (e.anchor[0]-0.5)**2 + (e.anchor[1]-0.5)**2}
    els.sort(key=key.get(sort, key["x"]))
    for idx, e in enumerate(els):
        e.id = "c%d" % idx
    return els or _identity(mask)


def extract(mask, spec=None):
    mask = mask.convert("L")
    if not spec:
        return _identity(mask)
    split = spec.get("split", "identity")
    if split == "components":
        return _components(mask, sort=spec.get("sort", "x"))
    # grid/rows/cols/authored — добавляются в Task 2/3
    return _identity(mask)
```

**Step 4: Запустить — зелёный.**
Run: `.venv/bin/python3 -m tools.elements`
Expected: `elements OK  identity=1 components=3`.

**Step 5: Checkpoint.** `feat(elements): Element + extract identity/components`.

---

## Task 2: tools/elements.py — grid / rows / cols

**Files:** Modify: `tools/elements.py`

**Step 1:** Добавить в `__main__` ассерт: `grid:2x2` на маске из 4 квадрантов даёт 4
элемента; `rows:3` на сплошной маске — 3 непустых горизонтальных среза.

**Step 2:** Запустить — падает (split не реализован).

**Step 3:** Реализовать `_grid(mask, rows, cols)` и `_slices(mask, n, axis)`:
- режем по bbox содержимого маски на сетку rows×cols / N полос по оси;
- каждый кусок — отдельный Element с `role="cell"` и своим центроидом;
- пустые куски (sum<=min_area) отбрасываем.
- В `extract` добавить ветки: `split.startswith("grid:")` (парсить `RxC`),
  `split.startswith("rows:")`, `split.startswith("cols:")`.

**Step 4:** Запустить — зелёный (`grid=4 rows=3`).

**Step 5: Checkpoint.** `feat(elements): grid/rows/cols split`.

---

## Task 3: tools/elements.py — authored regions

**Files:** Modify: `tools/elements.py`

**Step 1:** В `__main__` ассерт: `authored` с двумя bbox-регионами на маске даёт 2
элемента с заданными id/role/z/blend.

**Step 2:** Запустить — падает.

**Step 3:** Реализовать `_authored(mask, regions)`: для каждого региона
`{id, role?, bbox:[x0,y0,x1,y1] (норм. 0..1), z?, blend?, color?}` вырезать
подмаску (умножение на прямоугольную/полигональную маску региона), собрать Element.
Полигоны — через `PIL.ImageDraw.polygon` маску. Ветка в `extract`:
`split == "authored"` → `_authored(mask, spec["regions"])`.

**Step 4:** Запустить — зелёный.

**Step 5: Checkpoint.** `feat(elements): authored regions`.

---

## Task 4: tools/stage.py — staggered_phase + transform (бесшовность)

**Files:** Create: `tools/stage.py`

**Step 1: Скелет + самотест на бесшовный инвариант.**

```python
"""stage — раннер таймлайнов + компоновщик элементов в один кадр.

Каждый элемент рендерится через phosphor2(crt_post=False), композитится в
линейном свете (raster.over/add), затем ОДИН общий CRT-проход на кадр.
Инвариант: transform(p=0) == transform(p=1) (бесшовный луп).
"""
import math
from PIL import Image
from . import easing
from .phosphor2 import phosphor2

try:
    import numpy as np
    from . import raster, crt
    _NUMPY = True
except Exception:
    _NUMPY = False


def staggered_phase(p, index, count, stagger):
    """Локальная фаза элемента index из count при сдвиге stagger.
    Обёрнута в [0,1) так, что при p=0 и p=1 даёт одно и то же значение."""
    raise NotImplementedError


def apply_transform(mask, size, tf):
    """Применить аффинный трансформ tf={dx,dy,sx,sy,rot,anchor} к L-маске."""
    raise NotImplementedError


if __name__ == "__main__":
    # бесшовность: фаза на p=0 и p=1 совпадает для всех элементов
    for idx in range(4):
        a = staggered_phase(0.0, idx, 4, 0.12)
        b = staggered_phase(1.0, idx, 4, 0.12)
        assert abs(a - b) < 1e-9, (idx, a, b)
    print("stage.phase OK")
```

**Step 2:** Запустить — падает (`NotImplementedError`).

**Step 3:** Реализовать:

```python
def staggered_phase(p, index, count, stagger):
    off = (index * stagger) % 1.0
    return ((p - off) % 1.0)


def apply_transform(mask, size, tf):
    base = mask.convert("L").resize((size, size), Image.LANCZOS)
    ax, ay = tf.get("anchor", (0.5, 0.5))
    sx, sy = tf.get("sx", 1.0), tf.get("sy", 1.0)
    rot = tf.get("rot", 0.0)
    dx, dy = tf.get("dx", 0.0), tf.get("dy", 0.0)
    cx, cy = ax * size, ay * size
    w = max(1, int(size * sx)); h = max(1, int(size * sy))
    r = base.resize((w, h), Image.LANCZOS)
    if rot:
        r = r.rotate(rot, resample=Image.BICUBIC, expand=True, fillcolor=0)
    out = Image.new("L", (size, size), 0)
    out.paste(r, (int(cx - r.size[0] / 2 + dx), int(cy - r.size[1] / 2 + dy)))
    return out
```

**Step 4:** Запустить — `stage.phase OK`.

**Step 5: Checkpoint.** `feat(stage): staggered_phase + apply_transform`.

---

## Task 5: tools/stage.py — render() компоновщик + один CRT

**Files:** Modify: `tools/stage.py`

**Step 1:** Расширить самотест: собрать 3 элемента (из `elements._components`),
прогнать `render(...)` на n=12 → проверить: список из 12 RGBA 100×100, и дельта
кадр0↔кадрN мала (бесшовность), альфа в углу = 0.

**Step 2:** Запустить — падает (`render` нет).

**Step 3:** Реализовать `render`:

```python
def _pil_to_buf(img):
    arr = np.asarray(img).astype(np.float32) / 255.0
    a = arr[..., 3:4]
    lin = raster.srgb_to_linear(arr[..., :3]) * a
    return np.concatenate([lin, a], axis=-1)


def render(elements, motion_fn, size, color, n=90, *, crt_kw=None):
    """elements: list[Element]; motion_fn(element, index, count, p)->tf.
    Возвращает n RGBA-кадров (бесшовный луп)."""
    crt_kw = crt_kw or dict(barrel_k=0.07, chroma=1.0, scan_depth=0.28,
                            scan_period=2.2, vig=0.36, noise=0.03)
    count = len(elements)
    out = []
    for i in range(n):
        p = easing.loop_phase(i, n)
        if _NUMPY:
            comp = raster.new_buffer(size, size)
        else:
            comp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        for idx, el in enumerate(sorted(elements, key=lambda e: e.z)):
            tf = motion_fn(el, idx, count, p)
            m = apply_transform(el.mask, size, tf)
            col = el.color or color
            glow = tf.get("glow", 0.95)
            alpha = tf.get("alpha", 1.0)
            part = phosphor2(m, size=size, color=col, glow=glow,
                             phase=p, crt_post=False, scanlines=False)
            if alpha < 1.0:
                part.putalpha(part.getchannel("A").point(lambda a: int(a*alpha)))
            if _NUMPY:
                pb = _pil_to_buf(part)
                comp = raster.add(comp, pb) if el.blend == "add" else raster.over(comp, pb)
            else:
                comp.alpha_composite(part)
        if _NUMPY:
            comp = crt.apply_crt(comp, phase=p, **crt_kw)
            out.append(raster.to_pil(comp))
        else:
            out.append(comp)
    return out
```

**Step 4:** Запустить — зелёный (бесшовность + альфа угла = 0).

**Step 5: Checkpoint.** `feat(stage): render compositor + single CRT pass`.

---

## Task 6: tools/motion_presets.py — пресеты движения

**Files:** Create: `tools/motion_presets.py`

**Step 1:** Скелет + самотест: для каждого пресета `fn(el, idx, count, p, params)`
возвращает dict-трансформ, и `fn(...,0.0)==fn(...,1.0)` (бесшовность).

**Step 2:** Запустить — падает.

**Step 3:** Реализовать пресеты (используют `stage.staggered_phase`, `easing`):
- `stagger_rise(el, idx, count, p, prm)`: локальная фаза, элемент поднимается
  снизу (`dy` от +K к 0) и проявляется (`alpha`/`glow`) на `easing.BRAND`,
  затем держится и бесшовно уходит.
- `sequential_glow`: форма стоит, `glow`/`alpha` загораются по очереди (по idx),
  держатся, гаснут к концу лупа.
- `pulse_offset`: `sx/sy` пульс на `loop_sin(p + idx/count)`.
- `lead_follow`: ведущий (idx==0) на BRAND, ведомый — лаговая копия (сдвиг фазы
  `prm.lag`), параметризуется ролью.
- `assemble_in`: каждая часть стартует из офсета `(odx,ody)` (по idx/углу) и
  слетается к 0 на SNAP в первой половине лупа, держится, расходится в конце.
- `type_in`: части (по x) проявляются по очереди ступенчато + курсор-акцент.
- `segment_rebuild`: `rot` сегмента + поочерёдное проявление.
- `orbit`: `dx,dy = R*cos/sin(2pi*(p+idx/count))` — для акцентов.

Registry:
```python
PRESETS = {
    "stagger_rise": stagger_rise, "sequential_glow": sequential_glow,
    "pulse_offset": pulse_offset, "lead_follow": lead_follow,
    "assemble_in": assemble_in, "type_in": type_in,
    "segment_rebuild": segment_rebuild, "orbit": orbit,
}
def make_motion(name, params):
    fn = PRESETS[name]
    return lambda el, idx, count, p: fn(el, idx, count, p, params or {})
```

**Step 4:** Запустить — `motion_presets OK  presets=8 seamless=True`.

**Step 5: Checkpoint.** `feat(motion): preset library`.

---

## Task 7: tools/stage.py — акцент-элементы

**Files:** Modify: `tools/stage.py` (или `tools/accents.py`)

**Step 1:** Самотест: `build_accents(spec, size, n)` -> для каждого кадра список
`Element(blend="add")` с процедурной маской (искры/кольцо/скан-бар/орбита).

**Step 2:** Запустить — падает.

**Step 3:** Реализовать генераторы (переиспользуют `particles.ember_loop` для
spark/ember; `ImageDraw.ellipse` для ring; горизонтальная полоса для scanbar).
Акценты возвращаются как элементы с `blend="add"` и собственным motion (orbit/
fade), вливаются в `render` тем же путём.

**Step 4:** Запустить — зелёный.

**Step 5: Checkpoint.** `feat(stage): accent elements (spark/ring/scanbar/orbit)`.

---

## Task 8: build_emoji.py — Stage-путь + mask_from_shape части

**Files:** Modify: `tools/build_emoji.py`

**Step 1:** В `build_one` после получения `mask` (строка ~252, перед выбором `fn`)
добавить ветку:
```python
if spec.get("elements") or spec.get("motion"):
    from . import elements as _el, stage as _st, motion_presets as _mp
    els = _el.extract(mask, spec.get("elements"))
    mo = spec.get("motion", {})
    motion_fn = _mp.make_motion(mo.get("preset", "sequential_glow"),
                                mo.get("params", {}))
    frames = _st.render(els, motion_fn, _SIZE, render_color,
                        n=spec.get("frames", 90))
    # accents (опц.): дорисовать аддитивно (Task 7)
else:
    frames = fn(mask, _SIZE, render_color, **kw)   # СТАРЫЙ путь без изменений
```
Существующий путь оставить нетронутым (важно для совместимости).

**Step 2:** Рефактор `mask_from_shape`: добавить параметр `parts=False`; при
`parts=True` для `bars`/`arrow_down`/`warning` возвращать `list[(role, L-mask)]`
вместо одной маски. `procedural` split в `extract` тогда читает их (передать
через spec). Минимально: реализовать для `bars` (4 бара) и `warning`.

**Step 3:** Самопроверка сборки одного пилотного эмодзи (Task 10) — отложить до
Task 10; здесь только: `.venv/bin/python3 -c "import tools.build_emoji"` без ошибок,
и сборка текущего НЕ-элементного эмодзи не изменилась:
```bash
.venv/bin/python3 -m tools.build_emoji --id db
```
Expected: `db ... КБ ... build/emoji/db.webm` как раньше.

**Step 4: Checkpoint.** `feat(build): stage path + shape parts (additive)`.

---

## Task 9: Среда для паков — packs/<name>/ + --pack

**Files:** Modify: `tools/build_emoji.py`; Create: `packs/dropweb/pack.json`

**Step 1:** Перенос: скопировать `emoji_set.json` → `packs/dropweb/pack.json`;
ассеты, на которые ссылаются спеки (`assets/...`), оставить достижимыми (либо
симлинк/копия в `packs/dropweb/assets/`, либо резолвить от ROOT — выбрать ROOT-
резолв для минимального диффа).

**Step 2:** В `build_emoji`:
- добавить `--pack` (default `dropweb`);
- `load_set()` читает `packs/<pack>/pack.json`, фоллбэк на корневой
  `emoji_set.json` если файла пака нет (совместимость);
- выход → `build/<pack>/emoji/` (в `build_one` параметр `out_dir`).

**Step 3:** Проверка обоих путей:
```bash
.venv/bin/python3 -m tools.build_emoji --pack dropweb --id db
.venv/bin/python3 -m tools.build_emoji --id db   # фоллбэк на старый emoji_set.json
```
Expected: оба собирают `db.webm` (в `build/dropweb/emoji/` и `build/emoji/`).

**Step 4: Checkpoint.** `feat(env): packs/<name> layout + --pack`.

---

## Task 10: Пилот (signal, windows, think, eyes) + сборка + QA

**Files:** Modify: `packs/dropweb/pack.json`

**Step 1:** Добавить блоки `elements`/`motion` пилотным эмодзи:
- `signal`: `elements:{split:"procedural"}` (4 бара) `motion:{preset:"stagger_rise",stagger:0.12}`
- `windows`: `elements:{split:"grid:2x2"}` `motion:{preset:"sequential_glow",stagger:0.14}`
- `think`: `elements:{split:"components",sort:"x"}` `motion:{preset:"sequential_glow"}`
- `eyes`: `elements:{split:"authored","regions":[{id:"iris",...},{id:"lid",...}]}` `motion:{preset:"lead_follow",params:{lag:0.08}}`

**Step 2:** Собрать каждый и проверить бюджет:
```bash
for id in signal windows think eyes; do .venv/bin/python3 -m tools.build_emoji --pack dropweb --id $id; done
```
Expected: каждый `<=256.0 КБ`, путь `build/dropweb/emoji/<id>.webm`.

**Step 3:** Крупный план для глаза:
```bash
RENDER_SIZE=512 .venv/bin/python3 -m tools.build_emoji --pack dropweb --id signal
```
Просмотреть webm: бары встают по очереди, луп бесшовный, скан-линии единые.

**Step 4:** Если есть подключённое устройство — залить через @stickers и глянуть в
Telegram (ручной шаг, `docs/UPLOAD.md`).

**Step 5: Checkpoint.** `feat(pilot): element animation for signal/windows/think/eyes`.

---

## Task 11: Документация + финальная верификация

**Files:** Modify: `docs/animation-playbook.md`, `README.md`

**Step 1:** В `animation-playbook.md` дописать раздел «Поэлементный движок»:
Element/Stage, стратегии split, пресеты, инвариант бесшовного стаггера, порядок
рендера (per-element phosphor2 → линейный композит → один CRT).

**Step 2:** В `README.md` — пункт про `packs/<name>/` и `--pack`.

**Step 3:** Прогнать ВСЕ самотесты + проверить, что не-элементные эмодзи не
изменились:
```bash
for m in easing phosphor2 elements stage motion_presets animate2; do .venv/bin/python3 -m tools.$m; done
.venv/bin/python3 -m tools.build_emoji --pack dropweb --id db
```
Expected: все `OK`, `db.webm` собирается как раньше.

**Step 4: Checkpoint.** `docs: element engine + packs env`.

---

## Карта файлов (итог)

Новые: `tools/elements.py`, `tools/stage.py`, `tools/motion_presets.py`,
`packs/dropweb/pack.json`, этот план + дизайн-док.
Изменённые (аддитивно): `tools/build_emoji.py`, `docs/animation-playbook.md`,
`README.md`.
Без изменений: `phosphor2.py`, `raster.py`, `bloom.py`, `crt.py`, `particles.py`,
`easing.py`, `encode.py`, `animate.py`, `animate2.py`.
