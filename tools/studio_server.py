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
import json
import os
import re
import shutil
import tempfile
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import parse_qs, urlparse

from PIL import Image

from . import build_emoji, svg2base, vectorize
from . import gen_icon, gen_prompt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BadRequest(Exception):
    """Ошибка валидации входных данных -> HTTP 400 с сообщением."""


def _need_eid(body):
    """id эмодзи обязателен и не пустой (иначе PIL падает на пустом имени файла)."""
    eid = (body.get("id") or "").strip()
    if not eid:
        raise BadRequest("введи id (slug) — поле пустое")
    return eid

# --- провайдеры генерации (кураторский список, порядок = приоритет) ---------
# Nano Banana 2 (gemini image) идёт первым — единственный, что реально живой
# на прокси через chat/completions. ChatGPT (gpt-image-2) вторым выбором.
GEN_MODELS = [
    {"id": "gemini-3.1-flash-image", "label": "Nano Banana 2"},
    {"id": "gpt-image-2", "label": "ChatGPT"},
]

# --- flat-icon style steering + complexity guard ---------------------------
GROUP_CAP = 80
STYLE_SUFFIX = ("flat minimal vector icon, single bold solid silhouette, thick clean shapes, "
                "centered composition, pure black background, high contrast, neon green, "
                "no texture, no gradient, no fine detail, no thin lines, no realism, no shadow")


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
            """Кураторский список провайдеров генерации: Nano Banana 2 + ChatGPT."""
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
            ref = body.get("ref")
            # Decode optional reference image up-front so a bad ref -> 400.
            ref_png = None
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
                refs_dir = os.path.join(root, "build", pack_default, "refs")
                os.makedirs(refs_dir, exist_ok=True)
                ref_png = os.path.join(refs_dir, "%s.png" % eid)
                ref_img.save(ref_png, "PNG")
            cwd = os.getcwd()
            os.chdir(root)
            try:
                gen_dir = os.path.join(root, "build", "gen")
                os.makedirs(gen_dir, exist_ok=True)
                tmp_png = os.path.join(gen_dir, "%s.png" % eid)
                if ref_png:
                    # generate_edit has no internal retry -> wrap a small one.
                    last = None
                    for attempt in range(3):
                        try:
                            gen_icon.generate_edit(ref_png, _steer(prompt), tmp_png, model=model)
                            last = None
                            break
                        except Exception as e:
                            last = e
                            time.sleep(2 + attempt * 3)
                    if last is not None:
                        raise last
                else:
                    gen_icon.generate(_steer(prompt), tmp_png, model=model)
                raw_mask = _mask_from_gen_png(tmp_png)
                base, groups = _pipeline_from_mask(raw_mask, eid, pack_default, fit, color)
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
            self._send_json({"prompt": text, "idea": idea})

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
            """Переподгонка масштаба (fit) из сохранённой маски — без генерации."""
            eid = _need_eid(body)
            fit = body.get("fit")
            color = body.get("color")
            pack = body.get("pack", pack_default)
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
            if raw is None:
                self._send_json(
                    {"error": "нет сохранённой маски для %s — перегенери или загрузи PNG" % eid}, 404)
                return
            cwd = os.getcwd()
            os.chdir(root)
            try:
                base, groups = _pipeline_from_mask(raw, eid, pack_default, fit, color)
            finally:
                os.chdir(cwd)
            warn = ("Слишком детально (%d частей) — упрости промт" % groups) if groups > GROUP_CAP else None
            self._send_json({"id": eid, "base": base, "anchor": "", "groups": groups, "warn": warn})

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
            for k in ("source", "prompt", "color", "tgs", "anchor", "label", "anim"):
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
