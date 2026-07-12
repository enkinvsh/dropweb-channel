# Studio redesign + «Пак из референсов» — спек gpt-5.6-sol (2026-07-12)

**Итог:** студия должна стать не длинной страницей настроек, а рабочим местом с неизменными библиотекой и превью и одним контекстным правым модулем. Основная структура: фиксированная панель пака сверху, слева сетка стикеров, в центре выбранный стикер, справа четыре вкладки: **«Создать» / «Пак из референсов» / «Анимация» / «Экспорт»**.

Новая пакетная генерация строится как **план от `gpt-5.6-terra` + клиентская очередь с concurrency = 2**. Сервер не хранит состояние заданий: он только составляет план, сохраняет референсы и обрабатывает отдельные `/api/generate`; состояние очереди, прогресс, повторы и черновики живут в браузере.

---

# S1. Information architecture & layout

## 1. Главная структура

### Desktop, ширина от 1180 px

```text
┌──────────────────────────────────────────────────────────────────────┐
│ STUDIO · [пак dropweb ▼]  [+ Новый пак]        [Переимен.] [Удалить] │ 64 px
├───────────────┬──────────────────────┬───────────────────────────────┤
│ СТИКЕРЫ       │ ПРЕВЬЮ              │ Создать | Пак из реф. | ...  │
│               │                      │                               │
│ grid          │ выбранный стикер     │ контекстная рабочая панель    │
│ independent   │ sticky               │ independent scroll            │
│ scroll        │                      │                               │
└───────────────┴──────────────────────┴───────────────────────────────┘
```

CSS-геометрия:

```css
.app {
  display: grid;
  grid-template-rows: 64px minmax(0, 1fr);
  height: 100dvh;
}

.workspace {
  display: grid;
  grid-template-columns:
    244px
    minmax(340px, 400px)
    minmax(520px, 1fr);
  min-height: 0;
}
```

Каждая из трёх зон прокручивается независимо. Верхняя панель и вкладки правой зоны остаются видимыми.

### Поведение на меньшей ширине

- **768–1179 px:** сетка стикеров становится горизонтальной полосой высотой `116px` под верхней панелью; ниже остаются две колонки `340px / minmax(0, 1fr)`.
- **До 767 px:** сетка остаётся горизонтальной; превью и активная вкладка идут вертикально. Верхняя панель пака переносит действия во вторую строку.
- Минимальный целевой desktop viewport: `1100 × 700`.
- Никакого горизонтального скролла всей страницы.

## 2. Верхняя панель пака

Всегда видима, едина для всех режимов.

Слева направо:

1. `STUDIO` как небольшой product label.
2. Селектор текущего пака `#packsel`.
3. Текстовый индикатор: `24 стикера · 2 не сохранены`.
4. `#newpack` — «Новый пак».
5. `#renpack` — «Переименовать».
6. `#delpack` — «Удалить пак», danger-стиль.

Решения:

- Переименование и удаление больше не выглядят равнозначно выбору пака.
- Удаление находится последним и визуально отделено разделителем.
- При активной пакетной генерации селектор и операции над паком блокируются.
- Над панелью пакетной генерации выводится: `Результаты попадут в пакет «dropweb»`.
- Для генерации в новый пак пользователь сначала нажимает «Новый пак», затем открывает «Пак из референсов».

## 3. Левая зона: «Стикеры»

Сетка остаётся всегда видимой, потому что это навигация по результатам, а не один из этапов workflow.

Верх зоны:

```text
СТИКЕРЫ                                      24
[Все] [Черновики 2] [Сохранённые 22]
```

Фильтры новые, но полностью клиентские:

- `Все`;
- `Черновики`;
- `Сохранённые`.

Карточка стикера содержит:

- анимированную миниатюру;
- `slug`;
- существующий anchor/emoji как контентная метка;
- статусную точку и текст:
  - `Черновик`;
  - `Сохранён`;
  - `Генерация`;
  - `Ошибка`.

Состояние нельзя обозначать только цветом.

Порядок:

- новые пакетные результаты вставляются в начало;
- существующий порядок `ORDER` не меняется после сохранения;
- выбранный элемент имеет акцентную рамку без сильного свечения.

Пустое состояние:

> В этом паке пока нет стикеров.  
> Откройте «Создать» для одного стикера или «Пак из референсов» для серии.

## 4. Центральная зона: «Превью»

Центр отвечает только за выбранный стикер. Здесь больше нет экспорта и рандомизации.

### Шапка

- label `ПРЕВЬЮ`;
- имя `anchor + slug`;
- badge `Черновик` / `Сохранён`;
- `#pausebtn`;
- `#delemoji`.

### Основная область

- `#big`;
- переключатель фона `#bgrow`:
  - `Клетка`;
  - `Чёрный`;
  - `Чат`;
  - `Светлый`.
- метаданные:
  - slug;
  - набор animation kinds;
  - количество shape groups, если известно;
  - предупреждение о сложности.

### Нижняя панель выбранного стикера

Всегда видима:

```text
Изменения не сохранены                 [Сохранить]
```

Здесь находится существующий `#save`.

Правила:

- «Сохранить» всегда outline-кнопка, не второй зелёный primary CTA.
- При отсутствии изменений она disabled.
- После сохранения статус меняется на `Сохранено`.
- Для пакетного черновика сохранение использует его собственные `prompt_en`, `idea_ru`, `uses_ref` и `ref_set`, а не глобальный prompt вкладки «Создать».
- Удаление несохранённого черновика происходит только в клиенте.
- Удаление сохранённого стикера вызывает `/api/emoji/delete`.

