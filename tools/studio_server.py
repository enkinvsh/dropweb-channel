"""Zero-dependency (stdlib-only) local studio server for the sticker editor.

Serves the static studio at studio/ and a small JSON API that drives the
gen->mask->svg->base pipeline. Reuses the proven tools modules:
gen_icon, build_emoji (_fit_mask + the gen-png transform), vectorize,
and svg2base. Everything that writes runs with CWD=ROOT because
vectorize.make_clean_svg uses relative build/ paths.

Run:
    .venv/bin/python3 -m tools.studio_server --pack dropweb --port 8765
"""
import argparse
import base64
import binascii
import copy
import datetime
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import parse_qs, urlparse

from PIL import Image

from . import build_emoji, svg2base, vectorize
from . import gen_icon, gen_prompt, pack_plan

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ref_set id: секрет из secrets.token_hex(4) -> строго 8 hex. Клиент НЕ передаёт
# путь — только этот id, отсюда жёсткая валидация против path traversal.
REF_SET_RE = re.compile(r"^refs-[a-f0-9]{8}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ALLOWED_COUNTS = (6, 12, 18)
MAX_REF_BYTES = 10 * 1024 * 1024  # 10 MB на изображение после base64 decode


class BadRequest(Exception):
    """Ошибка валидации входных данных -> HTTP 400 с сообщением."""


def _need_eid(body):
    """id эмодзи обязателен и не пустой (иначе PIL падает на пустом имени файла)."""
    eid = (body.get("id") or "").strip()
    if not eid:
        raise BadRequest("введи id (slug) — поле пустое")
    return eid

# --- провайдеры генерации (кураторский список, порядок = приоритет) ---------
# ChatGPT (gpt-image-2) первым = дефолт по решению проекта. Nano Banana 2
# (gemini image) — рабочий резерв на прокси (chat/completions) для стилевого
# разнообразия.
GEN_MODELS = [
    {"id": "gpt-image-2", "label": "ChatGPT"},
    {"id": "gemini-3.1-flash-image", "label": "Nano Banana 2 · резервный"},
]

# --- flat-icon style steering + complexity guard ---------------------------
GROUP_CAP = 80
# Поля spec, которые _h_save переносит в pack.json emoji-запись. Включает
# метаданные пакетного черновика (idea_ru/uses_ref/ref_set) из draftMeta.
SAVE_SPEC_KEYS = ("source", "prompt", "color", "tgs", "anchor", "label", "anim",
                  "idea_ru", "uses_ref", "ref_set")
STYLE_SUFFIX = ("flat minimal vector icon, one bold connected silhouette, hard-edged solid fills, "
                "neon green subject on pure #000000 background, extremely high contrast, "
                "centered composition, no shadows, no glow, no gradients, no texture, "
                "no transparency, no soft edges, no tiny details, no thin lines, "
                "no background objects, no text")


def _steer(prompt):
    return (prompt or "").strip() + ". " + STYLE_SUFFIX


def _count_groups(base):
    """Count shape-groups (a `gr` whose `it` contains an `sh`) across all layers."""
    def _walk(shapes):
        n = 0
        for sh in shapes or []:
            if sh.get("ty") == "gr":
                items = sh.get("it", []) or []
                if any(x.get("ty") == "sh" for x in items):
                    n += 1
                n += _walk([x for x in items if x.get("ty") == "gr"])
        return n

    total = 0
    for layer in base.get("layers", []) or []:
        total += _walk(layer.get("shapes", []))
    return total


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}

# The mask transform used by build_emoji._gen_cached (gen-png -> mask).
_GEN_POINT = lambda v: 0 if v < 35 else min(255, int((v - 35) * 1.7))


def _mask_from_gen_png(path):
    """Open a generated PNG and apply the canonical gen->mask transform."""
    return Image.open(path).convert("L").point(_GEN_POINT)


def _pipeline_from_mask(raw_mask, eid, pack, fit, color):
    """raw_mask(L) -> _fit_mask -> save -> vectorize -> svg2base -> (base, groups).

    Applies a complexity guard: if the vectorized base exceeds GROUP_CAP
    shape-groups, it re-vectorizes the saved mask png with escalating
    turdsize values until it fits (or keeps the fewest-groups result).
    Must be called with CWD=ROOT (vectorize writes relative build/ paths).
    """
    m = build_emoji._fit_mask(raw_mask, fit if fit else 0.80)
    masks_dir = os.path.join(ROOT, "build", pack, "masks")
    os.makedirs(masks_dir, exist_ok=True)
    mask_png = os.path.join(masks_dir, "%s.png" % eid)
    m.save(mask_png, "PNG")  # явный формат: пустой/точечный eid не роняет PIL
    svg = vectorize.make_clean_svg(mask_png, eid, color=color or "#00DE52")
    base = svg2base.svg_to_base(svg)
    groups = _count_groups(base)

    # SIZE GUARD: too detailed -> re-vectorize with escalating turdsize.
    if groups > GROUP_CAP:
        best_base, best_groups = base, groups
        for turd in (24, 64, 160, 400):
            svg = vectorize.make_clean_svg(
                mask_png, eid, color=color or "#00DE52", turd=turd)
            cand = svg2base.svg_to_base(svg)
            cand_groups = _count_groups(cand)
            if cand_groups < best_groups:
                best_base, best_groups = cand, cand_groups
            if cand_groups <= GROUP_CAP:
                best_base, best_groups = cand, cand_groups
                break
        base, groups = best_base, best_groups

    return base, groups


