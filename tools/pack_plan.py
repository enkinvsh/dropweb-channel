"""Vision-планировщик пакета «Пак из референсов».

По 2–3 референс-изображениям и (опциональной) теме составляет план из N
концептов стикеров: за каждым — slug, русская идея, английский промт-сюжет и
флаг uses_ref (нужно ли генератору смотреть на референсы).

Модель фиксирована — **gpt-5.6-terra** (мультимодальный vision через
/chat/completions прокси). Не выбирается из фронтенда. Ключ/базу читаем из env,
никогда не хардкодим:
  CLIPROXY_BASE (по умолчанию http://localhost:8317/v1)
  CLIPROXY_KEY  (обязательно)

Стиль (flat neon vector, чёрный фон и т.п.) в prompt_en НЕ добавляется —
детерминированный style suffix дописывает сервер при генерации.

Self-test офлайн: `.venv/bin/python3 -m unittest tools.test_pack_plan -v`.
"""
import base64
import json
import math
import os
import re

import requests

from . import gen_prompt

BASE = os.environ.get("CLIPROXY_BASE", "http://localhost:8317/v1")
# Фиксированная модель планировщика. НЕ читается из env и не выбирается клиентом.
MODEL = "gpt-5.6-terra"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


# --- typed exceptions (без новых зависимостей) ------------------------------
class PlannerError(RuntimeError):
    """База для ошибок планировщика. Несёт code/retryable/http_status."""
    code = "internal_error"
    retryable = True
    http_status = 500

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class MissingKeyError(PlannerError):
    code = "missing_cliproxy_key"
    retryable = False
    http_status = 503


class PlannerUpstreamError(PlannerError):
    code = "planner_upstream_error"
    retryable = True
    http_status = 502


class PlannerInvalidJSON(PlannerError):
    code = "planner_invalid_json"
    retryable = True
    http_status = 502


# --- system prompt (дословно из спека S2.8) ---------------------------------
SYSTEM = (
    "You are the art director and concept planner for a Telegram sticker and custom-emoji studio.\n"
    "\n"
    "You will receive:\n"
    "1. exactly 2 or 3 user-provided reference images of one service, product, app, or brand;\n"
    "2. an optional service name or theme;\n"
    "3. a required sticker count: 6, 12, or 18.\n"
    "\n"
    "Analyze the references as a shared visual identity. Identify only features that are visibly "
    "supported by the images: distinctive logo geometry, mascot shape, product objects, interface "
    "metaphors, recurring symbols, and the service's apparent purpose. Do not invent unsupported "
    "product features.\n"
    "\n"
    "Create exactly N distinct sticker concepts, divided equally into these three groups:\n"
    "A. recognizable brand or mascot concepts derived from the references;\n"
    "B. service-relevant objects, actions, outcomes, or workflows;\n"
    "C. universal reactions or emotions reinterpreted through the service's identity.\n"
    "\n"
    "Concept quality rules:\n"
    "- Every concept must communicate one clear idea at Telegram-icon size.\n"
    "- Avoid generic filler such as a plain heart, star, rocket, light bulb, smiley, thumbs-up, "
    "gift, fire, or check mark unless it is materially transformed by a service-specific object or "
    "identity feature.\n"
    "- Do not repeat the same object with only a different emotion.\n"
    "- Prefer concrete visual actions and physical metaphors over abstract words such as "
    "innovation, speed, security, intelligence, connection, or success.\n"
    "- Cover positive, negative, waiting, celebration, surprise, failure, and action states where "
    "appropriate.\n"
    "- At least one third and at most two thirds of the concepts must have uses_ref=true.\n"
    "- uses_ref=true means the image generator must inspect the references to preserve recognizable "
    "geometry, mascot identity, or a service-specific object.\n"
    "- uses_ref=false means the concept can be generated from its text description without copying a "
    "reference shape.\n"
    "\n"
    "Mask and vectorization constraints:\n"
    "- One dominant subject.\n"
    "- One bold, compact, instantly readable silhouette.\n"
    "- Centered composition with generous outer negative space.\n"
    "- Thick connected shapes and large internal gaps.\n"
    "- No thin lines, tiny detached particles, intricate textures, complex scenes, realistic "
    "lighting, photographic composition, or multiple distant objects.\n"
    "- No text, letters, numbers, captions, UI labels, or slogans inside the sticker.\n"
    "- Do not request a screenshot or reproduce a reference photo literally.\n"
    "- When using brand identity, translate visible reference geometry into a simplified icon-scale "
    "emblem, mascot pose, or object silhouette.\n"
    "- Do not include colors, rendering style, background, vector, neon, flat, or other style "
    "instructions in prompt_en. A deterministic style suffix is appended later by the server.\n"
    "\n"
    "Field rules:\n"
    "- slug: lowercase ASCII, 2-32 characters, pattern ^[a-z0-9][a-z0-9_-]{0,31}$, unique.\n"
    "- idea_ru: concise natural Russian, 2-8 words, suitable for display in a plan.\n"
    "- prompt_en: English, maximum 45 words, subject and composition only.\n"
    "- uses_ref: JSON boolean.\n"
    "\n"
    "Return ONLY valid JSON. No markdown fences, commentary, notes, or trailing text.\n"
    "\n"
    "Schema:\n"
    "{\n"
    '  "service_summary_ru": "one concise Russian sentence",\n'
    '  "items": [\n'
    "    {\n"
    '      "slug": "unique-slug",\n'
    '      "idea_ru": "Короткая идея",\n'
    '      "prompt_en": "Concrete English subject and composition description",\n'
    '      "uses_ref": true\n'
    "    }\n"
    "  ]\n"
    "}"
)