`#genloader` больше не перекрывает центральное превью для всей студии. Статус одиночной генерации показывается в правой вкладке «Создать», а пакетные статусы — в карточках очереди. Выбранный генерирующийся элемент может показывать skeleton в `#big`.

## 5. Правая зона: вкладки workflow

Вкладки:

1. **Создать**
2. **Пак из референсов**
3. **Анимация**
4. **Экспорт**

Tab bar sticky внутри правой зоны. При переключении вкладок введённые данные не сбрасываются.

Используются настоящие `button[role=tab]`, `aria-selected`, клавиши Left/Right и связанный `tabpanel`.

---

## 6. Вкладка «Создать»

Это новая стартовая вкладка при открытии студии.

### Блок 1. Идея

```text
ИДЕЯ СТИКЕРА
[ textarea: Например: пингвин с ноутбуком                  ]

[x] Улучшить идею перед генерацией (GPT)

[Подготовить промт]                      статус prompt rewrite
```

Здесь находятся:

- `#prompt`;
- `#autoimprove`;
- `#autoprompt`.

Название «Авто-промт» заменить на **«Подготовить промт»**. Поведение остаётся fill-only.

Placeholder:

> Например: маскот сервиса празднует успешную оплату

### Блок 2. Источник

```text
ИСТОЧНИК
[Без референса] [Добавить референс]
```

Здесь находятся:

- `#refBtn`;
- `#reffile`;
- `#refthumb`;
- `#refimg`;
- `#refclear`.

После выбора изображения показывается горизонтальная миниатюра с именем файла и действием «Убрать».

Это одиночный референс. Для 2–3 изображений интерфейс явно направляет во вкладку «Пак из референсов».

### Блок 3. Параметры

Двухколоночная компактная секция:

- `#genid` — `ID / slug`;
- `#gencolor` — `Цвет`;
- `#genmodel` — `Модель`;
- `#genfit` — `Размер в кадре`.

Модель сохраняет существующий выбор:

- `ChatGPT` — default;
- `Nano Banana 2 · резервный`.

`#genid` автоматически заполняется через `/api/prompt`, но остаётся редактируемым.

### Основное действие

Внизу sticky action bar вкладки:

```text
Генерация обычно занимает 1–3 минуты.

[                     Генерировать                     ]
```

Здесь находится `#generate`. Это единственная заполненная зелёная CTA вкладки.

Во время запроса:

- текст `Генерируем стикер…`;
- elapsed timer `01:42`;
- кнопка disabled;
- вкладки и просмотр существующих стикеров продолжают работать.

### Блок 4. Действия с выбранным

Ниже параметров, не рядом с Generate:

- `#regen` — «Перегенерировать выбранный»;
- `#refitBtn` — «Пересчитать размер»;
- `#uploadBtn` — «Загрузить PNG»;
- `#pngfile`.

Все secondary outline.

`#regen` disabled, если текущий элемент не был создан генератором или отсутствует prompt.  
`#refitBtn` disabled, если нет маски.  
`#uploadBtn` работает независимо от API-ключа.

---

## 7. Вкладка «Анимация»

Сюда переносится весь текущий блок «Анимация / Стиль».

Структура:

### Быстрый старт

- `#brandpreset` — «Бренд-пресет».
- `#addlayer` — «Добавить слой».
- текущий счётчик: `1 из 4 слоёв`.

### Слои анимации

`#layers`, каждый слой:

- номер слоя;
- kind и category;
- предыдущий/следующий kind;
- slider выбора kind;
- `amp`;
- `ov`;
- направление;
- фаза;
- удалить слой.

Слой становится accordion-карточкой:

- заголовок всегда виден;
- параметры раскрыты только у активного слоя;
- одновременно открыт один слой;
- добавление нового слоя сразу раскрывает его.

### Ритм и внешний вид

В отдельных секциях:

**Ритм**

- `#beats`.

**Цвет**

- `#sw`;
- `#custom`;
- `#rainbow`.

**Контур**

- `#outline`;
- `#width`.

**Фон-плитка**

- `#bgtile`;
- `#bgctl`;
- `#bgrx`;
- `#bgfill`.

`Толщина` disabled и визуально приглушена, пока обводка выключена.  
`Радиус фона` и `Цвет фона` скрыты, пока плитка выключена.

### Быстрые варианты

Внизу отдельный блок **«Быстрые варианты»**:

- `rnd()` — «Случайная анимация»;
- `rnd(true)` — «Экспериментальная»;
- `rndAll()` — «Случайные для всего пака»;
- `applyAll()` — «Применить настройки ко всему паку».

Для двух операций над всем паком требуется inline-подтверждение:

> Изменить анимацию у всех 24 стикеров?  
> `[Отмена] [Применить]`

Не использовать `window.confirm()`.

---

## 8. Вкладка «Экспорт»

Здесь остаются только операции получения файлов.

### Текущий стикер

- имя;
- параметры `.tgs`: `512×512 · 60 fps · loop`;
- `exportOne()` — **«Скачать выбранный .tgs»**, primary CTA.

### Весь пак

- количество стикеров;
- предупреждение о несохранённых черновиках;
- `exportAll()` — «Скачать весь пак .zip», secondary.

Правила:

- экспорт использует текущее состояние в браузере, включая несохранённые настройки;
- если есть черновики, перед ZIP показывается предупреждение:
  > В ZIP попадут 2 несохранённых черновика.
- техническая подсказка про `120 BPM` остаётся здесь, в раскрываемом блоке «Параметры формата».

---

