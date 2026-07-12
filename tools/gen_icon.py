"""Генерация базовой иконки через cliproxyapi (OpenAI-совместимый прокси).

Два пути в зависимости от модели:
  * gpt-image-* (ChatGPT/OpenAI)  -> /images/generations и /images/edits
  * gemini *image* (Nano Banana)  -> /chat/completions с modalities=[image,text]
    (gemini-модели НЕ поддерживаются на /images/* эндпоинтах прокси)

Ключ/базу читаем из env (никогда не хардкодим):
  CLIPROXY_BASE  (по умолчанию http://localhost:8317/v1)
  CLIPROXY_KEY   (обязательно)
  DW_IMAGE_MODEL (по умолчанию gpt-image-2 = ChatGPT; gemini остаётся
                  поддержан как резервный через chat/completions)
"""
import base64
import os
import time
from io import BytesIO

import requests
from PIL import Image

BASE = os.environ.get("CLIPROXY_BASE", "http://localhost:8317/v1")
MODEL = os.environ.get("DW_IMAGE_MODEL", "gpt-image-2")


class UpstreamError(RuntimeError):
    """Ошибка от cliproxyapi/апстрима с человекочитаемым сообщением."""

    def __init__(self, status, message, retry_after=None):
        self.status = status
        self.retry_after = retry_after
        super().__init__("cliproxyapi %s: %s" % (status, message))


class MultiRefUnsupported(RuntimeError):
    """Multi-ref (2–3 референса) запрошен для chat-image модели (gemini/nano
    banana) — прокси поддерживает только один reference через chat/completions.
    Несёт code для карты ошибок сервера."""
    code = "model_no_multi_ref"


def _key():
    key = os.environ.get("CLIPROXY_KEY")
    if not key:
        raise RuntimeError("задай env CLIPROXY_KEY (см. конфиг ~/.cli-proxy-api)")
    return key


def _parse_retry_after(resp):
    """Retry-After (секунды) из заголовка ответа -> float или None."""
    raw = resp.headers.get("Retry-After") if getattr(resp, "headers", None) else None
    if not raw:
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


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
    raise UpstreamError(resp.status_code, msg or "ошибка провайдера",
                        retry_after=_parse_retry_after(resp))


def _save_png_on_black(data, out_png):
    """Декодированные байты изображения -> PNG на непрозрачном ЧЁРНОМ фоне.

    gpt-image-2 может вернуть прозрачный PNG. Даунстрим mask-порог (v<35->0)
    ждёт почти-чёрный фон, а PIL .convert("L") на RGBA теряет альфу и делает
    прозрачные зоны белыми. Поэтому композитим на #000000."""
    img = Image.open(BytesIO(data))
    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (0, 0, 0))
        bg.paste(rgba, mask=rgba.split()[-1])
        out = bg
    else:
        out = img.convert("RGB")
    out.save(out_png, "PNG")
    return out_png


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
    return _save_png_on_black(data, out_png)


_RETRYABLE_EXC = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)


def _image_bytes_from_response(resp, model):
    """Достать байты изображения из ответа /images/* с валидацией.

    Пустой data[] или элемент без b64_json/url -> понятная RuntimeError
    (а не голый KeyError)."""
    data = (resp.json() or {}).get("data") or []
    if not data:
        raise RuntimeError("модель %s вернула пустой ответ без изображения" % model)
    item = data[0] or {}
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        return requests.get(item["url"], timeout=120).content
    raise RuntimeError("модель %s вернула пустой ответ без изображения" % model)


def _retry_call(do_request):
    """Не более 3 попыток. Ретраим ТОЛЬКО таймауты/коннекты и UpstreamError
    со статусом 429 или >=500. Прочие 4xx — сразу наверх (протух токен, нет
    модели). Honor Retry-After: спим max(retry_after or 0, 3 + attempt*4)."""
    last = None
    for attempt in range(3):
        try:
            return do_request()
        except UpstreamError as e:
            last = e
            status = e.status or 0
            if status == 429 or status >= 500:
                if attempt == 2:
                    raise
                time.sleep(max(e.retry_after or 0, 3 + attempt * 4))
                continue
            raise  # прочие 4xx — не ретраим
        except _RETRYABLE_EXC as e:
            last = e
            if attempt == 2:
                raise
            time.sleep(3 + attempt * 4)
    raise last if last is not None else RuntimeError("retry loop exhausted")


def generate(prompt, out_png, size="1024x1024", model=MODEL):
    if _is_chat_image_model(model):
        return _gen_via_chat(prompt, out_png, model)
    key = _key()

    def _do():
        resp = requests.post(
            "%s/images/generations" % BASE,
            headers={"Authorization": "Bearer %s" % key},
            json={"model": model, "prompt": prompt, "size": size, "n": 1},
            timeout=240,
        )
        _raise_upstream(resp)
        return _save_png_on_black(_image_bytes_from_response(resp, model), out_png)

    return _retry_call(_do)


def generate_edit(ref_png_or_paths, prompt, out_png, size="1024x1024", model=MODEL):
    """Правка изображения (image-to-image) для КОНСИСТЕНТНЫХ состояний:
    следующий кадр сюжета получаем правкой базового, сохраняя геометрию.

    ref_png_or_paths:
      * строка path      -> одиночный референс (legacy);
      * список 2–3 path  -> multi-reference (только gpt-image-*).

    Для gpt-image-* один референс идёт полем `image`, несколько — повторяющимся
    полем `image[]`. Для chat-image моделей (gemini/nano banana) multi-ref не
    поддерживается — падаем понятной ошибкой ДО сетевого запроса.

    Ретрай (3 попытки) живёт внутри — сервер больше не оборачивает свой.
    Файловые handles открываются заново на каждой попытке и закрываются после."""
    paths = list(ref_png_or_paths) if isinstance(ref_png_or_paths, (list, tuple)) \
        else [ref_png_or_paths]
    if not paths:
        raise ValueError("нужен хотя бы один референс")
    is_multi = len(paths) > 1

    if _is_chat_image_model(model):
        if is_multi:
            raise MultiRefUnsupported(
                "Пак из нескольких референсов поддерживает только ChatGPT")
        return _gen_via_chat(prompt, out_png, model, ref_png=paths[0])
    key = _key()

    def _do():
        handles = [open(p, "rb") for p in paths]
        try:
            if is_multi:
                files = [("image[]",
                          (os.path.basename(p), fh, "image/png"))
                         for p, fh in zip(paths, handles)]
            else:
                files = {"image": ("base.png", handles[0], "image/png")}
            data = {"model": model, "prompt": prompt, "size": size, "n": "1"}
            resp = requests.post("%s/images/edits" % BASE,
                                 headers={"Authorization": "Bearer %s" % key},
                                 files=files, data=data, timeout=300)
        finally:
            for fh in handles:
                fh.close()
        _raise_upstream(resp)
        return _save_png_on_black(_image_bytes_from_response(resp, model), out_png)

    return _retry_call(_do)
