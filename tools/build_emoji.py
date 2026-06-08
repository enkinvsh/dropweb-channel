"""Сборка одного (или всех) эмодзи: маска -> анимация -> webm. Удобно для пилота.

Использование:
  CLIPROXY_KEY=... python3 -m tools.build_emoji --id db            # пилот
  CLIPROXY_KEY=... python3 -m tools.build_emoji                    # весь набор
  python3 -m tools.build_emoji --id new                           # текст: ключ не нужен
Требует: pip install -r requirements.txt  +  ffmpeg в PATH.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

from . import animate
from .encode import encode_webm
from .gen_icon import generate, generate_edit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "assets/fonts/Unbounded-variable.ttf")  # единственный бренд-шрифт
GEN_CACHE = os.path.join(ROOT, "build/gen")


def _font(px):
    f = ImageFont.truetype(FONT, px)
    try:  # Unbounded — вариативный, ставим тяжёлый вес для панча
        f.set_variation_by_axes([800])
    except Exception:
        pass
    return f


def mask_from_png(path, hi=512):
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    if a.getextrema() == (255, 255):  # непрозрачный -> берём яркость
        a = im.convert("L")
    return a.resize((hi, hi), Image.LANCZOS)


def mask_from_text(text, hi=512, frac=0.5):
    target = 0.90 * hi
    px = int(hi * 0.34)
    f = _font(px)
    probe = ImageDraw.Draw(Image.new("L", (hi, hi)))
    for _ in range(9):
        f = _font(px)
        if chr(10) in text:
            bb = probe.multiline_textbbox((0, 0), text, font=f, spacing=int(hi * 0.06))
        else:
            bb = probe.textbbox((0, 0), text, font=f)
        if (bb[2]-bb[0]) <= target and (bb[3]-bb[1]) <= target:
            break
        px = int(px * 0.85)
    im = Image.new("L", (hi, hi), 0)
    d = ImageDraw.Draw(im)
    if chr(10) in text:
        d.multiline_text((hi / 2, hi / 2), text, fill=255, font=f,
                         anchor="mm", align="center", spacing=int(hi * 0.06))
    else:
        w, h = bb[2]-bb[0], bb[3]-bb[1]
        d.text(((hi - w) / 2 - bb[0], (hi - h) / 2 - bb[1]), text, fill=255, font=f)
    return im


def mask_from_shape(name, hi=512):
    """Маски, нарисованные геометрией (там где шрифт не годится)."""
    im = Image.new("L", (hi, hi), 0)
    d = ImageDraw.Draw(im)
    if name == "bars":  # 4 восходящих столбика сигнала
        n, gap = 4, int(hi * 0.05)
        bw = int((hi * 0.7 - gap * (n - 1)) / n)
        x0 = int(hi * 0.15)
        base = int(hi * 0.78)
        for i in range(n):
            bh = int(hi * (0.18 + 0.16 * i))
            x = x0 + i * (bw + gap)
            d.rectangle([x, base - bh, x + bw, base], fill=255)
    elif name == "arrow_down":  # стрелка вниз (скачать)
        cx = hi // 2
        d.rectangle([cx - hi * 0.07, hi * 0.18, cx + hi * 0.07, hi * 0.55], fill=255)
        d.polygon([(cx - hi * 0.20, hi * 0.50), (cx + hi * 0.20, hi * 0.50),
                   (cx, hi * 0.78)], fill=255)
        d.rectangle([hi * 0.22, hi * 0.86, hi * 0.78, hi * 0.92], fill=255)
    elif name == "warning":  # треугольник с восклицательным знаком
        cx = hi // 2
        d.polygon([(cx, int(hi * 0.15)), (int(hi * 0.12), int(hi * 0.83)),
                   (int(hi * 0.88), int(hi * 0.83))], outline=255, width=int(hi * 0.055))
        d.rectangle([cx - hi * 0.045, hi * 0.40, cx + hi * 0.045, hi * 0.64], fill=255)
        d.rectangle([cx - hi * 0.045, hi * 0.70, cx + hi * 0.045, hi * 0.77], fill=255)
    elif name == "spider_detailed":  # детальный гладкий зелёный паук (не пиксельный)
        cx, cy = hi // 2, int(hi * 0.46)
        lw = max(3, int(hi * 0.014))
        # паутинная нить
        d.line([(cx, int(hi * 0.05)), (cx, cy - int(hi * 0.15))], fill=255, width=lw)
        # тело: голова + брюшко, гладкий outline
        d.ellipse([cx - hi*0.055, cy - hi*0.135, cx + hi*0.055, cy - hi*0.035], outline=255, width=lw)
        d.ellipse([cx - hi*0.085, cy - hi*0.025, cx + hi*0.085, cy + hi*0.155], outline=255, width=lw)
        # рисунок на брюшке
        d.arc([cx-hi*0.045, cy+hi*0.010, cx+hi*0.045, cy+hi*0.115], 205, 335, fill=255, width=max(2,lw//2))
        d.line([(cx, cy+int(hi*0.005)), (cx, cy+int(hi*0.125))], fill=255, width=max(2,lw//2))
        # длинные сегментированные ноги, ближе к рефу
        legs = [
            [(-0.06,-0.08),(-0.22,-0.20),(-0.38,-0.22),(-0.48,-0.16)],
            [(-0.07,-0.03),(-0.25,-0.08),(-0.42,-0.05),(-0.52, 0.03)],
            [(-0.06, 0.03),(-0.24, 0.10),(-0.38, 0.22),(-0.42, 0.34)],
            [(-0.04, 0.10),(-0.15, 0.26),(-0.20, 0.42),(-0.14, 0.52)],
            [( 0.06,-0.08),( 0.22,-0.20),( 0.38,-0.22),( 0.48,-0.16)],
            [( 0.07,-0.03),( 0.25,-0.08),( 0.42,-0.05),( 0.52, 0.03)],
            [( 0.06, 0.03),( 0.24, 0.10),( 0.38, 0.22),( 0.42, 0.34)],
            [( 0.04, 0.10),( 0.15, 0.26),( 0.20, 0.42),( 0.14, 0.52)],
        ]
        for leg in legs:
            pts=[(cx+int(hi*x), cy+int(hi*y)) for x,y in leg]
            d.line(pts, fill=255, width=lw, joint='curve')
        # маленькие глаза/акцент
        r=max(2,int(hi*0.008))
        d.ellipse([cx-hi*0.022-r, cy-hi*0.080-r, cx-hi*0.022+r, cy-hi*0.080+r], fill=255)
        d.ellipse([cx+hi*0.022-r, cy-hi*0.080-r, cx+hi*0.022+r, cy-hi*0.080+r], fill=255)
    elif name == "spider_smooth":  # гладкий не-пиксельный паук (реф: тонкие синие ноги)
        cx, cy = hi // 2, int(hi * 0.48)
        w = max(2, int(hi * 0.018))
        # тело + голова
        d.ellipse([cx - hi*0.055, cy - hi*0.075, cx + hi*0.055, cy + hi*0.075], outline=255, width=w)
        d.ellipse([cx - hi*0.035, cy - hi*0.145, cx + hi*0.035, cy - hi*0.075], outline=255, width=w)
        # ноги: плавные полилинии, тонкие и длинные
        legs = [
            [(-0.04,-0.03),(-0.20,-0.16),(-0.34,-0.24)],
            [(-0.04, 0.00),(-0.23,-0.06),(-0.39,-0.08)],
            [(-0.03, 0.03),(-0.20, 0.10),(-0.33, 0.22)],
            [(-0.02, 0.06),(-0.12, 0.18),(-0.19, 0.34)],
            [( 0.04,-0.03),( 0.20,-0.16),( 0.34,-0.24)],
            [( 0.04, 0.00),( 0.23,-0.06),( 0.39,-0.08)],
            [( 0.03, 0.03),( 0.20, 0.10),( 0.33, 0.22)],
            [( 0.02, 0.06),( 0.12, 0.18),( 0.19, 0.34)],
        ]
        for leg in legs:
            pts=[(cx+int(hi*x), cy+int(hi*y)) for x,y in leg]
            d.line(pts, fill=255, width=w, joint='curve')
    elif name == "sauron_eye":
        cx, cy = hi // 2, hi // 2
        lw = max(3, int(hi * 0.02))
        d.arc([cx - hi*0.40, cy - hi*0.34, cx + hi*0.40, cy + hi*0.46], 205, 335, fill=255, width=lw)
        d.arc([cx - hi*0.40, cy - hi*0.46, cx + hi*0.40, cy + hi*0.34], 25, 155, fill=255, width=lw)
        d.ellipse([cx - hi*0.05, cy - hi*0.28, cx + hi*0.05, cy + hi*0.28], fill=255)
        import math as _m
        for ang in range(0, 360, 24):
            a = _m.radians(ang)
            r1 = hi * 0.43; r2 = r1 + (hi * 0.10 if ang % 48 == 0 else hi * 0.05)
            d.line([(cx + r1*_m.cos(a), cy + r1*_m.sin(a)), (cx + r2*_m.cos(a), cy + r2*_m.sin(a))], fill=255, width=max(2, lw-1))
    elif name == "soap":
        lw = max(3, int(hi * 0.02))
        d.rounded_rectangle([hi*0.18, hi*0.34, hi*0.82, hi*0.66], radius=int(hi*0.07), outline=255, width=lw)
        for yy in (0.44, 0.50, 0.56):
            d.line([(hi*0.30, hi*yy), (hi*0.70, hi*yy)], fill=255, width=max(2, lw-1))
        d.ellipse([hi*0.64, hi*0.24, hi*0.74, hi*0.34], outline=255, width=max(2, lw-1))
        d.ellipse([hi*0.75, hi*0.30, hi*0.80, hi*0.35], outline=255, width=max(2, lw-2))
    elif name == "brick_phone":
        lw = max(3, int(hi * 0.02))
        d.rounded_rectangle([hi*0.34, hi*0.16, hi*0.66, hi*0.86], radius=int(hi*0.045), outline=255, width=lw)
        d.rectangle([hi*0.40, hi*0.24, hi*0.60, hi*0.40], outline=255, width=max(2, lw-1))
        for ry in (0.50, 0.60, 0.70):
            for rx in (0.42, 0.50, 0.58):
                d.ellipse([hi*rx-hi*0.013, hi*ry-hi*0.013, hi*rx+hi*0.013, hi*ry+hi*0.013], fill=255)
        d.line([(hi*0.60, hi*0.16), (hi*0.66, hi*0.04)], fill=255, width=lw)
        d.ellipse([hi*0.645, hi*0.018, hi*0.678, hi*0.05], fill=255)
    elif name == "mushroom":
        lw = max(3, int(hi * 0.02)); cx = hi/2
        d.pieslice([cx-hi*0.40, hi*0.18, cx+hi*0.40, hi*0.66], 180, 360, outline=255, width=lw)
        d.rounded_rectangle([cx-hi*0.22, hi*0.50, cx+hi*0.22, hi*0.84], radius=int(hi*0.06), outline=255, width=lw)
    else:
        raise ValueError(f"неизвестная фигура {name}")
    return im


def _gen_cached(cache_key, prompt, hi=512):
    os.makedirs(GEN_CACHE, exist_ok=True)
    raw = os.path.join(GEN_CACHE, cache_key + ".png")
    if not os.path.exists(raw):
        generate(prompt, raw)
    im = Image.open(raw).convert("L").point(lambda v: 0 if v < 35 else min(255, int((v - 35) * 1.7)))
    return im.resize((hi, hi), Image.LANCZOS)


def mask_from_gen(spec, hi=512):
    return _gen_cached(spec["id"], spec["prompt"], hi)


def _gen_states_seq(spec, hi=512):
    """state0 генерим из текста, остальные — РЕДАКТИРОВАНИЕМ state0 (консистентно)."""
    os.makedirs(GEN_CACHE, exist_ok=True)
    eid = spec["id"]; prompts = spec["states"]
    raw0 = os.path.join(GEN_CACHE, eid + "_s0.png")
    if not os.path.exists(raw0):
        generate(prompts[0], raw0)
    raws = [raw0]; prev = raw0
    chain = spec.get("chain", False)
    for j, pr in enumerate(prompts[1:], start=1):
        rj = os.path.join(GEN_CACHE, "%s_s%d.png" % (eid, j))
        if not os.path.exists(rj):
            src = prev if chain else raw0       # chain: правим предыдущий кадр
            try:
                generate_edit(src, pr, rj)
            except Exception:
                generate(pr, rj)
        raws.append(rj); prev = rj
    out = []
    for r in raws:
        im = Image.open(r).convert("L").point(lambda v: 0 if v < 35 else min(255, int((v - 35) * 1.7)))
        out.append(im.resize((hi, hi), Image.LANCZOS))
    return out


def _fit_mask(mask, target=0.80):
    """Вписать содержимое маски в безопасную зону target*size (центр + поля),
    чтобы ничего не упиралось в край (фикс \"db не влезло\")."""
    m = mask.convert("L")
    bbox = m.getbbox()
    if not bbox:
        return m
    hi = m.size[0]
    crop = m.crop(bbox)
    cw, ch = crop.size
    scale = (target * hi) / max(cw, ch)
    nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
    crop = crop.resize((nw, nh), Image.LANCZOS)
    out = Image.new("L", (hi, hi), 0)
    out.paste(crop, ((hi - nw) // 2, (hi - nh) // 2))
    return out


def build_one(spec, color, palette=None, out_dir=None, fps=30):
    src = spec["source"]
    states = None
    if src == "png":
        mask = mask_from_png(os.path.join(ROOT, spec["asset"]))
    elif src == "text":
        mask = mask_from_text(spec["glyph"])
    elif src == "shape":
        mask = mask_from_shape(spec["shape"])
    elif src == "gen":
        mask = mask_from_gen(spec)
    elif src == "gen_states":
        states = [_fit_mask(m, spec.get("fit", 0.80)) for m in _gen_states_seq(spec)]
        mask = states[0]
    elif src == "text_states":
        states = [_fit_mask(mask_from_text(g), spec.get("fit", 0.80))
                  for g in spec["states"]]
        mask = states[0]
    else:
        raise ValueError(f"неизвестный source {src}")
    mask = _fit_mask(mask, spec.get("fit", 0.80))
    deg = spec.get("rotate_deg")
    if deg:
        hi = mask.size[0]
        rot = mask.rotate(deg, resample=Image.BICUBIC, expand=True, fillcolor=0)
        rot.thumbnail((int(hi * 0.98), int(hi * 0.98)), Image.LANCZOS)
        canvas = Image.new("L", (hi, hi), 0)
        canvas.paste(rot, ((hi - rot.size[0]) // 2, (hi - rot.size[1]) // 2))
        mask = canvas
    fn = animate.EFFECTS.get(spec.get("anim", "breath"), animate.breath)
    kw = {"palette": palette}
    if states is not None:
        kw["states"] = states
        kw["transition"] = spec.get("transition", "crossfade")
    render_color = spec.get("color", color)
    _SIZE = int(os.environ.get("RENDER_SIZE", "100"))
    _MARGIN = max(0, int(os.environ.get("EMOJI_MARGIN", "8")) * _SIZE // 100)
    frames = fn(mask, _SIZE, render_color, **kw)
    out_dir = out_dir or os.path.join(ROOT, "build/emoji")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, spec["id"] + ".webm")
    _S = _SIZE; _M = _MARGIN; _inner = max(1, _S - 2 * _M)
    _ts = _S * 4
    _th = Image.new("L", (_ts, _ts), 0)
    ImageDraw.Draw(_th).rounded_rectangle(
        [_M * 4, _M * 4, _ts - 1 - _M * 4, _ts - 1 - _M * 4],
        radius=max(2, int(_inner * 0.18 * 4)), fill=255)
    _tmask = _th.resize((_S, _S), Image.LANCZOS)
    _flat = []
    for f in frames:
        canvas = Image.new("RGBA", (_S, _S), (0, 0, 0, 255))
        canvas.alpha_composite(f.convert("RGBA").resize((_inner, _inner), Image.LANCZOS), (_M, _M))
        canvas.putalpha(_tmask)
        _flat.append(canvas)
    frames = _flat
    return encode_webm(frames, out, fps=fps, size=_S)


def load_set(pack="dropweb"):
    pack_path = os.path.join(ROOT, "packs", pack, "pack.json")
    path = pack_path if os.path.exists(pack_path) else os.path.join(ROOT, "emoji_set.json")
    with open(path) as f:
        return json.load(f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--id", help="id одного эмодзи (пилот)")
    p.add_argument("--color", default=None, help="переопределить неон hex")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--pack", default="dropweb", help="имя пака в packs/<name>/pack.json")
    a = p.parse_args()
    data = load_set(a.pack)
    color = a.color or data["meta"]["default_color"]
    palette = data.get("theme_cycle")
    specs = [s for s in data["emoji"] if not a.id or s["id"] == a.id]
    if not specs:
        raise SystemExit(f"нет эмодзи с id={a.id}")
    out_dir = os.path.join(ROOT, "build", a.pack, "emoji")
    for s in specs:
        path, kb = build_one(s, color, palette=palette, out_dir=out_dir, fps=a.fps)
        print(f"{s['id']:10s} {kb:6.1f}КБ  {path}")


if __name__ == "__main__":
    main()