## 9. Полная карта существующих контролов

| Существующий контроль | Новый дом |
|---|---|
| `packsel` | фиксированная верхняя панель |
| `newpack` | верхняя панель, «Новый пак» |
| `renpack` | верхняя панель, secondary |
| `delpack` | верхняя панель, danger |
| grid | всегда видимая левая зона |
| `big` | всегда видимый центр |
| `pausebtn` | шапка превью |
| `delemoji` | шапка превью |
| клетка / чёрный / чат / светлый | под большим превью |
| `save` | нижняя панель превью |
| `prompt` | «Создать» → «Идея» |
| `autoimprove` | «Создать» → «Идея» |
| `autoprompt` | «Создать» → «Подготовить промт» |
| `genid` | «Создать» → «Параметры» |
| `gencolor` | «Создать» → «Параметры» |
| `genmodel` | «Создать» → «Параметры» |
| `genfit` | «Создать» → «Параметры» |
| `refBtn`, `reffile`, `refthumb`, `refclear` | «Создать» → «Источник» |
| `generate` | sticky footer вкладки «Создать» |
| `uploadBtn`, `pngfile` | «Создать» → «Действия с выбранным» |
| `regen` | «Создать» → «Действия с выбранным» |
| `refitBtn` | «Создать» → «Действия с выбранным» |
| `brandpreset` | «Анимация» → «Быстрый старт» |
| `addlayer`, `layers` | «Анимация» → «Слои» |
| `beats` | «Анимация» → «Ритм» |
| `sw`, `custom`, `rainbow` | «Анимация» → «Цвет» |
| `outline`, `width` | «Анимация» → «Контур» |
| `bgtile`, `bgrx`, `bgfill` | «Анимация» → «Фон-плитка» |
| `rnd`, `rnd(true)` | «Анимация» → «Быстрые варианты» |
| `rndAll`, `applyAll` | «Анимация» → «Быстрые варианты» |
| `exportOne`, `exportAll` | «Экспорт» |

Ни один существующий control или workflow не удаляется.

---

# S2. Новая функция «Пак из референсов»

## 1. Продуктовое решение

Использовать **`gpt-5.6-terra`** для анализа и составления плана.

Причины:

- vision уже проверен через локальный proxy;
- задача ограниченная и структурированная;
- Terra достаточно качественен для классификации визуальной идентичности и генерации JSON;
- Sol не устранит основной bottleneck: 6–18 дорогих image-generation запросов;
- фиксированная модель делает поведение воспроизводимым.

`gpt-5.6-sol` в интерфейс не выводить и не использовать для этого workflow.

Для изображений пакетного режима использовать только **`gpt-image-2`**:

- multi-reference `/images/edits` подтверждён;
- текущий Gemini path поддерживает только один reference;
- смешивание моделей внутри одного пака ухудшит консистентность.

## 2. Архитектура выполнения

Выбранный вариант:

1. `/api/pack/plan` принимает 2–3 изображения и составляет план.
2. Сервер сохраняет нормализованные референсы и возвращает `ref_set`.
3. Браузер запускает отдельный `/api/generate` для каждого пункта.
4. Одновременно выполняются не более **2 запросов**.
5. Сервер не хранит queue/job state.
6. Готовые bases и статусы находятся в JS-состоянии страницы.
7. Сохранение в `pack.json` и `bases.json` выполняется отдельно.

Почему concurrency = 2:

- даёт примерно двукратное ускорение;
- не создаёт три параллельных image jobs плюс внутренние retries;
- меньше вероятность 429, зависаний и перегрузки локального proxy;
- 12 стикеров займут ориентировочно 10–15 минут вместо 24 минут serial.

Concurrency 3 в первой версии не разрешать и не настраивать через UI.

## 3. Wizard

### Шаг 1. Референсы

```text
ПАК ИЗ РЕФЕРЕНСОВ
Создаём серию в паке «dropweb»

┌──────────────────────────────────────────────┐
│ Перетащите сюда 2–3 изображения              │
│ Логотип, скриншот интерфейса, маскот          │
│                                              │
│                  Выбрать файлы               │
└──────────────────────────────────────────────┘

[thumb logo.png ×] [thumb app.png ×] [thumb mascot.png ×]

Название или тема
[ Dropweb — доступ к AI-сервисам                 ]

Количество
[6] [12] [18]

[                 Составить план                 ]
```

Правила:

- минимум 2, максимум 3 файла;
- PNG, JPEG или WebP;
- максимум `10 MB` на файл;
- сервер нормализует в PNG;
- после трёх файлов dropzone disabled;
- default count: **12**;
- theme optional;
- если theme пустой, planner должен вывести название/тему из изображений;
- изображения можно переставлять drag-and-drop до составления плана;
- кнопка «Составить план» — единственная primary CTA.

### Шаг 2. План

Header:

```text
План: 12 стикеров
4 используют фирменные формы · 8 тематических сюжетов

[Перегенерировать план]
```

Каждая строка:

```text
01  [service-success________]  [Использовать референсы ●]
    Успешное подключение к сервису
    Промт: plug entering a compact portal with a clear success check...
                                                        [Удалить]
```

Поля:

- порядковый номер;
- editable `slug`;
- editable `idea_ru`;
- toggle `uses_ref`;
- раскрываемое editable поле `prompt_en`;
- удалить строку.

Правила валидации:

