"""Агент-промтер: короткая идея -> грамотный промт для gpt-image-2.

Дёргает chat-эндпоинт cliproxyapi (OpenAI-совместимый). Ключ/базу — из env,
никогда не хардкодим:
  CLIPROXY_BASE (по умолчанию http://localhost:8317/v1)
  CLIPROXY_KEY  (обязательно)
  DW_TEXT_MODEL (по умолчанию gpt-5.5)

Агент описывает ТОЛЬКО сюжет/композицию иконки. Стиль (flat neon vector,
чёрный фон, неон-зелёный) дописывается детерминированно в studio_server._steer,
поэтому здесь стиль и цвета не упоминаем — иначе будет дублирование.

Self-test: `.venv/bin/python3 -m tools.gen_prompt "пингвин с ноутбуком"`.
"""
import os
import sys

import requests

BASE = os.environ.get("CLIPROXY_BASE", "http://localhost:8317/v1")
TEXT_MODEL = os.environ.get("DW_TEXT_MODEL", "gpt-5.5")

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
            "max_tokens": 200,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
    text = text.strip().strip('"').strip("'").strip()
    return " ".join(text.split())


if __name__ == "__main__":
    idea = " ".join(sys.argv[1:]) or "пингвин с ноутбуком"
    print(rewrite_prompt(idea))