def _strip_fences(text):
    """Убрать markdown-огранку ```json ... ``` если модель нарушила инструкцию."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _parse_doc(text):
    """Текст ответа модели -> dict. Чистит fences, при мусоре -> planner_invalid_json."""
    cleaned = _strip_fences(text)
    try:
        doc = json.loads(cleaned)
    except Exception:
        # запасной путь: вырезать самый внешний {...}
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                doc = json.loads(cleaned[start:end + 1])
            except Exception:
                raise PlannerInvalidJSON("планировщик вернул невалидный JSON")
        else:
            raise PlannerInvalidJSON("планировщик вернул невалидный JSON")
    if not isinstance(doc, dict):
        raise PlannerInvalidJSON("планировщик вернул не-объект JSON")
    return doc


def _normalize_slug(raw, idea_ru):
    """slug модели -> валидный latin slug. При провале — из idea_ru, иначе 'icon'."""
    s = gen_prompt.idea_slug(raw if isinstance(raw, str) else "")
    if s == "icon":
        s = gen_prompt.idea_slug(idea_ru or "")
    return s


def _dedupe(slugs, existing):
    """Уникальность внутри плана + отсутствие конфликта с существующим ORDER.
    Конфликт -> суффикс -2, -3, ... (с усечением до 32 символов)."""
    used: set = set(existing or ())
    out = []
    for s in slugs:
        cand = s
        n = 2
        while cand in used:
            suffix = "-%d" % n
            base = s[:32 - len(suffix)].rstrip("-_") or "icon"
            cand = base + suffix
            n += 1
        used.add(cand)
        out.append(cand)
    return out


def _enforce_ratio(items, count):
    """Гарантия: ceil(count/3) <= (кол-во uses_ref=true) <= floor(2*count/3).

    Модель может нарушить — тогда ДЕТЕРМИНИРОВАННО переворачиваем флаги без
    повторного запроса к модели. Не хватает true — включаем самые ранние false
    (более «брендовые» по порядку); слишком много true — выключаем последние
    true (наименее бренд-зависимые в порядке разнообразия)."""
    min_true = math.ceil(count / 3)
    max_true = (2 * count) // 3
    true_idx = [i for i, it in enumerate(items) if it["uses_ref"]]
    n_true = len(true_idx)
    if n_true < min_true:
        need = min_true - n_true
        for i, it in enumerate(items):
            if need <= 0:
                break
            if not it["uses_ref"]:
                it["uses_ref"] = True
                need -= 1
    elif n_true > max_true:
        need = n_true - max_true
        for i in reversed(true_idx):
            if need <= 0:
                break
            items[i]["uses_ref"] = False
            need -= 1
    return items


def _validate_items(doc, count):
    """Проверить schema и вернуть список сырых валидных item'ов (ровно count)."""
    items = doc.get("items")
    summary = doc.get("service_summary_ru")
    if not isinstance(summary, str) or not summary.strip():
        raise PlannerInvalidJSON("нет service_summary_ru в ответе планировщика")
    if not isinstance(items, list) or not items:
        raise PlannerInvalidJSON("нет items в ответе планировщика")
    clean = []
    for raw in items:
        if not isinstance(raw, dict):
            raise PlannerInvalidJSON("item плана — не объект")
        idea_ru = (raw.get("idea_ru") or "").strip() if isinstance(raw.get("idea_ru"), str) else ""
        prompt_en = (raw.get("prompt_en") or "").strip() if isinstance(raw.get("prompt_en"), str) else ""
        uses_ref = raw.get("uses_ref")
        if not idea_ru or not prompt_en or not isinstance(uses_ref, bool):
            raise PlannerInvalidJSON("item плана без idea_ru/prompt_en/uses_ref")
        clean.append({
            "slug_raw": raw.get("slug", ""),
            "idea_ru": idea_ru,
            "prompt_en": prompt_en,
            "uses_ref": uses_ref,
        })
    if len(clean) < count:
        raise PlannerInvalidJSON(
            "план короче запрошенного: %d < %d" % (len(clean), count))
    return clean[:count]