- slug: `^[a-z0-9][a-z0-9_-]{0,31}$`;
- slug уникален внутри плана;
- slug не конфликтует с существующим `ORDER`;
- сервер при первичном плане автоматически добавляет `-2`, `-3` при конфликте;
- нельзя начать генерацию при ошибках slug или пустом prompt;
- после удаления допустимо любое количество от 1 до исходного N;
- добавление новых строк вручную не входит в первую версию;
- `prompt_en` — фактический input генератора;
- `idea_ru` — человекочитаемое название результата;
- рядом с раскрытым prompt показывается пояснение:
  > Генерация использует этот английский промт. Стиль добавится автоматически.

«Перегенерировать план»:

- повторно использует сохранённый `ref_set`;
- до начала генерации заменяет текущий план без подтверждения;
- после появления готовых результатов требует inline-подтверждение и сбрасывает только план/очередь, но не удаляет уже созданные черновики из главной сетки.

Внизу:

```text
Оценка: около 10–15 минут · одновременно генерируются 2

[                 Сгенерировать всё                 ]
```

### Шаг 3. Генерация

План превращается в progress grid, две колонки.

Состояния карточки:

- `В очереди`;
- `Генерируется · 01:18`;
- `Готово`;
- `Ошибка`;
- `Пропущено`;
- `Сохранено`.

Карточка:

```text
┌──────────────────────────────┐
│ [preview / skeleton]         │
│ service-success              │
│ Успешное подключение         │
│ Генерируется · 01:18         │
└──────────────────────────────┘
```

Для failed:

```text
Ошибка: upstream timeout
[Повторить] [Пропустить]
```

Глобальный header:

```text
Готово 7 из 12 · Генерируются 2 · Ошибок 1
██████████████░░░░░░ 58%

[Остановить очередь]
```

«Остановить очередь»:

- прекращает запуск новых элементов;
- уже отправленные два запроса не отменяет;
- после их завершения оставшиеся получают статус `Пропущено`;
- кнопка меняется на «Продолжить очередь».

### Повторы

- В `gen_icon` уже есть три backend retry для timeout, connection error, 429 и 5xx.
- Клиент не выполняет дополнительный автоматический retry.
- После окончательной ошибки очередь продолжает остальные элементы.
- Доступны:
  - «Повторить» на карточке;
  - «Повторить все ошибки» внизу.
- Ручной retry добавляет элемент в начало очереди, но всё равно соблюдает limit 2.
- «Пропустить» меняет `failed → skipped` и убирает ошибку из незавершённого результата.

### Результаты

После успешного `/api/generate`:

1. Результат сразу добавляется в начало основной сетки.
2. Получает badge `Черновик`.
3. Его можно выбрать и настроить во вкладке «Анимация».
4. Карточка progress grid использует то же preview.
5. Сохраняется metadata:

```js
draftMeta[id] = {
  source: "pack-ref",
  idea_ru,
  prompt_en,
  ref_set,
  uses_ref
};
```

Действия:

- «Сохранить» в центральном preview — один результат;
- «Удалить» — удалить черновик из client state;
- **«Сохранить все готовые»** — sequential save всех готовых черновиков;
- «Удалить все несохранённые» — inline confirmation.

`Сохранить все готовые` выполняет `/api/save` **последовательно**, а не параллельно: существующий save handler использует read-modify-write и параллельные записи могут потерять изменения.

После bulk save:

> Сохранено 10 из 10 готовых.  
> 1 ошибка и 1 пропущенный элемент не сохранены.

## 4. API: составление плана

### Endpoint

```http
POST /api/pack/plan
Content-Type: application/json
```

### Первый запрос

```json
{
  "pack": "dropweb",
  "theme": "Dropweb — access to global AI services",
  "count": 12,
  "refs": [
    {
      "name": "logo.png",
      "mime": "image/png",
      "data_b64": "iVBORw0KGgo..."
    },
    {
      "name": "app.jpg",
      "mime": "image/jpeg",
      "data_b64": "/9j/4AAQSk..."
    }
  ]
}
```

`data_b64` принимается как чистый base64 или data URL.

### Повторное составление плана

```json
{
  "pack": "dropweb",
  "theme": "Dropweb — access to global AI services",
  "count": 12,
  "ref_set": "refs-7f4c19a2"
}
```

`refs` и `ref_set` взаимоисключающие.

### Успешный ответ

```json
{
  "ok": true,
  "model": "gpt-5.6-terra",
  "ref_set": "refs-7f4c19a2",
  "service_summary_ru": "Сервис доступа к глобальным AI-платформам с неоновым знаком db.",
  "plan": [
    {
      "slug": "brand-signal",
      "idea_ru": "Фирменный сигнал сервиса",
      "prompt_en": "A compact intertwined lowercase d and b mark emitting one strong upward signal pulse, centered as one readable emblem",
      "uses_ref": true
    },
    {
      "slug": "connection-success",
      "idea_ru": "Подключение успешно",
      "prompt_en": "A sturdy network plug locking into a circular portal with one large confirmation check integrated into the silhouette",
      "uses_ref": false
    }
  ]
}
```

Гарантии ответа:

- `plan.length === count`;
- порядок отражает разнообразие набора, не приоритет;
- slugs нормализованы и уникальны;
- `prompt_en` не содержит style suffix;
- не менее `count / 3` элементов имеют `uses_ref: true`;
- не более `2 × count / 3` имеют `uses_ref: true`.

### Ошибки

Единая форма новых ошибок:

```json
{
  "error": "Нужно добавить 2–3 изображения",
  "code": "invalid_refs",
  "retryable": false
}
```

Коды:

