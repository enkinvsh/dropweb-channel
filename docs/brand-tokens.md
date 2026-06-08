# dropweb — токены бренда и источник истины по эмодзи

Вытащено из реальных проектов. Это рецепт, чтобы попасть в лук 1:1.

## Исходники (скопированы в этот репозиторий)

| Файл | Откуда | Роль |
|---|---|---|
| `assets/logo/dropweb-logo.svg` | `dropweb-remnasub/dropweb-logo.svg` | Вектор-мастер «db» — 12 прямоугольников, монохром `#FAFAFA` |
| `assets/logo/icon.png` | `dropweb-app/assets/images/icon.png` | Неоновый «db» (== Pictures/logo.png) |
| `assets/logo/icon_white.png` | `dropweb-app/assets/images/icon_white.png` | Белый вариант «db» |
| `assets/logo/header.png` | `dropweb-app/assets/images/header.png` | Хедер-арт |
| `assets/logo/logo-neon-original.png` | `~/Pictures/logo.png` | Оригинальный неоновый логотип |
| `assets/fonts/JetBrainsMono-Regular.ttf` | `dropweb-app/assets/fonts` | Моноширинный шрифт для ASCII |
| `assets/fonts/Unbounded-variable.ttf` | `dropweb-fonts` | Заголовочный шрифт (вес 900) |
| `assets/fonts/Onest-variable.ttf` | `dropweb-fonts` | Текстовый шрифт |
| `reference/dropweb_gen.reference.py` | `projects/dropweb_gen.py` | Референс рецепта глоу/сканлайнов |
| `reference/theme-edit.reference.html` | `dropweb-theme-edit/index.html` | Исходник палитры тем |

## Цвета (из `dropweb-app/lib/common/lumina.dart`)

- Фон `void`: `#030305` (НЕ чистый чёрный — лёгкий синий подтон)
- Поверхности: `#060608` `#0A0A0D` `#0F0F12` `#141417` `#1A1A1D`
- Неон основной (ядро): `#15803D`
- Неон вторичный (яркое свечение): `#00DE52`  <-- рекомендованный акцент эмодзи
- Акцент-циан: `#38BDF8`
- Панчёвый рекламный неон (баннер): `#39FF14` (альтернатива)

## Пресеты тем (6) — для эмодзи 🎨 с перебором цвета

| Пресет | Семейство hex |
|---|---|
| Падение (зелёный, дефолт) | `#00DE52` / `#2BFF7A` / `#15803D` |
| Иней (frost) | `#38BDF8` / `#60A5FA` |
| Аметист (amethyst) | `#A78BFA` / `#8B5CF6` / `#A855F7` |
| Багрянец (crimson) | `#EF4444` / `#F87171` / `#B91C1C` |
| Янтарь (amber) | `#F59E0B` / `#FBBF24` / `#B45309` |
| Стелс (stealth) | `#64748B` / `#94A3B8` / `#475569` |

Фильтры схемы (из `color.dart`): vibrant (насыщенность ×1.4), monochrome (0),
neutral (×0.3), expressive (сдвиг тона +30), fidelity (без изменений).

## Рецепт фосфорного глоу + CRT (из `dropweb_gen.reference.py`)

- Глоу: слоёный GaussianBlur — проход 1 радиус R, альфа ~165; проход 2 радиус R/4; затем заливка альфа 255.
- Сканлайны: горизонтальная линия каждые 4px, белая альфа ~6.
- Точки-сетка: неон альфа ~10 каждые 54px (опциональная текстура).
- Рамка: неон альфа ~28, 1px.

## Моушн-подпись (из `lumina.dart`)

- Кривая: `Cubic(0.2, 0.8, 0.2, 1.0)`
- Длительность: 400мс
- Тень-глоу: blurRadius 16, spread 2, intensity 0.4
- Blur sigma: 4 (обычный) / 8 (тяжёлый)

Переиспользуем это, чтобы набор «двигался» как само приложение.

## Бэкенд генерации — cliproxyapi

- Endpoint: `http://localhost:8317` (OpenAI-совместимый)
- Image-модель: **`gpt-image-2`** (выбрана). Альтернатива: `gemini-3.1-flash-image`.
- API-ключ: лежит в `~/.cli-proxy-api/cliproxyapi.conf.staged` (в репо НЕ хардкодим; читаем в env `CLIPROXY_KEY`).
- Image-эндпоинты (OpenAI-compat): `/v1/images/generations`, `/v1/images/edits` (с референсом).

## Спека кастом-эмодзи Telegram (анимированные)

- Видео `.webm`: кодек VP9, ровно 100×100, ≤3с, ≤30fps, ≤256КБ, без звука, зациклено.
- Вектор `.tgs`: Lottie, 100×100 (эмодзи), ≤64КБ, 60fps — отклонено (rlottie не тянет глоу).
- Заливка: бот @stickers → `/newemojipack`. Ссылка: `t.me/addemoji/<slug>`.
- Каждое эмодзи должно иметь ≥1 якорный базовый эмодзи для поиска.

## Набор эмодзи v2 (32) — словарь постов + платформы + реакции + хакер

Бренд/статус: `db` (подпись канала) · `[NEW]` релиз · `ON` подключено.
Фичи: brain (smart-ядро) · shield (TLS Fragment/DPI) · think (умный сервер) · monitor (сервера) · palette (тема) · helix (редактор тем) · signal (аварийный пул) · globe (лого провайдера).
Футер: doc (доки) · download (скачать) · penguin (Linux) · heart (донат) · star (github).

Анимация на эмодзи: общая база «дыхание» блума + фирменный акцент (db пульс+скан,
NEW мигание курсора, ON расходящееся кольцо, shield скан-свип + распад SNI, palette
перебор 6 цветов тем, monitor CRT-загрузка, signal заполнение баров, helix вращение спирали).
