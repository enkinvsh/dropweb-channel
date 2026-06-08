# Автозаливка эмодзи в Telegram через @Stickers (Playwright)

Рабочий, проверенный метод заливки видео-эмодзи (.webm) в @Stickers через
Telegram Web K с браузерной автоматизацией Playwright.

## Подготовка
- Файлы: `build/emoji/*.webm` (100x100, VP9, <=3с, <=256КБ, чёрный скруглённый фон).
- Маппинг id->якорный эмодзи: `build/emoji/ORDER.txt`.
- Логин: пользователь логинится сам (QR на web.telegram.org/k/).

## Поток @Stickers
1. `/newemojipack`
2. Выбрать тип — кнопка **«Видеоэмодзи»** (это `.reply-markup-button`, НЕ подчёркнутые
   слова в тексте — те ведут на доку core.telegram.org и открывают «Open Link»).
3. Имя набора: `dropweb`
4. Далее цикл на каждое эмодзи: прислать .webm как ДОКУМЕНТ -> бот просит якорный
   эмодзи -> прислать эмодзи -> «Эмодзи добавлен. Количество: N».
5. После всех 33: `/publish` -> обложка (`/skip` или один эмодзи) -> короткое имя
   `dropweb` -> ссылка `t.me/addemoji/dropweb`.

## ВАЖНО: как слать файл (грабли)
НЕ кликать «скрепка -> Document» — это открывает OS-filechooser, который Playwright MCP
ставит в очередь; при цикле они каскадируются и блокируют все инструменты
(«Tool does not handle the modal state»). Чистить можно только отменой
`browser_file_upload {}` по одному.

ПРАВИЛЬНО — прямой `setInputFiles` на скрытый document-input (accept=null), без диалога:

```js
// надёжный цикл (browser_run_code_unsafe), чанками по ~5 (иначе таймаут запроса)
async (page) => {
  const base='/Users/mac/Documents/projects/dropweb-channel/build/emoji/';
  const items=[['db.webm','💚'], /* ... id->emoji ... */];
  const log=[];
  for (const [file,emo] of items) {
    const inp = page.locator('input[type=file]').first();   // accept=null = document input
    await inp.setInputFiles(base+file);                     // показывает попап "Send File"
    await page.waitForTimeout(2000);
    await page.keyboard.press('Enter');                     // отправить файл (документом, без сжатия)
    await page.waitForTimeout(2300);
    const ed = page.locator('div.input-message-input[contenteditable=true]').first();
    await ed.click();
    await page.keyboard.insertText(emo);                    // якорный эмодзи (insertText, не type)
    await page.waitForTimeout(250);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(2400);
    const msgs = await page.locator('.bubble').allInnerTexts();
    const lb = msgs[msgs.length-1]||'';
    const k = lb.indexOf('наборе:');
    log.push(file+':'+(k>=0 ? (lb.slice(k+8).match(/[0-9]+/)||['?'])[0] : '?'));
  }
  return JSON.stringify(log);
}
```

## Замечания
- Эмодзи слать через `insertText`, не `type` (надёжнее для unicode/ZWJ: 🏴‍☠️, 🧑‍💻).
- Регэксп в JSON-аргументах: без `\s`/`\d` (невалидный JSON-escape) — использовать `[0-9]`.
- Чанк по 5 файлов: один цикл ~35с, иначе MCP `Request timed out` (но код часто
  доезжает на сервере — проверять счётчик после таймаута).
- Проверка счётчика: последний бабл бота «Количество эмодзи в наборе: N».