| HTTP | code | retryable |
|---|---|---|
| 400 | `invalid_request` | false |
| 400 | `invalid_refs` | false |
| 400 | `invalid_count` | false |
| 400 | `invalid_pack` | false |
| 404 | `ref_set_not_found` | false |
| 413 | `ref_too_large` | false |
| 502 | `planner_upstream_error` | true |
| 502 | `planner_invalid_json` | true |
| 503 | `missing_cliproxy_key` | false |
| 500 | `internal_error` | true |

Frontend продолжает принимать старые `{error: "..."}` от остальных endpoint.

## 5. API: генерация элемента плана

Расширить существующий endpoint:

```http
POST /api/generate
```

Запрос без референсов:

```json
{
  "pack": "dropweb",
  "id": "connection-success",
  "prompt": "A sturdy network plug locking into a circular portal...",
  "color": "#00DE52",
  "fit": 0.8,
  "model": "gpt-image-2",
  "uses_ref": false
}
```

Запрос с ref set:

```json
{
  "pack": "dropweb",
  "id": "brand-signal",
  "prompt": "A compact intertwined lowercase d and b mark...",
  "color": "#00DE52",
  "fit": 0.8,
  "model": "gpt-image-2",
  "ref_set": "refs-7f4c19a2",
  "uses_ref": true
}
```

Правила:

- `pack` обязателен для нового batch path;
- старый single flow без `pack` сохраняет fallback на `pack_default`;
- `uses_ref: true` требует валидный `ref_set`;
- `uses_ref: false` игнорирует `ref_set`;
- legacy `ref` с одним base64 изображением продолжает работать;
- при `ref_set` сервер передаёт все 2–3 изображения в `/images/edits`;
- response остаётся совместимым:

```json
{
  "id": "brand-signal",
  "base": {},
  "anchor": "",
  "groups": 7,
  "warn": null
}
```

## 6. Multi-reference в `gen_icon.py`

Сигнатура:

```python
generate_edit(ref_png_or_paths, prompt, out_png, size="1024x1024", model=MODEL)
```

Поддерживаемый input:

- строка path — legacy single-ref;
- список из 2–3 path — multi-ref.

Для `gpt-image-2`:

- один reference сохраняет текущий multipart field `image`;
- несколько передаются как повторяющийся field `image[]`:

```python
files = [
    ("image[]", ("ref-01.png", file1, "image/png")),
    ("image[]", ("ref-02.png", file2, "image/png")),
]
```

Для chat-image моделей multi-ref не поддерживать:

```json
{
  "error": "Пак из нескольких референсов поддерживает только ChatGPT",
  "code": "model_no_multi_ref",
  "retryable": false
}
```

## 7. Хранение референсов

Путь:

```text
build/<pack>/refs/<ref_set>/
├── ref-01.png
├── ref-02.png
├── ref-03.png
└── manifest.json
```

Пример manifest:

```json
{
  "ref_set": "refs-7f4c19a2",
  "pack": "dropweb",
  "created_at": "2026-07-12T18:42:11Z",
  "files": [
    {
      "file": "ref-01.png",
      "original_name": "logo.png",
      "sha256": "..."
    }
  ]
}
```

Правила:

- `ref_set` создаётся через `secrets.token_hex(4)`;
- path нельзя принимать напрямую от клиента;
- сервер разрешает только `refs-[a-f0-9]{8}`;
- оригинальные изображения не перезаписывают друг друга;
- существующий legacy путь `build/<pack>/refs/<id>.png` оставить;
- ref sets считаются build cache и не попадают в `packs/<pack>`;
- при удалении пака `build/<pack>/refs` удаляется best-effort вместе с остальными build artifacts.

## 8. System prompt для vision planner

```text
You are the art director and concept planner for a Telegram sticker and custom-emoji studio.

You will receive:
1. exactly 2 or 3 user-provided reference images of one service, product, app, or brand;
2. an optional service name or theme;
3. a required sticker count: 6, 12, or 18.

Analyze the references as a shared visual identity. Identify only features that are visibly supported by the images: distinctive logo geometry, mascot shape, product objects, interface metaphors, recurring symbols, and the service's apparent purpose. Do not invent unsupported product features.

Create exactly N distinct sticker concepts, divided equally into these three groups:
A. recognizable brand or mascot concepts derived from the references;
B. service-relevant objects, actions, outcomes, or workflows;
C. universal reactions or emotions reinterpreted through the service's identity.

Concept quality rules:
- Every concept must communicate one clear idea at Telegram-icon size.
- Avoid generic filler such as a plain heart, star, rocket, light bulb, smiley, thumbs-up, gift, fire, or check mark unless it is materially transformed by a service-specific object or identity feature.
- Do not repeat the same object with only a different emotion.
- Prefer concrete visual actions and physical metaphors over abstract words such as innovation, speed, security, intelligence, connection, or success.
- Cover positive, negative, waiting, celebration, surprise, failure, and action states where appropriate.
- At least one third and at most two thirds of the concepts must have uses_ref=true.
- uses_ref=true means the image generator must inspect the references to preserve recognizable geometry, mascot identity, or a service-specific object.
- uses_ref=false means the concept can be generated from its text description without copying a reference shape.

Mask and vectorization constraints:
- One dominant subject.
- One bold, compact, instantly readable silhouette.
- Centered composition with generous outer negative space.
- Thick connected shapes and large internal gaps.
- No thin lines, tiny detached particles, intricate textures, complex scenes, realistic lighting, photographic composition, or multiple distant objects.
- No text, letters, numbers, captions, UI labels, or slogans inside the sticker.
- Do not request a screenshot or reproduce a reference photo literally.
- When using brand identity, translate visible reference geometry into a simplified icon-scale emblem, mascot pose, or object silhouette.
- Do not include colors, rendering style, background, vector, neon, flat, or other style instructions in prompt_en. A deterministic style suffix is appended later by the server.

Field rules:
- slug: lowercase ASCII, 2-32 characters, pattern ^[a-z0-9][a-z0-9_-]{0,31}$, unique.
- idea_ru: concise natural Russian, 2-8 words, suitable for display in a plan.
- prompt_en: English, maximum 45 words, subject and composition only.
- uses_ref: JSON boolean.

Return ONLY valid JSON. No markdown fences, commentary, notes, or trailing text.

Schema:
{
  "service_summary_ru": "one concise Russian sentence",
  "items": [
    {
      "slug": "unique-slug",
      "idea_ru": "Короткая идея",
      "prompt_en": "Concrete English subject and composition description",
      "uses_ref": true
    }
  ]
}
```

