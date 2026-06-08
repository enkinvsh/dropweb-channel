"""Сборка одного (или всех) эмодзи в анимированный Telegram .tgs (вектор/Lottie).

Векторный аналог tools/build_emoji.py (который делает webm): маска -> hi-res PNG ->
многопутёвый SVG (potrace+picosvg) -> поэлементная анимация -> .tgs (<=64КБ).

Использование:
  .venv/bin/python3 -m tools.build_tgs --pack dropweb --id signal   # пилот
  .venv/bin/python3 -m tools.build_tgs --pack dropweb               # весь набор
Требует: potrace + picosvg + lottie в .venv (всё установлено).
"""
import argparse
import os

from . import build_emoji as B
from . import vectorize
from . import tgs_anim


def mask_for_spec(spec):
    """Повторяет диспетчеризацию source из build_emoji.build_one (без модификации)."""
    src = spec["source"]
    if src == "png":
        m = B.mask_from_png(os.path.join(B.ROOT, spec["asset"]))
    elif src == "text":
        m = B.mask_from_text(spec["glyph"])
    elif src == "shape":
        m = B.mask_from_shape(spec["shape"])
    elif src == "gen":
        m = B.mask_from_gen(spec)
    elif src in ("gen_states", "text_states"):
        # для tgs берём ПОСЛЕДНЕЕ/самое полное состояние как одну маску
        st = spec.get("states")
        if src == "text_states":
            m = B.mask_from_text(st[-1])
        else:
            m = B.mask_from_gen({**spec, "prompt": spec.get("prompt", "")})
    else:
        raise ValueError("неизвестный source %s" % src)
    return B._fit_mask(m, spec.get("fit", 0.80))


def build_one_tgs(spec, color, pack="dropweb", n=60, bg=None):
    # picosvg/potrace в vectorize пишут в относительный build/ -> работаем из ROOT
    cwd = os.getcwd()
    os.chdir(B.ROOT)
    try:
        mask = mask_for_spec(spec)
        masks_dir = os.path.join(B.ROOT, "build", pack, "masks")
        os.makedirs(masks_dir, exist_ok=True)
        mask_png = os.path.join(masks_dir, spec["id"] + ".png")
        mask.convert("L").save(mask_png)

        render_color = spec.get("color", color)
        svg = vectorize.make_clean_svg(mask_png, spec["id"], color=render_color)

        tg = spec.get("tgs")
        if isinstance(tg, str):
            preset, params, nn = tg, {}, n
        elif isinstance(tg, dict):
            preset = tg.get("preset", "pulse_offset")
            params = tg.get("params", {})
            nn = tg.get("n", n)
        else:
            preset, params, nn = "pulse_offset", {}, n

        tgs_dir = os.path.join(B.ROOT, "build", pack, "tgs")
        os.makedirs(tgs_dir, exist_ok=True)
        out = os.path.join(tgs_dir, spec["id"] + ".tgs")
        bg_cfg = bg if bg is not None else spec.get("bg")
        tgs_anim.build_elements_tgs(svg, out, preset, params, nn, bg=bg_cfg)
        size_kb = os.path.getsize(out) / 1024.0
        return out, size_kb
    finally:
        os.chdir(cwd)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pack", default="dropweb", help="имя пака в packs/<name>/pack.json")
    p.add_argument("--id", help="id одного эмодзи (пилот)")
    p.add_argument("--color", default=None, help="переопределить неон hex")
    p.add_argument("--n", type=int, default=60, help="число кадров")
    p.add_argument("--bg", nargs="?", const="default", default=None,
                   help="статичный фон-плитка: --bg (дефолт) или --bg rx:fill, "
                        "напр. --bg 90:#030305; без флага -> только из spec")
    a = p.parse_args()
    data = B.load_set(a.pack)
    color = a.color or data["meta"]["default_color"]

    # --bg given on CLI overrides per-spec bg; absent -> per-spec only.
    if a.bg is None:
        cli_bg = None
    elif a.bg == "default":
        cli_bg = True
    else:
        rx_s, _, fill_s = a.bg.partition(":")
        cli_bg = {
            "rx": float(rx_s) if rx_s else tgs_anim.BG_DEFAULT["rx"],
            "fill": fill_s or tgs_anim.BG_DEFAULT["fill"],
        }

    specs = [s for s in data["emoji"] if not a.id or s["id"] == a.id]
    if not specs:
        raise SystemExit("нет эмодзи с id=%s" % a.id)
    for s in specs:
        path, kb = build_one_tgs(s, color, pack=a.pack, n=a.n, bg=cli_bg)
        print(f"{s['id']:10s} {kb:6.1f}KB  {path}")


if __name__ == "__main__":
    main()
