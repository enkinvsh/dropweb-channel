"""Генерация базовой иконки через gpt-image-2 (cliproxyapi, OpenAI-совместимый).

Ключ/базу читаем из env (никогда не хардкодим):
  CLIPROXY_BASE (по умолчанию http://localhost:8317/v1)
  CLIPROXY_KEY  (обязательно)
"""
import base64
import os
import time

import requests

BASE = os.environ.get("CLIPROXY_BASE", "http://localhost:8317/v1")
MODEL = os.environ.get("DW_IMAGE_MODEL", "gpt-image-2")


def generate(prompt, out_png, size="1024x1024", model=MODEL):
    key = os.environ.get("CLIPROXY_KEY")
    if not key:
        raise RuntimeError("задай env CLIPROXY_KEY (см. конфиг ~/.cli-proxy-api)")
    last = None
    for attempt in range(7):
        try:
            resp = requests.post(
                f"{BASE}/images/generations",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "prompt": prompt, "size": size, "n": 1},
                timeout=240,
            )
            resp.raise_for_status()
            item = resp.json()["data"][0]
            if item.get("b64_json"):
                data = base64.b64decode(item["b64_json"])
            else:
                data = requests.get(item["url"], timeout=120).content
            with open(out_png, "wb") as f:
                f.write(data)
            return out_png
        except Exception as e:
            last = e
            time.sleep(3 + attempt * 4)
    raise last


def generate_edit(base_png, prompt, out_png, size="1024x1024", model=MODEL):
    """Редактирование изображения (image-to-image) для КОНСИСТЕНТНЫХ состояний:
    следующий кадр сюжета получаем правкой базового, сохраняя геометрию."""
    key = os.environ.get("CLIPROXY_KEY")
    if not key:
        raise RuntimeError("set CLIPROXY_KEY env")
    with open(base_png, "rb") as fh:
        files = {"image": ("base.png", fh, "image/png")}
        data = {"model": model, "prompt": prompt, "size": size, "n": "1"}
        resp = requests.post(f"{BASE}/images/edits",
                             headers={"Authorization": f"Bearer {key}"},
                             files=files, data=data, timeout=300)
    resp.raise_for_status()
    item = resp.json()["data"][0]
    if item.get("b64_json"):
        out = base64.b64decode(item["b64_json"])
    else:
        out = requests.get(item["url"], timeout=120).content
    with open(out_png, "wb") as f:
        f.write(out)
    return out_png