User content отправляется отдельным multimodal message:

```text
Theme: <theme or "Infer from references">
Required count: <6|12|18>
Reference images follow.
```

Параметры planner call:

```json
{
  "model": "gpt-5.6-terra",
  "reasoning_effort": "medium",
  "temperature": 0.5,
  "max_tokens": 4000
}
```

Сервер:

1. удаляет markdown fences, если модель нарушила инструкцию;
2. парсит JSON;
3. валидирует schema;
4. нормализует slugs;
5. устраняет конфликты с текущим паком;
6. при невалидном ответе возвращает `planner_invalid_json`;
7. не выполняет скрытый второй planner request в рамках одного нажатия.

---

# S3. Visual design language refresh

## 1. Основной принцип

Lumina сохраняется, но зелёный становится **сигналом действия и состояния**, а не рамкой каждого объекта.

Запрещено:

- зелёная рамка у каждой карточки;
- glow у каждого slider thumb и выбранного поля;
- одинаковый вес primary, secondary и destructive actions;
- emoji-префиксы в названиях кнопок;
- больше одной заполненной зелёной CTA в активной правой вкладке.

## 2. Токены

Сохранить текущие шрифты и основные Lumina colors.

```css
:root {
  --void: #030305;
  --surface-1: #060608;
  --surface-2: #0A0A0D;
  --surface-3: #0F0F12;
  --surface-raised: #141418;

  --accent: #15803D;
  --accent-2: #22C55E;
  --accent-bright: #00DE52;
  --accent-deep: #006625;

  --text: #E2E2E2;
  --text-strong: #F4F6F4;
  --text-dim: #9AA0AA;
  --text-faint: #666C75;

  --line: rgba(255, 255, 255, 0.08);
  --line-strong: rgba(255, 255, 255, 0.14);
  --line-accent: rgba(0, 222, 82, 0.46);

  --warning: #F59E0B;
  --error: #EF4444;
  --info: #38BDF8;
}
```

## 3. Spacing

Только эта шкала:

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 24px;
--space-6: 32px;
```

Правила:

- внутренний padding большой рабочей зоны: `16px`;
- padding section card: `16px`;
- расстояние между секциями: `16px`;
- расстояние label → control: `8px`;
- расстояние между связанными controls: `8px`;
- между заголовком и содержимым секции: `12px`.

## 4. Радиусы

```css
--radius-control: 10px;
--radius-card: 14px;
--radius-panel: 18px;
--radius-preview: 20px;
```

Не использовать текущий `26px` у каждой карточки. Большой радиус остаётся только у preview и внешней рабочей панели.

## 5. Типографика

Использовать только существующие Onest и JetBrains Mono.

| Элемент | Стиль |
|---|---|
| название активной вкладки/экрана | Onest 18/24, 700 |
| заголовок секции | Onest 13/18, 700 |
| tab label / button | Onest 13/18, 600 |
| основной текст | Onest 13/20, 400 |
| label | Onest 11/16, 600 |
| metadata/status | Onest 11/16, 500 |
| slug/value/timer | JetBrains Mono 11/16, 600 |

- Section headings — sentence case, не all-caps.
- Uppercase оставить только для коротких product labels: `STUDIO`, `ПРЕВЬЮ`, `СТИКЕРЫ`.
- Tracking uppercase label: `0.08em`.
- Slugs и числовые значения используют `font-variant-numeric: tabular-nums`.

## 6. Поверхности

### Большая зона

```css
background: var(--surface-1);
border-right: 1px solid var(--line);
```

### Section card

```css
background: var(--surface-2);
border: 1px solid var(--line);
border-radius: var(--radius-card);
box-shadow: inset 0 1px rgba(255,255,255,.025);
```

### Raised/active card

```css
background: var(--surface-raised);
border-color: var(--line-strong);
```

Не использовать зелёную border у обычных карточек.

Ambient aura оставить, но:

- opacity `0.28`;
- blur `72px`;
- без анимации дыхания;
- зелёный orb только в верхней правой четверти;
- голубой orb снизить до opacity `0.05`.

## 7. Кнопки

Высота:

- normal: `40px`;
- compact: `34px`;
- primary wizard CTA: `44px`.

### Primary

```css
background: #00DE52;
color: #031108;
border: 1px solid #00DE52;
box-shadow: 0 8px 22px rgba(0, 153, 56, .20);
```

Hover:

```css
background: #19E968;
transform: translateY(-1px);
box-shadow: 0 10px 26px rgba(0, 153, 56, .28);
```

### Secondary

```css
background: rgba(255,255,255,.025);
color: var(--text);
border: 1px solid var(--line-strong);
box-shadow: none;
```

### Tertiary

Текстовая кнопка без карточки и glow.

### Danger

```css
color: #FF7474;
border-color: rgba(239,68,68,.28);
background: transparent;
```

Emoji-иконки в кнопках заменить на простые inline SVG `16×16`, `stroke-width:1.75`, `currentColor`. Новую icon library не добавлять.

## 8. Поля

```css
min-height: 40px;
background: var(--surface-1);
border: 1px solid var(--line-strong);
border-radius: 10px;
padding: 9px 11px;
```

Focus:

```css
border-color: var(--accent-bright);
box-shadow: 0 0 0 3px rgba(0,222,82,.14);
outline: none;
```

Ошибка:

```css
border-color: var(--error);
box-shadow: 0 0 0 3px rgba(239,68,68,.12);
```

## 9. Tabs

```css
.tabbar {
  height: 48px;
  padding: 4px;
  background: var(--surface-1);
  border-bottom: 1px solid var(--line);
}