def _atomic_write_json(path, obj):
    """Write JSON atomically (temp file in same dir + os.replace)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _valid_ref_set(rs):
    return isinstance(rs, str) and bool(REF_SET_RE.match(rs))


def _valid_pack_slug(name):
    return isinstance(name, str) and bool(SLUG_RE.match(name))


def _to_png_bytes(img):
    """PIL-изображение -> нормализованные PNG-байты (режим совместим с PNG)."""
    if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        img = img.convert("RGBA")
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _decode_ref_entry(entry):
    """Один ref из тела запроса -> (original_name, png_bytes). Бросает PlanError."""
    data = entry.get("data_b64") if isinstance(entry, dict) else None
    if not isinstance(data, str) or not data:
        raise PlanError("Битое изображение референса", "invalid_refs", 400)
    if "," in data[:64] and "base64" in data[:64]:
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=False)
    except (binascii.Error, ValueError):
        raise PlanError("Битое изображение референса", "invalid_refs", 400)
    if len(raw) > MAX_REF_BYTES:
        raise PlanError("Изображение больше 10 МБ", "ref_too_large", 413)
    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception:
        raise PlanError("Битое изображение референса", "invalid_refs", 400)
    name = entry.get("name") if isinstance(entry.get("name"), str) else None
    return (name or "ref.png"), _to_png_bytes(img)


def _ref_set_dir(root, pack, ref_set):
    return os.path.join(root, "build", pack, "refs", ref_set)


def _store_ref_set(root, pack, decoded):
    """decoded: [(original_name, png_bytes)] -> ref_set id + запись на диск.

    Файлы ref-01.png, ref-02.png, ... в порядке получения + manifest c sha256."""
    ref_set = "refs-" + secrets.token_hex(4)
    rs_dir = _ref_set_dir(root, pack, ref_set)
    os.makedirs(rs_dir, exist_ok=True)
    files_meta = []
    for i, (orig_name, png_bytes) in enumerate(decoded, start=1):
        fn = "ref-%02d.png" % i
        with open(os.path.join(rs_dir, fn), "wb") as f:
            f.write(png_bytes)
        files_meta.append({
            "file": fn,
            "original_name": orig_name,
            "sha256": hashlib.sha256(png_bytes).hexdigest(),
        })
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _atomic_write_json(os.path.join(rs_dir, "manifest.json"), {
        "ref_set": ref_set,
        "pack": pack,
        "created_at": created,
        "files": files_meta,
    })
    return ref_set


def _ref_set_files(root, pack, ref_set):
    """Пути к сохранённым референсам набора в порядке ref-01, ref-02, ...

    Читает manifest; фолбэк — отсортированный glob ref-NN.png. [] если нет."""
    rs_dir = _ref_set_dir(root, pack, ref_set)
    manifest = os.path.join(rs_dir, "manifest.json")
    if os.path.isfile(manifest):
        try:
            with open(manifest) as f:
                m = json.load(f)
            paths = [os.path.join(rs_dir, x["file"]) for x in (m.get("files") or [])
                     if isinstance(x, dict) and x.get("file")]
            paths = [p for p in paths if os.path.isfile(p)]
            if paths:
                return paths
        except Exception:
            pass
    if os.path.isdir(rs_dir):
        fns = sorted(fn for fn in os.listdir(rs_dir)
                     if re.match(r"^ref-\d+\.png$", fn))
        return [os.path.join(rs_dir, fn) for fn in fns]
    return []


class PlanError(Exception):
    """Ошибка нового endpoint'а с полями error/code/retryable (см. S2 таблицу)."""

    def __init__(self, message, code, http_status, retryable=False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


# --- векторный ресайз стикера (масклесс-фолбэк для /api/refit) ---------------
# База Lottie: слой ty:4 (ks) -> outer gr (tr) -> inner gr (tr) -> sh (ks.k.v).
# Вершины `v` лежат в СЫРОМ SVG-пространстве; на канву 512×512 их переносит
# аффинный tr родительских групп (у dropweb — ненулевой s/p у outer gr).
# Ресайз запекаем В ВЕРШИНЫ (никакие tr не трогаем -> makeAnimX/el_* целы):
# масштаб фактором вокруг rc = T^-1(256,256), где T — цепочка tr от слоя к sh.
FIT_MIN, FIT_MAX = 0.30, 0.98


class VectorResizeUnsupported(Exception):
    """База не раскладывается в статичный аффин (анимация/скос/вырождение)."""


def _clamp_fit(x) -> float:
    return max(FIT_MIN, min(FIT_MAX, float(x)))


def _tr_static(prop, default):
    """Статичное значение Lottie-свойства (a==0). Анимация -> Unsupported."""
    if not isinstance(prop, dict):
        return default
    if prop.get("a") not in (0, None):
        raise VectorResizeUnsupported("анимированный transform")
    k = prop.get("k")
    return default if k is None else k


def _affine_from_tr(tr):
    """Lottie tr -> (a,b,c,d,e,f): x'=a·x+c·y+e, y'=b·x+d·y+f.

    out = p + Rot(r)·Scale(s/100)·(v - anchor). Скос (sk≠0) -> Unsupported."""
    if tr is None:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    sk = _tr_static(tr.get("sk"), 0)
    if isinstance(sk, (int, float)) and abs(sk) > 1e-9:
        raise VectorResizeUnsupported("скос не поддерживается")
    anc = _tr_static(tr.get("a"), [0.0, 0.0])
    pos = _tr_static(tr.get("p"), [0.0, 0.0])
    scl = _tr_static(tr.get("s"), [100.0, 100.0])
    rot = _tr_static(tr.get("r"), 0.0)
    if isinstance(rot, list):
        rot = rot[0] if rot else 0.0
    th = math.radians(rot)
    sx, sy = scl[0] / 100.0, scl[1] / 100.0
    cos, sin = math.cos(th), math.sin(th)
    a, b, c, d = cos * sx, sin * sx, -sin * sy, cos * sy
    e = pos[0] - (a * anc[0] + c * anc[1])
    f = pos[1] - (b * anc[0] + d * anc[1])
    return (a, b, c, d, e, f)


def _affine_compose(o, i):
    """o∘i — сначала i, затем o."""
    a1, b1, c1, d1, e1, f1 = o
    a2, b2, c2, d2, e2, f2 = i
    return (
        a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1,
    )


def _affine_apply(t, x, y):
    a, b, c, d, e, f = t
    return (a * x + c * y + e, b * x + d * y + f)


def _affine_inverse(t):
    a, b, c, d, e, f = t
    det = a * d - b * c
    if abs(det) < 1e-12:
        raise VectorResizeUnsupported("вырожденный transform")
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(ia * e + ic * f), -(ib * e + id_ * f))