def _postprocess(doc, count, existing_slugs):
    """doc модели -> финальный ответ с гарантиями (slugs, ratio, длина)."""
    raw_items = _validate_items(doc, count)
    slugs = _dedupe(
        [_normalize_slug(c["slug_raw"], c["idea_ru"]) for c in raw_items],
        existing_slugs,
    )
    plan = []
    for c, slug in zip(raw_items, slugs):
        plan.append({
            "slug": slug,
            "idea_ru": c["idea_ru"],
            "prompt_en": c["prompt_en"],
            "uses_ref": c["uses_ref"],
        })
    _enforce_ratio(plan, count)
    return {
        "service_summary_ru": doc["service_summary_ru"].strip(),
        "plan": plan,
    }


def make_plan(ref_pngs, theme, count, existing_slugs=()):
    """Составить план по референсам.

    ref_pngs: список PNG-байтов (2–3 штуки, в порядке ref-01, ref-02, ...);
    theme: строка темы/названия или пусто (тогда модель выводит из картинок);
    count: 6, 12 или 18 (длину плана гарантируем ровно count);
    existing_slugs: slug'и текущего пака (ORDER) для устранения конфликтов.

    Возвращает {"service_summary_ru": str, "plan": [{slug, idea_ru, prompt_en, uses_ref}]}.
    """
    key = os.environ.get("CLIPROXY_KEY")
    if not key:
        raise MissingKeyError("задай env CLIPROXY_KEY (см. конфиг ~/.cli-proxy-api)")

    theme_line = theme.strip() if isinstance(theme, str) and theme.strip() else "Infer from references"
    user_text = ("Theme: %s\nRequired count: %d\nReference images follow."
                 % (theme_line, count))
    content: list = [{"type": "text", "text": user_text}]
    for png in ref_pngs:
        b64 = base64.b64encode(png).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + b64}})

    try:
        resp = requests.post(
            "%s/chat/completions" % BASE,
            headers={"Authorization": "Bearer %s" % key,
                     "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": content},
                ],
                "reasoning_effort": "medium",
                "temperature": 0.5,
                "max_tokens": 4000,
            },
            timeout=300,
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        raise PlannerUpstreamError("планировщик недоступен: %s" % e)

    if resp.status_code >= 400:
        emsg = ""
        try:
            emsg = (resp.json().get("error") or {}).get("message") or ""
        except Exception:
            emsg = (resp.text or "")[:200]
        raise PlannerUpstreamError(
            "cliproxyapi %s: %s" % (resp.status_code, emsg or "ошибка планировщика"))

    try:
        text = ((resp.json().get("choices") or [{}])[0] or {}).get("message", {}).get("content")
    except Exception:
        raise PlannerInvalidJSON("не удалось прочитать ответ планировщика")
    if not text or not isinstance(text, str):
        raise PlannerInvalidJSON("пустой ответ планировщика")

    doc = _parse_doc(text)
    return _postprocess(doc, count, existing_slugs)