.tab {
  color: var(--text-dim);
  border-bottom: 2px solid transparent;
}

.tab[aria-selected="true"] {
  color: var(--text-strong);
  border-bottom-color: var(--accent-bright);
}
```

Не использовать четыре отдельные pill-кнопки с зелёными рамками.

## 10. Batch status

Цвет и текст:

- queued: `#9AA0AA`, `В очереди`;
- running: `#38BDF8`, `Генерируется`;
- done: `#00DE52`, `Готово`;
- failed: `#EF4444`, `Ошибка`;
- skipped: `#666C75`, `Пропущено`;
- saved: `#22C55E`, `Сохранено`.

Progress bar:

```css
height: 6px;
background: rgba(255,255,255,.08);
border-radius: 999px;
```

Fill:

```css
background: linear-gradient(90deg, #15803D, #00DE52);
```

Running cards получают только левую status line `3px`; никакого полного glow.

Skeleton:

- background `surface-3`;
- shimmer только opacity/transform;
- reduced-motion отключает shimmer.

## 11. Interaction timing

- hover/focus: `160ms`;
- panels/accordion: `220ms`;
- easing: `cubic-bezier(.2,.8,.2,1)`;
- press: `translateY(1px)`;
- никакой постоянной декоративной анимации, кроме Lottie preview и progress/skeleton текущей операции.

---

# S4. Implementation slicing

Общий лимит: **один рабочий день**, без перехода на framework и без изменения animation engine.

## A. Backend

### A1. Новый `tools/pack_plan.py`

Реализовать:

- fixed model `gpt-5.6-terra`;
- multimodal `/chat/completions`;
- system prompt из S2;
- загрузку 2–3 reference images;
- очистку fenced JSON;
- schema validation;
- slug normalization;
- проверку количества и `uses_ref`;
- понятные typed exceptions без новой зависимости.

**Acceptance criteria:**

1. Два PNG + `count=6` возвращают ровно 6 валидных items.
2. Три изображения + `count=12` возвращают ровно 12 items.
3. Slugs соответствуют regex, уникальны и не конфликтуют с текущим паком.
4. Каждый item содержит непустые `idea_ru`, `prompt_en`, boolean `uses_ref`.
5. Ответ с markdown fences успешно очищается.
6. Garbage JSON возвращает `planner_invalid_json`, а не traceback клиенту.
7. Prompt не добавляет style suffix в `prompt_en`.
8. Модель не выбирается из frontend.

### A2. `tools/studio_server.py`: `/api/pack/plan`

Добавить:

- route;
- validation refs/count/pack;
- сохранение ref set;
- повторный plan по `ref_set`;
- error shape из S2;
- limit `10 MB` на изображение после base64 decode;
- нормализацию через Pillow в PNG;
- manifest с SHA-256.

**Acceptance criteria:**

1. `refs.length < 2` и `> 3` дают HTTP 400.
2. Невалидное изображение даёт HTTP 400.
3. Существующий pack обязателен.
4. Файлы оказываются в `build/<pack>/refs/<ref_set>/`.
5. Повторный request с `ref_set` не требует base64.
6. Path traversal через `pack` или `ref_set` невозможен.
7. Existing endpoints продолжают работать.

### A3. `tools/gen_icon.py`: multi-reference edit

Расширить `generate_edit`.

**Acceptance criteria:**

1. Строковый path работает как раньше.
2. Список из двух PNG отправляется через повторяющийся `image[]`.
3. Список из трёх PNG работает.
4. Файловые handles закрываются после каждого retry.
5. Internal retry policy остаётся максимум три попытки.
6. Multi-ref с Gemini завершается понятной validation error до network request.

### A4. `tools/studio_server.py`: расширить `/api/generate`

Добавить `pack`, `ref_set`, `uses_ref`.

**Acceptance criteria:**

1. `uses_ref=false` вызывает `/images/generations`.
2. `uses_ref=true` с ref set вызывает `/images/edits` с 2–3 файлами.
3. Style suffix добавляется ровно один раз.
4. Маска, fit, vectorization и complexity guard остаются прежними.
5. Результат записывает mask в `build/<pack>/masks`, а не всегда в default pack.
6. Legacy single `ref` продолжает работать.
7. Ответ остаётся совместимым с текущим `absorb()`.

### A5. Безопасность последовательного сохранения

Backend locking в рамках однодневного scope не добавлять. Frontend обязан выполнять bulk `/api/save` последовательно.

**Acceptance criteria:**

- сохранение десяти результатов даёт десять записей в `pack.json` и `bases.json`;
- ни одна запись не теряется.

---

## B. Frontend: `studio/index.html`

### B1. Перестроить shell