def _collect_sh(base):
    """(sh, T) для каждого пути: T переводит sh.ks.k.v -> канву."""
    pairs = []
    for layer in (base.get("layers") or []):
        if not isinstance(layer, dict) or layer.get("ty") != 4:
            continue
        t = _affine_from_tr(layer.get("ks"))
        _collect_items(layer.get("shapes") or [], t, pairs)
    return pairs


def _collect_items(items, t, pairs):
    for it in items or []:
        if not isinstance(it, dict):
            continue
        ty = it.get("ty")
        if ty == "sh":
            ks = it.get("ks") or {}
            if ks.get("a") not in (0, None):
                raise VectorResizeUnsupported("анимированный путь")
            pairs.append((it, t))
        elif ty == "gr":
            sub = it.get("it") or []
            gtr = next((x for x in sub
                        if isinstance(x, dict) and x.get("ty") == "tr"), None)
            child = _affine_compose(t, _affine_from_tr(gtr))
            _collect_items(
                [x for x in sub
                 if not (isinstance(x, dict) and x.get("ty") == "tr")],
                child, pairs)


def _canvas_bbox(pairs):
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for sh, t in pairs:
        for pt in (((sh.get("ks") or {}).get("k") or {}).get("v") or []):
            if not (isinstance(pt, list) and len(pt) >= 2):
                continue
            x, y = _affine_apply(t, pt[0], pt[1])
            minx, miny = min(minx, x), min(miny, y)
            maxx, maxy = max(maxx, x), max(maxy, y)
    if minx == float("inf"):
        return None
    return (minx, miny, maxx, maxy)


def _occupancy(pairs) -> float:
    bb = _canvas_bbox(pairs)
    if not bb:
        raise VectorResizeUnsupported("нет геометрии")
    return max(bb[2] - bb[0], bb[3] - bb[1]) / 512.0


def _occupancy_of_base(base) -> float:
    return _occupancy(_collect_sh(base))


