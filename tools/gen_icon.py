"""Генерация базовой иконки через cliproxyapi (OpenAI-совместимый прокси).

Два пути в зависимости от модели:
  * gpt-image-* (ChatGPT/OpenAI)  -> /images/generations и /images/edits
  * gemini *image* (Nano Banana)  -> /chat/completions с modalities=[image,text]
    (gemini-модели НЕ поддерживаются на /images/* эндпоинтах прокси)

Ключ/базу читаем из env (никогда не хардкодим):
  CLIPROXY_BASE  (по умолчанию http://localhost:8317/v1)
  CLIPROXY_KEY   (обязательно)
  DW_IMAGE_MODEL (по умолчанию gemini-3.1-flash-image = Nano Banana 2)
"""
import base64
import os
import time

import requests

BASE = os.environ.get("CLIPROXY_BASE", "http://localhost:8317/v1")
MODEL = os.environ.get("DW_IMAGE_MODEL", "gemini-3.1-flash-image")


class UpstreamError(RuntimeError):
    """Ошибка от cliproxyapi/апстрима с человекочитаемым сообщением."""

    def __init__(self, status, message):
        self.status = status
        super().__init__("cliproxyapi %s: %s" % (status, message))


def _key():
    key = os.environ.get("CLIPROXY_KEY")
    if not key:
        raise RuntimeError("задай env CLIPROXY_KEY (см. конфиг ~/.cli-proxy-api)")
    return key


def _raise_upstream(resp):
    """4xx/5xx -> UpstreamError с текстом из тела (а не голый 'HTTP 401')."""
    if resp.status_code < 400:
        return
    msg = ""
    try:
        j = resp.json()
        msg = (j.get("error") or {}).get("message") or j.get("detail") or ""
    except Exception:
        msg = (resp.text or "")[:200]
    raise UpstreamError(resp.status_code, msg or "ошибка провайдера")


def _is_chat_image_model(model):
    """gemini/nano-banana image-модели идут через chat/completions, не через /images/*."""
    m = (model or "").lower()
    return "image" in m and not m.startswith("gpt-image")


def _extract_image_url(msg):
    """Достать data-URL картинки из ответа chat/completions (images[] или content-parts)."""
    for img in (msg.get("images") or []):
        url = (img.get("image_url") or {}).get("url") if isinstance(img, dict) else None
        if url:
            return url
    content = msg.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url")
                if url:
                    return url
    return None


def _gen_via_chat(prompt, out_png, model, ref_png=None):
    """Генерация/правка изображения через chat/completions (Nano Banana / gemini)."""
    key = _key()
    content = [{"type": "text", "text": prompt}]
    if ref_png:
        with open(ref_png, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + b64}})
    resp = requests.post(
        "%s/chat/completions" % BASE,
        headers={"Authorization": "Bearer %s" % key,
                 "Content-Type": "application/json"},
        json={"model": model,
              "messages": [{"role": "user", "content": content}],
              "modalities": ["image", "text"]},
        timeout=300,
    )
    _raise_upstream(resp)
    msg = ((resp.json().get("choices") or [{}])[0] or {}).get("message", {}) or {}
    url = _extract_image_url(msg)
    if not url or "," not in url:
        raise RuntimeError("модель %s не вернула изображение "
                           "(проверь, что это image-модель)" % model)
    data = base64.b64decode(url.split(",", 1)[1])
    with open(out_png, "wb") as f:
        f.write(data)
    return out_png


def generate(prompt, out_png, size="1024x1024", model=MODEL):
    if _is_chat_image_model(model):
        return _gen_via_chat(prompt, out_png, model)
    key = _key()
    last = None
    for attempt in range(7):
        try:
            resp = requests.post(
                "%s/images/generations" % BASE,
                headers={"Authorization": "Bearer %s" % key},
                json={"model": model, "prompt": prompt, "size": size, "n": 1},
                timeout=240,
            )
            _raise_upstream(resp)
            item = resp.json()["data"][0]
            if item.get("b64_json"):
                data = base64.b64decode(item["b64_json"])
            else:
                data = requests.get(item["url"], timeout=120).content
            with open(out_png, "wb") as f:
                f.write(data)
            return out_png
        except UpstreamError as e:
            last = e
            if 400 <= (e.status or 0) < 500:
                raise  # клиентские ошибки (протух токен, нет модели) — не ретраим
            time.sleep(3 + attempt * 4)
        except Exception as e:
            last = e
            time.sleep(3 + attempt * 4)
    raise last


def generate_edit(base_png, prompt, out_png, size="1024x1024", model=MODEL):
    """Правка изображения (image-to-image) для КОНСИСТЕНТНЫХ состояний:
    следующий кадр сюжета получаем правкой базового, сохраняя геометрию."""
    if _is_chat_image_model(model):
        return _gen_via_chat(prompt, out_png, model, ref_png=base_png)
    key = _key()
    with open(base_png, "rb") as fh:
        files = {"image": ("base.png", fh, "image/png")}
        data = {"model": model, "prompt": prompt, "size": size, "n": "1"}
        resp = requests.post("%s/images/edits" % BASE,
                             headers={"Authorization": "Bearer %s" % key},
                             files=files, data=data, timeout=300)
    _raise_upstream(resp)
    item = resp.json()["data"][0]
    if item.get("b64_json"):
        out = base64.b64decode(item["b64_json"])
    else:
        out = requests.get(item["url"], timeout=120).content
    with open(out_png, "wb") as f:
        f.write(out)
    return out_png