- fixed top pack bar;
- left library;
- center preview;
- right tabbed panel;
- independent scroll;
- responsive layouts из S1.

**Acceptance criteria:**

1. При `1512×806` все три зоны видны без прокрутки всей страницы.
2. Создание одного стикера доступно без вертикального скролла до другой секции.
3. Preview остаётся видимым при прокрутке длинных animation layers.
4. Pack controls всегда видимы.
5. На `1100px` нет горизонтального page scroll.

### B2. Перенести существующие controls

Перенести controls по таблице S1 без изменения ids и бизнес-логики, где это возможно.

**Acceptance criteria:**

- каждый id из таблицы присутствует ровно один раз;
- `studio.js` не изменяется;
- одиночная генерация, reference, upload, regen, refit, save работают;
- все animation controls продолжают обновлять Lottie;
- export one/all работает.

### B3. Реализовать tabs

- semantic tabs;
- state не сбрасывается;
- выбранная вкладка хранится в `sessionStorage` как `dw_studio_tab`;
- default: `create`.

**Acceptance criteria:**

- mouse и keyboard navigation работают;
- после reload восстанавливается последняя вкладка;
- hidden panel не участвует в tab order.

### B4. Реализовать wizard «Пак из референсов»

JS state:

```js
batch = {
  pack,
  refSet,
  theme,
  count,
  plan: [],
  items: new Map(),
  running: 0,
  paused: false
};
```

**Acceptance criteria:**

1. Dropzone принимает drag/drop и file picker.
2. Нельзя прикрепить меньше 2 или больше 3 файлов.
3. Plan response отображается редактируемыми rows.
4. Slug validation происходит до старта.
5. Regenerate plan переиспользует `ref_set`.
6. Start создаёт queue из текущих plan rows.
7. Никогда не выполняется больше двух `/api/generate`.
8. Ошибка одного элемента не останавливает очередь.
9. Retry и retry-all работают.
10. Stop не запускает новые requests, но принимает ответы уже активных.

### B5. Интегрировать batch results в grid

Расширить client state:

```js
let draftMeta = {};
let draftStatus = {};
```

**Acceptance criteria:**

1. Готовый item появляется в основной сетке без reload.
2. Его можно открыть и анимировать.
3. Save selected использует metadata конкретного item.
4. Delete draft не вызывает `/api/emoji/delete`.
5. Delete saved вызывает `/api/emoji/delete`.
6. Фильтры grid корректно разделяют drafts/saved.
7. При закрытии/reload с незаписанными drafts или активной очередью срабатывает `beforeunload` warning.

### B6. Bulk save

**Acceptance criteria:**

1. Сохраняются только `done` и ещё не сохранённые items.
2. POST requests идут строго один за другим.
3. Ошибка одного save не блокирует следующие.
4. Карточки получают состояние `saved` или `save failed`.
5. Итоговый текст показывает точные количества.

### B7. Visual cleanup

Применить токены и правила S3.

**Acceptance criteria:**

1. Только одна filled green CTA в активной правой вкладке.
2. Обычные cards используют neutral border.
3. Green glow не используется у обычных controls/cards.
4. Кнопки не содержат emoji-декора.
5. Focus-visible виден у каждого interactive control.
6. Статусы queue имеют текст, а не только цвет.
7. Reduced motion отключает shimmer и декоративные transitions.
8. UI проверен минимум на `1512×806`, `1100×800`, `768×1024`.

## Явно вне scope

- серверная база заданий;
- WebSocket, SSE или polling job endpoint;
- восстановление активной очереди после reload;
- background generation после закрытия вкладки;
- изменение `studio.js`;
- новые animation presets;
- автоматический выбор concurrency;
- concurrency 3+;
- генерация видео или animated source images;
- Telegram upload/publish;
- облачное хранение refs;
- authentication или multi-user locking;
- undo/redo;
- ручное добавление новых строк в AI plan;
- поиск и теги в библиотеке;
- переход на React/Vue/Svelte;
- новые npm/pip зависимости;
- полноценная мобильная переработка;
- изменение Lumina palette или шрифтов.

---

# S5. Risks & guards

| Риск | Guard |
|---|---|
| Vision planner возвращает prose, fenced JSON или неполную структуру | очистить fences, валидировать весь schema и fail closed с `planner_invalid_json`; не запускать генерацию частичного плана |
| `gpt-image-2` игнорирует часть референсов или буквально копирует screenshot | использовать `uses_ref` только для identity-dependent items и явно требовать simplified emblem/object silhouette, а не literal photo reproduction |
| Два параллельных запроса вместе с внутренними retries перегружают proxy | жёстко зафиксировать concurrency 2; 429/5xx обрабатываются backend retry, после исчерпания — только ручной retry |
| Длинный browser fetch обрывается после 2–5 минут | не ставить frontend timeout, показывать elapsed timer, сохранять остальные элементы очереди и давать per-item Retry |
| Фотореалистичные референсы дают шумную маску и слишком много path groups | style suffix остаётся обязательным; threshold и escalating potrace guard не меняются; карточка показывает warning по groups и предлагает retry с упрощённым prompt |

**Effort:** Medium, один плотный рабочий день при сохранении vanilla JS и текущего pipeline.  
**Confidence:** High: структура опирается на фактические controls в [`studio/index.html`](/Users/mac/Documents/projects/dropweb-channel/studio/index.html), текущий threaded API в [`tools/studio_server.py`](/Users/mac/Documents/projects/dropweb-channel/tools/studio_server.py) и уже проверенные vision/multi-reference возможности proxy.