def _scale_pairs(pairs, factor):
    """Масштаб вершин вокруг rc = T^-1(256,256); касательные i/o × factor."""
    for sh, t in pairs:
        rcx, rcy = _affine_apply(_affine_inverse(t), 256.0, 256.0)
        k = (sh.get("ks") or {}).get("k") or {}
        v, i, o = k.get("v") or [], k.get("i") or [], k.get("o") or []
        for idx in range(len(v)):
            if isinstance(v[idx], list) and len(v[idx]) >= 2:
                v[idx] = [(v[idx][0] - rcx) * factor + rcx,
                          (v[idx][1] - rcy) * factor + rcy]
            if idx < len(i) and isinstance(i[idx], list) and len(i[idx]) >= 2:
                i[idx] = [i[idx][0] * factor, i[idx][1] * factor]
            if idx < len(o) and isinstance(o[idx], list) and len(o[idx]) >= 2:
                o[idx] = [o[idx][0] * factor, o[idx][1] * factor]


def _resize_base_vector(base, target_fit):
    """Deep-copy базы с занятостью кадра target_fit. Возвращает (base, current)."""
    b = copy.deepcopy(base)
    pairs = _collect_sh(b)
    current = _occupancy(pairs)
    if current <= 1e-9:
        raise VectorResizeUnsupported("вырожденная занятость")
    _scale_pairs(pairs, target_fit / current)
    return b, current


def _refit_target(fit, delta, current):
    """Целевая занятость кадра. fit XOR delta; оба -> BadRequest."""
    if fit is not None and delta is not None:
        raise BadRequest("передай либо fit, либо delta")
    if delta is not None:
        return _clamp_fit(current + float(delta))
    if fit is not None:
        return _clamp_fit(float(fit))
    return None


def _working_base(root, body, pack, eid):
    """Текущая база стикера: из тела запроса, иначе из packs/<pack>/bases.json."""
    b = body.get("base")
    if isinstance(b, dict) and isinstance(b.get("layers"), list) and b["layers"]:
        return b
    bases_path = os.path.join(root, "packs", pack, "bases.json")
    if os.path.isfile(bases_path):
        try:
            with open(bases_path) as f:
                stored = (json.load(f).get("bases") or {}).get(eid)
            if isinstance(stored, dict) and stored.get("layers"):
                return stored
        except Exception:
            pass
    return None


