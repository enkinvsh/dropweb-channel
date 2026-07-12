"""Агент-промтер: короткая идея -> грамотный промт для gpt-image-2.

Дёргает chat-эндпоинт cliproxyapi (OpenAI-совместимый). Ключ/базу — из env,
никогда не хардкодим:
  CLIPROXY_BASE (по умолчанию http://localhost:8317/v1)
  CLIPROXY_KEY  (обязательно)
  DW_TEXT_MODEL (по умолчанию gpt-5.6-terra)

Агент описывает ТОЛЬКО сюжет/композицию иконки. Стиль (flat neon vector,
чёрный фон, неон-зелёный) дописывается детерминированно в studio_server._steer,
поэтому здесь стиль и цвета не упоминаем — иначе будет дублирование.

Self-test: `.venv/bin/python3 -m tools.gen_prompt "пингвин с ноутбуком"`.
"""
import os
import re
import sys

import requests

BASE = os.environ.get("CLIPROXY_BASE", "http://localhost:8317/v1")
TEXT_MODEL = os.environ.get("DW_TEXT_MODEL", "gpt-5.6-terra")

# Детерминированный транслит RU->latin для slug-а из идеи (без сети).
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def idea_slug(idea):
    """Идея (RU/EN) -> детерминированный latin slug для id иконки.

    Транслит кириллицы, lowercase, всё вне [a-z0-9_-] -> '-', схлопывание
    повторов '-', обрезка по краям, максимум 32 символа. Если результат
    пустой или не проходит валидацию -> 'icon'."""
    s = (idea or "").lower()
    out = []
    for ch in s:
        out.append(_TRANSLIT.get(ch, ch))
    s = "".join(out)
    s = re.sub(r"[^a-z0-9_-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    if len(s) > 32:
        s = s[:32].rstrip("-")
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,31}$", s):
        return "icon"
    return s

SYSTEM = (
    "You are a prompt engineer for a neon sticker studio. The user gives a short idea "
    "(1-4 words, Russian or English) for a Telegram custom-emoji icon. Turn it into ONE "
    "vivid English image prompt describing the SUBJECT and its composition for a FLAT, "
    "MINIMAL, SINGLE-SILHOUETTE vector icon.\n"
    "Rules:\n"
    "- Describe only WHAT it depicts and the pose/angle, concretely: one bold, instantly "
    "recognizable silhouette, centered, thick clean shapes, generous negative space.\n"
    "- It becomes a monochrome mask and is vectorized: keep it a single closed shape; avoid "
    "fine detail, thin lines, text, small gaps, gradients, textures, realism, 3D shading.\n"
    "- Do NOT mention colors or style words (flat/vector/neon/green/black background); those "
    "are appended automatically.\n"
    "- Output ONLY the prompt, no quotes, no preamble, max 35 words."
)


def rewrite_prompt(idea, model=None, timeout=45):
    """idea (любой язык) -> чистый англоязычный промт-описание сюжета иконки."""
    key = os.environ.get("CLIPROXY_KEY")
    if not key:
        raise RuntimeError("задай env CLIPROXY_KEY (см. конфиг ~/.cli-proxy-api)")
    idea = (idea or "").strip()
    if not idea:
        raise ValueError("пустая идея")
    resp = requests.post(
        "%s/chat/completions" % BASE,
        headers={"Authorization": "Bearer %s" % key,
                 "Content-Type": "application/json"},
        json={
            "model": model or TEXT_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": idea},
            ],
            "temperature": 0.8,
            "reasoning_effort": "low",
            "max_tokens": 400,
        },
        timeout=timeout,
    )
    if resp.status_code >= 400:
        emsg = ""
        try:
            emsg = (resp.json().get("error") or {}).get("message") or ""
        except Exception:
            emsg = (resp.text or "")[:200]
        raise RuntimeError("cliproxyapi %s: %s (модель %s — попробуй другую через "
                           "DW_TEXT_MODEL)" % (resp.status_code, emsg or "ошибка",
                                               model or TEXT_MODEL))
    text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
    text = text.strip().strip('"').strip("'").strip()
    return " ".join(text.split())


if __name__ == "__main__":
    idea = " ".join(sys.argv[1:]) or "пингвин с ноутбуком"
    print(rewrite_prompt(idea))