def make_handler(pack_default, root):
    studio_dir = os.path.join(root, "studio")

    class Handler(BaseHTTPRequestHandler):
        server_version = "StudioServer/1.0"

        # ---- low-level helpers ------------------------------------------
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _send_json(self, obj, status=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _send_err(self, message, code, status, retryable=False):
            self._send_json(
                {"error": message, "code": code, "retryable": retryable}, status)

        def _send_bytes(self, data, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def log_message(self, format, *args):  # quieter logs
            pass

        # ---- static serving --------------------------------------------
        def _serve_static(self, url_path):
            rel = url_path.lstrip("/")
            if rel == "" or rel == "/":
                rel = "index.html"
            target = os.path.normpath(os.path.join(studio_dir, rel))
            # path traversal guard
            if not target.startswith(os.path.abspath(studio_dir) + os.sep) \
                    and target != os.path.abspath(studio_dir):
                self._send_json({"error": "forbidden"}, 403)
                return
            if not os.path.isfile(target):
                self._send_json({"error": "not found"}, 404)
                return
            ext = os.path.splitext(target)[1].lower()
            ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
            with open(target, "rb") as f:
                self._send_bytes(f.read(), ctype)

        # ---- API: GET ---------------------------------------------------
        def _api_pack(self, qs):
            name = (qs.get("name") or [pack_default])[0]
            bases_path = os.path.join(root, "packs", name, "bases.json")
            if not os.path.isfile(bases_path):
                self._send_json({"error": "no bases.json for pack %s" % name}, 404)
                return
            with open(bases_path) as f:
                data = json.load(f)
            specs = []
            pack_path = os.path.join(root, "packs", name, "pack.json")
            if os.path.isfile(pack_path):
                with open(pack_path) as f:
                    specs = json.load(f).get("emoji", [])
            self._send_json({
                "order": data.get("order", []),
                "anchors": data.get("anchors", {}),
                "defmap": data.get("defmap", {}),
                "bases": data.get("bases", {}),
                "specs": specs,
            })

        def _api_packs(self):
            packs_dir = os.path.join(root, "packs")
            names = []
            if os.path.isdir(packs_dir):
                for entry in os.listdir(packs_dir):
                    if os.path.isfile(os.path.join(packs_dir, entry, "pack.json")):
                        names.append(entry)
            names.sort()
            if pack_default in names:
                names.remove(pack_default)
                names.insert(0, pack_default)
            self._send_json({"packs": names, "default": pack_default})

        def _api_genconfig(self):
            """Кураторский список провайдеров генерации: ChatGPT + Nano Banana 2."""
            key = os.environ.get("CLIPROXY_KEY")
            self._send_json({
                "default": GEN_MODELS[0]["id"],
                "base": gen_icon.BASE,
                "key": bool(key),
                "models": GEN_MODELS,
            })

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/api/packs":
                    self._api_packs()
                    return
                if path == "/api/genconfig":
                    self._api_genconfig()
                    return
                if path == "/api/pack":
                    self._api_pack(parse_qs(parsed.query))
                    return
                if path == "/" or not path.startswith("/api/"):
                    self._serve_static(path)
                    return
                self._send_json({"error": "unknown route"}, 404)
            except Exception as e:
                traceback.print_exc()
                self._send_json({"error": str(e)}, 500)

        # ---- API: OPTIONS preflight ------------------------------------
        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        # ---- API: POST --------------------------------------------------
        def _h_generate(self, body):
            if not os.environ.get("CLIPROXY_KEY"):
                self._send_json({"error": "no CLIPROXY_KEY"}, 503)
                return
            eid = _need_eid(body)
            prompt = body["prompt"]
            color = body.get("color")
            fit = body.get("fit")
            model = body.get("model") or gen_icon.MODEL
            uses_ref = bool(body.get("uses_ref"))
            ref_set = body.get("ref_set")

            pk = body.get("pack") or pack_default
            if body.get("pack") and (not _valid_pack_slug(pk) or not os.path.isfile(
                    os.path.join(root, "packs", pk, "pack.json"))):
                self._send_err("Пак не найден", "invalid_request", 400)
                return

            ref_arg = None
            if uses_ref:
                if not _valid_ref_set(ref_set):
                    self._send_err("Нужен валидный набор референсов",
                                   "invalid_request", 400)
                    return
                paths = _ref_set_files(root, pk, ref_set)
                if not paths:
                    self._send_err("Набор референсов не найден",
                                   "invalid_request", 400)
                    return
                if len(paths) > 1 and gen_icon._is_chat_image_model(model):
                    self._send_err(
                        "Пак из нескольких референсов поддерживает только ChatGPT",
                        "model_no_multi_ref", 400)
                    return
                ref_arg = paths if len(paths) > 1 else paths[0]
            else:
                # legacy single reference (одно base64-изображение) остаётся рабочим
                ref = body.get("ref")
                if ref:
                    raw_ref = ref
                    if "," in raw_ref[:64] and "base64" in raw_ref[:64]:
                        raw_ref = raw_ref.split(",", 1)[1]
                    try:
                        ref_bytes = base64.b64decode(raw_ref)
                        ref_img = Image.open(BytesIO(ref_bytes)).convert("RGBA")
                    except Exception:
                        self._send_json({"error": "bad ref image"}, 400)
                        return
                    refs_dir = os.path.join(root, "build", pk, "refs")
                    os.makedirs(refs_dir, exist_ok=True)
                    ref_arg = os.path.join(refs_dir, "%s.png" % eid)
                    ref_img.save(ref_arg, "PNG")

            cwd = os.getcwd()
            os.chdir(root)
            try:
                gen_dir = os.path.join(root, "build", "gen")
                os.makedirs(gen_dir, exist_ok=True)
                tmp_png = os.path.join(gen_dir, "%s.png" % eid)
                if ref_arg is not None:
                    gen_icon.generate_edit(ref_arg, _steer(prompt), tmp_png, model=model)
                else:
                    gen_icon.generate(_steer(prompt), tmp_png, model=model)
                raw_mask = _mask_from_gen_png(tmp_png)
                base, groups = _pipeline_from_mask(raw_mask, eid, pk, fit, color)
            finally:
                os.chdir(cwd)
            warn = ("Слишком детально (%d частей) — упрости промт" % groups) if groups > GROUP_CAP else None
            self._send_json({"id": eid, "base": base, "anchor": "", "groups": groups, "warn": warn})

        def _h_regenerate(self, body):
            if not os.environ.get("CLIPROXY_KEY"):
                self._send_json({"error": "no CLIPROXY_KEY"}, 503)
                return
            eid = _need_eid(body)
            prompt = body["prompt"]
            color = body.get("color")
            fit = body.get("fit")
            model = body.get("model") or gen_icon.MODEL
            cwd = os.getcwd()
            os.chdir(root)
            try:
                gen_dir = os.path.join(root, "build", "gen")
                os.makedirs(gen_dir, exist_ok=True)
                last_png = os.path.join(gen_dir, "%s.png" % eid)
                src = last_png if os.path.exists(last_png) else None
                if body.get("prev_png") and os.path.exists(body["prev_png"]):
                    src = body["prev_png"]
                out_png = os.path.join(gen_dir, "%s.png" % eid)
                if src:
                    gen_icon.generate_edit(src, _steer(prompt), out_png, model=model)
                else:
                    gen_icon.generate(_steer(prompt), out_png, model=model)
                raw_mask = _mask_from_gen_png(out_png)
                base, groups = _pipeline_from_mask(raw_mask, eid, pack_default, fit, color)
            finally:
                os.chdir(cwd)
            warn = ("Слишком детально (%d частей) — упрости промт" % groups) if groups > GROUP_CAP else None
            self._send_json({"id": eid, "base": base, "anchor": "", "groups": groups, "warn": warn})

        def _h_prompt(self, body):
            """Агент-промтер: короткая идея -> грамотный промт (в поле prompt)."""
            if not os.environ.get("CLIPROXY_KEY"):
                self._send_json({"error": "no CLIPROXY_KEY"}, 503)
                return
            idea = (body.get("idea") or body.get("prompt") or "").strip()
            if not idea:
                self._send_json({"error": "пустая идея"}, 400)
                return
            text = gen_prompt.rewrite_prompt(idea)
            self._send_json({"prompt": text, "idea": idea,
                             "slug": gen_prompt.idea_slug(idea)})

        def _h_upload(self, body):
            eid = _need_eid(body)
            color = body.get("color")
            fit = body.get("fit")
            png_bytes = base64.b64decode(body["png_b64"])
            raw_mask = Image.open(BytesIO(png_bytes)).convert("L").point(_GEN_POINT)
            cwd = os.getcwd()
            os.chdir(root)
            try:
                base, groups = _pipeline_from_mask(raw_mask, eid, pack_default, fit, color)
            finally:
                os.chdir(cwd)
            warn = ("Слишком детально (%d частей) — упрости промт" % groups) if groups > GROUP_CAP else None
            self._send_json({"id": eid, "base": base, "anchor": "", "groups": groups, "warn": warn})

        def _h_refit(self, body):
            """Ресайз стикера.

            delta (относительный) ВСЕГДА идёт по вершинам рабочей базы: mask-fit
            и vector-bbox-occupancy — разные шкалы, поэтому mask-путь в delta не
            сходится (каждый шаг перемеряет ту же занятость -> застревает). Вектор
            точен и самосогласован с мерой занятости, шаги сходятся.
            Абсолютный fit -> mask-пайплайн если есть маска, иначе вектор."""
            eid = _need_eid(body)
            fit = body.get("fit")
            delta = body.get("delta")
            color = body.get("color")
            pack = body.get("pack", pack_default)

            if delta is not None:
                wbase = _working_base(root, body, pack, eid)
                if wbase is None:
                    self._send_json(
                        {"error": "нет базы для относительного ресайза — открой стикер"}, 404)
                    return
                try:
                    current = _occupancy_of_base(wbase)
                    target_fit = _refit_target(fit, delta, current)
                    assert target_fit is not None  # delta задан -> не None
                    base, _current = _resize_base_vector(wbase, target_fit)
                except VectorResizeUnsupported:
                    self._send_json(
                        {"error": "эта база не поддерживает векторный ресайз — перегенерируй"}, 400)
                    return
                groups = _count_groups(base)
                warn = ("Слишком детально (%d частей) — упрости промт" % groups) if groups > GROUP_CAP else None
                self._send_json({"id": eid, "base": base, "anchor": "",
                                 "groups": groups, "warn": warn,
                                 "fit": round(target_fit * 100)})
                return

            target_fit = _refit_target(fit, None, None)
            raw = None
            for cand in (
                os.path.join(root, "build", pack, "masks", "%s.png" % eid),
                os.path.join(root, "build", pack_default, "masks", "%s.png" % eid),
            ):
                if os.path.isfile(cand):
                    raw = Image.open(cand).convert("L")
                    break
            if raw is None:
                gen_png = os.path.join(root, "build", "gen", "%s.png" % eid)
                if os.path.isfile(gen_png):
                    raw = _mask_from_gen_png(gen_png)

            if raw is not None:
                cwd = os.getcwd()
                os.chdir(root)
                try:
                    base, groups = _pipeline_from_mask(raw, eid, pack, target_fit, color)
                finally:
                    os.chdir(cwd)
                if target_fit is not None:
                    fit_out = round(target_fit * 100)
                else:
                    try:
                        fit_out = round(_occupancy_of_base(base) * 100)
                    except VectorResizeUnsupported:
                        fit_out = 80
            else:
                wbase = _working_base(root, body, pack, eid)
                if wbase is None:
                    self._send_json(
                        {"error": "нет сохранённой маски и базы для %s — перегенери "
                                  "или загрузи PNG" % eid}, 404)
                    return
                if target_fit is None:
                    self._send_json(
                        {"error": "передай fit или delta для ресайза"}, 400)
                    return
                try:
                    base, _current = _resize_base_vector(wbase, target_fit)
                except VectorResizeUnsupported:
                    self._send_json(
                        {"error": "эта база не поддерживает векторный ресайз — перегенерируй"}, 400)
                    return
                groups = _count_groups(base)
                fit_out = round(target_fit * 100)

            warn = ("Слишком детально (%d частей) — упрости промт" % groups) if groups > GROUP_CAP else None
            self._send_json({"id": eid, "base": base, "anchor": "",
                             "groups": groups, "warn": warn, "fit": fit_out})

        def _h_save(self, body):
            pack = body.get("pack", pack_default)
            eid = body["id"]
            spec = body.get("spec", {}) or {}
            cfg = body.get("cfg", {}) or {}
            base = body["base"]

            # (1) update pack.json
            pack_path = os.path.join(root, "packs", pack, "pack.json")
            with open(pack_path) as f:
                pack_doc = json.load(f)
            emoji = pack_doc.setdefault("emoji", [])
            found = None
            for e in emoji:
                if e.get("id") == eid:
                    found = e
                    break
            merge = {}
            for k in SAVE_SPEC_KEYS:
                if k in spec:
                    merge[k] = spec[k]
            if cfg:
                merge["studio"] = cfg
            if found is not None:
                found.update(merge)
            else:
                new_e = {"id": eid, "anchor": spec.get("anchor", "")}
                new_e.update(merge)
                emoji.append(new_e)
            _atomic_write_json(pack_path, pack_doc)

            # (2) update bases.json
            bases_path = os.path.join(root, "packs", pack, "bases.json")
            with open(bases_path) as f:
                bdoc = json.load(f)
            bdoc.setdefault("bases", {})[eid] = base
            order = bdoc.setdefault("order", [])
            if eid not in order:
                order.append(eid)
            bdoc.setdefault("anchors", {})[eid] = spec.get("anchor", "")
            bdoc.setdefault("defmap", {})[eid] = cfg.get("kind", "beat")
            _atomic_write_json(bases_path, bdoc)

            self._send_json({"ok": True})

        def _h_pack_create(self, body):
            name = body.get("name", "")
            if not isinstance(name, str) or not re.match(
                    r"^[a-z0-9][a-z0-9_-]{0,31}$", name):
                self._send_json({"error": "bad name"}, 400)
                return
            pack_dir = os.path.join(root, "packs", name)
            pack_path = os.path.join(pack_dir, "pack.json")
            if os.path.exists(pack_path):
                self._send_json({"error": "pack exists"}, 409)
                return
            os.makedirs(pack_dir, exist_ok=True)
            _atomic_write_json(pack_path, {
                "meta": {"name": name, "default_color": "#00DE52"},
                "emoji": [],
            })
            _atomic_write_json(os.path.join(pack_dir, "bases.json"), {
                "order": [],
                "anchors": {},
                "defmap": {},
                "bases": {},
            })
            self._send_json({"ok": True, "name": name})

        @staticmethod
        def _valid_slug(name):
            return isinstance(name, str) and bool(
                re.match(r"^[a-z0-9][a-z0-9_-]{0,31}$", name))

        def _h_pack_delete(self, body):
            name = body.get("name", "")
            if not self._valid_slug(name):
                self._send_json({"error": "bad name"}, 400)
                return
            pack_dir = os.path.join(root, "packs", name)
            pack_path = os.path.join(pack_dir, "pack.json")
            if not os.path.isfile(pack_path):
                self._send_json({"error": "pack not found"}, 404)
                return
            if name == pack_default:
                self._send_json(
                    {"error": "нельзя удалить пак по умолчанию"}, 400)
                return
            shutil.rmtree(pack_dir)
            self._send_json({"ok": True})

        def _h_pack_rename(self, body):
            src = body.get("from")
            dst = body.get("to")
            if not self._valid_slug(src) or not self._valid_slug(dst):
                self._send_json({"error": "bad name"}, 400)
                return
            src_dir = os.path.join(root, "packs", src)
            dst_dir = os.path.join(root, "packs", dst)
            if not os.path.isfile(os.path.join(src_dir, "pack.json")):
                self._send_json({"error": "pack not found"}, 404)
                return
            if os.path.isfile(os.path.join(dst_dir, "pack.json")):
                self._send_json({"error": "pack exists"}, 409)
                return
            os.rename(src_dir, dst_dir)
            dst_pack_path = os.path.join(dst_dir, "pack.json")
            with open(dst_pack_path) as f:
                pack_doc = json.load(f)
            pack_doc.setdefault("meta", {})["name"] = dst
            _atomic_write_json(dst_pack_path, pack_doc)
            self._send_json({"ok": True, "name": dst})

        def _h_emoji_delete(self, body):
            pack = body["pack"]
            eid = body["id"]
            pack_path = os.path.join(root, "packs", pack, "pack.json")
            bases_path = os.path.join(root, "packs", pack, "bases.json")
            if not os.path.isfile(pack_path):
                self._send_json({"error": "pack not found"}, 404)
                return

            # (1) remove from pack.json emoji list
            with open(pack_path) as f:
                pack_doc = json.load(f)
            emoji = pack_doc.get("emoji", []) or []
            pack_doc["emoji"] = [e for e in emoji if e.get("id") != eid]
            _atomic_write_json(pack_path, pack_doc)

            # (2) remove from bases.json order + dicts
            if os.path.isfile(bases_path):
                with open(bases_path) as f:
                    bdoc = json.load(f)
                order = bdoc.get("order", []) or []
                bdoc["order"] = [x for x in order if x != eid]
                for key in ("bases", "anchors", "defmap"):
                    d = bdoc.get(key)
                    if isinstance(d, dict):
                        d.pop(eid, None)
                _atomic_write_json(bases_path, bdoc)

            # (3) best-effort cleanup of build artifacts (non-fatal)
            for art in (
                os.path.join(root, "build", pack, "tgs", "%s.tgs" % eid),
                os.path.join(root, "build", pack, "masks", "%s.png" % eid),
            ):
                try:
                    if os.path.isfile(art):
                        os.remove(art)
                except Exception:
                    pass

            self._send_json({"ok": True})

        def _h_pack_plan(self, body):
            pack = body.get("pack", pack_default)
            if not _valid_pack_slug(pack) or not os.path.isfile(
                    os.path.join(root, "packs", pack, "pack.json")):
                self._send_err("Пак не найден", "invalid_pack", 400)
                return
            count = body.get("count")
            if count not in ALLOWED_COUNTS:
                self._send_err("Количество должно быть 6, 12 или 18",
                               "invalid_count", 400)
                return
            has_refs = body.get("refs") is not None
            has_set = bool(body.get("ref_set"))
            if has_refs == has_set:
                self._send_err("Передай либо refs, либо ref_set",
                               "invalid_request", 400)
                return

            try:
                if has_refs:
                    refs = body.get("refs")
                    if not isinstance(refs, list) or not (2 <= len(refs) <= 3):
                        self._send_err("Нужно добавить 2–3 изображения",
                                       "invalid_refs", 400)
                        return
                    decoded = [_decode_ref_entry(r) for r in refs]
                    ref_set = _store_ref_set(root, pack, decoded)
                    ref_pngs = [png for _name, png in decoded]
                else:
                    ref_set = body.get("ref_set")
                    if not _valid_ref_set(ref_set):
                        self._send_err("Некорректный ref_set",
                                       "invalid_request", 400)
                        return
                    paths = _ref_set_files(root, pack, ref_set)
                    if not paths:
                        self._send_err("Набор референсов не найден",
                                       "ref_set_not_found", 404)
                        return
                    ref_pngs = []
                    for p in paths:
                        with open(p, "rb") as f:
                            ref_pngs.append(f.read())
            except PlanError as e:
                self._send_err(e.message, e.code, e.http_status, e.retryable)
                return

            theme = body.get("theme") or ""
            existing = self._pack_order(pack)
            try:
                result = pack_plan.make_plan(ref_pngs, theme, count,
                                             existing_slugs=existing)
            except pack_plan.PlannerError as e:
                self._send_err(e.message, e.code, e.http_status, e.retryable)
                return

            self._send_json({
                "ok": True,
                "model": pack_plan.MODEL,
                "ref_set": ref_set,
                "service_summary_ru": result["service_summary_ru"],
                "plan": result["plan"],
            })

        @staticmethod
        def _pack_order(pack):
            bases_path = os.path.join(root, "packs", pack, "bases.json")
            if os.path.isfile(bases_path):
                try:
                    with open(bases_path) as f:
                        return json.load(f).get("order", []) or []
                except Exception:
                    return []
            return []

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            routes = {
                "/api/generate": self._h_generate,
                "/api/prompt": self._h_prompt,
                "/api/regenerate": self._h_regenerate,
                "/api/upload": self._h_upload,
                "/api/refit": self._h_refit,
                "/api/save": self._h_save,
                "/api/pack/create": self._h_pack_create,
                "/api/pack/delete": self._h_pack_delete,
                "/api/pack/rename": self._h_pack_rename,
                "/api/pack/plan": self._h_pack_plan,
                "/api/emoji/delete": self._h_emoji_delete,
            }
            handler = routes.get(path)
            if handler is None:
                self._send_json({"error": "unknown route"}, 404)
                return
            try:
                body = self._read_json()
            except Exception as e:
                self._send_json({"error": "bad json: %s" % e}, 400)
                return
            try:
                handler(body)
            except BadRequest as e:
                self._send_json({"error": str(e)}, 400)
            except KeyError as e:
                self._send_json({"error": "missing field %s" % e}, 400)
            except gen_icon.MultiRefUnsupported as e:
                self._send_err(str(e), gen_icon.MultiRefUnsupported.code, 400)
            except gen_icon.UpstreamError as e:
                self._send_json({"error": str(e)}, 502)
            except Exception as e:
                traceback.print_exc()
                self._send_json({"error": str(e)}, 500)

    return Handler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pack", default="dropweb")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--root", default=ROOT)
    a = p.parse_args()
    root = os.path.abspath(a.root)
    handler = make_handler(a.pack, root)
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    print("Studio: http://localhost:%d  (pack=%s)" % (a.port, a.pack))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
