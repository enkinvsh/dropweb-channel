"""animate2 — premium effects on the new numpy stack.

These keep the EXACT effect contract from animate.py:

    fn(mask, size, color, **kw) -> list[RGBA PIL frames]   (seamless loop)

so build_emoji.py can call them through the same EFFECTS registry. They layer
the new modules (bloom, particles, crt, easing, motion blur) on top of
phosphor2 to demonstrate the "badass" upgrade. Every effect:
  * loops seamlessly (phase-based / ping-pong / warm-up)
  * passes a rolling `phase` into phosphor2 so the CRT scanlines scroll
  * stays 100x100 RGBA and transparent (alpha webm safe)
  * runs CPU-only; if numpy is missing, phosphor2 degrades and these still run

This file is additive — it does NOT modify the existing animate.py. The proposal
explains how to fold these back into animate.py once approved.
"""
import math

from PIL import Image

from . import easing
from .phosphor2 import phosphor2, motion_blur

try:
    import numpy as np
    from . import raster, bloom, particles, crt
    _NUMPY = True
except Exception:  # pragma: no cover
    _NUMPY = False


# --- 1. ember_breath: phosphor breath + rising embers + CRT ------------------

def ember_breath(mask, size, color, n=84, **k):
    """Slow branded breath with a fountain of additive embers behind the glyph.

    Showcases: bloom + particle system + seamless CRT roll + bezier breath.
    """
    out = []
    if not _NUMPY:  # graceful: just the breathing glow
        for i in range(n):
            g = 0.8 + 0.3 * easing.ping_pong(i, n, ease=easing.BRAND)
            out.append(phosphor2(mask, size=size, color=color, glow=g,
                                 phase=easing.loop_phase(i, n)))
        return out

    col = raster.hex_to_linear(color)
    ember_bufs = particles.ember_loop(size, col, n, seed=hash(str(mask.size)) & 0xFFFF,
                                      rate=10, cx=size * 0.5, cy=size * 0.66)
    for i in range(n):
        phase = easing.loop_phase(i, n)
        g = 0.85 + 0.30 * easing.ping_pong(i, n, ease=easing.BRAND)
        base = phosphor2(mask, size=size, color=color, glow=g, phase=phase,
                         crt_post=False)  # CRT applied once at the end on the comp
        # composite embers (additive) under/over the glyph in linear space
        glyph = _pil_to_buf(base)
        emb = bloom.apply(ember_bufs[i], levels=4, base_sigma=1.0, intensity=1.2)
        comp = raster.add(raster.new_buffer(size, size), emb, gain=0.9)
        comp = raster.over(comp, glyph)
        comp = crt.apply_crt(comp, phase=phase, barrel_k=0.07, chroma=1.0,
                             scan_depth=0.28, scan_period=2.2, vig=0.36,
                             noise=0.03)
        out.append(raster.to_pil(comp))
    return out


# --- 2. spin3d: pseudo-3D rotation with subframe MOTION BLUR -----------------

def spin3d(mask, size, color, n=84, **k):
    """The old `spin` reimagined: width by |cos|, but each frame is motion-blurred
    across 3 subframes so the fast edge smears like real rotation."""
    base = mask.convert("L").resize((size, size), Image.LANCZOS)

    def render_at(t):
        c = math.cos(2 * math.pi * t)
        w = max(int(size * 0.30), int(size * abs(c)))
        src = base if c >= 0 else base.transpose(Image.FLIP_LEFT_RIGHT)
        m2 = Image.new("L", (size, size), 0)
        m2.paste(src.resize((w, size), Image.LANCZOS), ((size - w) // 2, 0))
        return phosphor2(m2, size=size, color=color,
                         glow=0.6 + 0.45 * abs(c), phase=t)

    out = []
    for i in range(n):
        sub = 3 if _NUMPY else 1
        out.append(motion_blur(lambda s: render_at((i + s) / n), n_sub=sub))
    return out


# --- 3. shock_ring: expanding ring eased by a snappy cubic-bezier ------------

def shock_ring(mask, size, color, n=90, **k):
    """Expanding additive shock ring on a SNAP curve (fast out, soft settle).
    Far more deliberate than the old linear ring."""
    from PIL import ImageDraw
    out = []
    for i in range(n):
        phase = easing.loop_phase(i, n)
        t = easing.SNAP(phase)              # eased radius growth
        glow = 0.9 + 0.15 * easing.loop_sin(i, n)
        canvas = phosphor2(mask, size=size, color=color, glow=glow, phase=phase)
        rm = Image.new("L", (size, size), 0)
        d = ImageDraw.Draw(rm)
        rad = int((0.16 + 0.36 * t) * size)
        w = max(1, int(size * 0.06 * (1 - t)))
        d.ellipse([size / 2 - rad, size / 2 - rad, size / 2 + rad, size / 2 + rad],
                  outline=255, width=w)
        ring = phosphor2(rm, size=size, color=color, glow=0.6, scanlines=False,
                         crt_post=False, phase=phase)
        # fade the ring out as it expands (seamless: alpha 0 at loop end)
        fade = (1.0 - t)
        if _NUMPY:
            rb = _pil_to_buf(ring) * np.float32(fade)
            cb = raster.add(_pil_to_buf(canvas), rb, gain=1.0)
            out.append(raster.to_pil(cb))
        else:
            ring.putalpha(ring.getchannel("A").point(lambda a: int(a * fade)))
            canvas.alpha_composite(ring)
            out.append(canvas)
    return out


def _pil_to_buf(img):
    """sRGB RGBA PIL -> linear premultiplied buffer (numpy path only)."""
    arr = np.asarray(img).astype(np.float32) / 255.0
    a = arr[..., 3:4]
    lin = raster.srgb_to_linear(arr[..., :3]) * a
    return np.concatenate([lin, a], axis=-1)



# --- 4. impulse: charge -> snap -> settle, bloom packet + micro scale ---------

def _event(p, s, e):
    return 0.0 if (p < s or p > e) else (p - s) / (e - s)


def _scale_mask(mask, size, sc):
    base = mask.convert("L").resize((size, size), Image.LANCZOS)
    w = max(1, int(size * sc))
    m = Image.new("L", (size, size), 0)
    m.paste(base.resize((w, w), Image.LANCZOS), ((size - w) // 2, (size - w) // 2))
    return m


def _lerp_hex(a, b, t):
    from .phosphor2 import hex_rgb
    ca, cb = hex_rgb(a), hex_rgb(b)
    return "#%02X%02X%02X" % tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))


def _scale_xy(mask, size, sx, sy):
    base = mask.convert("L").resize((size, size), Image.LANCZOS)
    w = max(1, int(size * sx)); h = max(1, int(size * sy))
    r = base.resize((w, h), Image.LANCZOS)
    m = Image.new("L", (size, size), 0)
    m.paste(r, ((size - w) // 2, (size - h) // 2))
    return m


def _shift(mask, dx, dy):
    m = Image.new("L", mask.size, 0)
    m.paste(mask, (int(dx), int(dy)))
    return m


def impulse(mask, size, color, n=90, **k):
    """Плавное дыхание формы (scale breathing) + один мотивированный пакет
    (bloom surge + squash snap). Форма реально меняется, луп длинный и плавный."""
    out = []
    for i in range(n):
        phase = easing.loop_phase(i, n)
        breath = 0.5 - 0.5 * math.cos(2 * math.pi * phase)        # 0..1..0 гладко
        u = _event(phase, 0.10, 0.46)
        packet = (math.sin(math.pi * u) ** 2) if u > 0 else 0.0
        sx = 0.965 + 0.035 * breath + 0.06 * packet
        sy = sx * (1.0 - 0.05 * packet)                            # squash на снэпе
        m2 = _scale_xy(mask, size, sx, sy)
        glow = 0.9 + 0.5 * packet + 0.06 * breath
        out.append(phosphor2(m2, size=size, color=color, glow=glow, phase=phase,
                             bloom_intensity=1.6))
    return out


# --- 5. glitch_crt: controlled digital glitch packets + chroma spike ----------

def _slice_glitch(img, amp):
    if not _NUMPY:
        return img
    import random as _r
    a = np.asarray(img).copy()
    h = a.shape[0]
    for _ in range(3):
        y = _r.randint(0, h - 4)
        hh = _r.randint(2, 8)
        dx = _r.randint(-amp, amp)
        a[y:y + hh] = np.roll(a[y:y + hh], dx, axis=1)
    return Image.fromarray(a, "RGBA")


def glitch_crt(mask, size, color, n=90, **k):
    """Mostly stable, two short glitch hits (slice roll + bright chroma). Hacker/alert."""
    out = []
    for i in range(n):
        phase = easing.loop_phase(i, n)
        g = max(math.sin(math.pi * _event(phase, 0.22, 0.29)) ** 2,
                math.sin(math.pi * _event(phase, 0.64, 0.71)) ** 2)
        img = phosphor2(mask, size=size, color=color, glow=0.92 + 0.45 * g, phase=phase)
        if g > 0.06:
            img = _slice_glitch(img, int(2 + 6 * g))
        out.append(img)
    return out


# --- 6. color_cycle2: cycle through the 6 theme colors with premium bloom -----

def color_cycle2(mask, size, color, n=90, palette=None, **k):
    palette = palette or ["#00DE52", "#38BDF8", "#A78BFA", "#EF4444", "#F59E0B", "#64748B"]
    out = []
    seg = max(1, n // len(palette))
    for i in range(n):
        f = i / seg
        a, b = int(f) % len(palette), (int(f) + 1) % len(palette)
        c = _lerp_hex(palette[a], palette[b], f - int(f))
        out.append(phosphor2(mask, size=size, color=c, glow=1.0,
                             phase=easing.loop_phase(i, n)))
    return out



def beat(mask, size, color, n=90, **k):
    """Сердцебиение: двойной squash&stretch (форма пульсирует)."""
    out = []
    for i in range(n):
        phase = easing.loop_phase(i, n)
        t1 = math.sin(math.pi * _event(phase, 0.05, 0.20)) ** 2
        t2 = math.sin(math.pi * _event(phase, 0.24, 0.42)) ** 2
        a = max(t1, 0.7 * t2)
        m2 = _scale_xy(mask, size, 1.0 + 0.11 * a, 1.0 - 0.08 * a)
        out.append(phosphor2(m2, size=size, color=color, glow=0.9 + 0.5 * a, phase=phase))
    return out


def bounce(mask, size, color, n=90, **k):
    """Имба-прыжок: squash&stretch (узкий+высокий в воздухе, широкий+низкий на земле),
    два подскока за луп с подлётом вверх."""
    out = []
    for i in range(n):
        p = easing.loop_phase(i, n)
        air = abs(math.sin(math.pi * p * 2))      # 0..1..0..1..0 (два прыжка)
        sx = 1.0 - 0.12 * air + 0.10 * (1 - air)   # в воздухе уже, на земле шире
        sy = 1.0 + 0.16 * air - 0.10 * (1 - air)   # в воздухе выше, на земле ниже
        m = _scale_xy(mask, size, sx, sy)
        m = _shift(m, 0, -size * 0.12 * air)        # подлёт вверх
        out.append(phosphor2(m, size=size, color=color,
                             glow=0.9 + 0.2 * air, phase=p))
    return out


def assemble(mask, size, color, n=90, block=12, **k):
    """Иконка собирается из блоков от центра наружу (реальная сборка формы)."""
    if not _NUMPY:
        return impulse(mask, size, color, n=n)
    base = mask.convert("L").resize((size, size), Image.LANCZOS)
    arr = np.asarray(base)
    blocks = []
    for by in range(0, size, block):
        for bx in range(0, size, block):
            if arr[by:by + block, bx:bx + block].max() > 12:
                blocks.append((bx, by))
    cx = cy = size / 2.0
    blocks.sort(key=lambda b: (b[0] + block / 2 - cx) ** 2 + (b[1] + block / 2 - cy) ** 2)
    build = int(n * 0.55)
    out = []
    for i in range(n):
        phase = easing.loop_phase(i, n)
        if i >= build:
            m = base
        else:
            kk = int(len(blocks) * easing.BRAND(i / max(1, build)))
            pa = np.zeros_like(arr)
            for (bx, by) in blocks[:kk]:
                pa[by:by + block, bx:bx + block] = arr[by:by + block, bx:bx + block]
            m = Image.fromarray(pa, "L")
        glow = 0.82 + 0.2 * min(1.0, i / max(1, build))
        out.append(phosphor2(m, size=size, color=color, glow=glow, phase=phase))
    return out



def _blend_l(a, b, t):
    return Image.blend(a.convert("L"), b.convert("L"), max(0.0, min(1.0, t)))


def _wipe_l(a, b, t, size):
    """CRT-вайп: B проявляется сверху вниз по A, с яркой полосой развёртки на стыке."""
    if not _NUMPY:
        return _blend_l(a, b, t)
    aa = np.asarray(a.convert("L")).astype(np.float32)
    bb = np.asarray(b.convert("L")).astype(np.float32)
    y = np.arange(size)[:, None]
    edge = t * size
    m = (y < edge).astype(np.float32)
    band = np.exp(-((y - edge) ** 2) / (2 * 3.5 ** 2)) * 255.0  # светящаяся развёртка
    out = bb * m + aa * (1 - m)
    out = np.maximum(out, band * (0.0 < t < 1.0))
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"), "L")


def sequence(mask, size, color, n=90, states=None, transition="crossfade",
             hold=0.55, **k):
    """Покадровый переход между несколькими состояниями (профессиональный сценарий).
    Каждое состояние держится hold, затем плавный eased-переход в следующее.
    transition: crossfade | wipe | glitch_cut. Луп бесшовный (последнее->первое)."""
    states = states or [mask]
    base = [s.convert("L").resize((size, size), Image.LANCZOS) for s in states]
    S = len(base)
    out = []
    for i in range(n):
        phase = easing.loop_phase(i, n)
        pos = (i / n) * S
        idx = int(pos) % S
        nxt = (idx + 1) % S
        local = pos - math.floor(pos)
        t = 0.0 if local < hold else easing.BRAND((local - hold) / (1.0 - hold))
        if transition == "type":
            m = base[idx]
        elif transition == "wipe":
            m = _wipe_l(base[idx], base[nxt], t, size)
        else:
            m = _blend_l(base[idx], base[nxt], t)
        glow = 0.9 + 0.3 * math.sin(math.pi * t)             # всплеск на переходе
        img = phosphor2(m, size=size, color=color, glow=glow, phase=phase)
        if transition == "glitch_cut" and 0.04 < t < 0.96:
            img = _slice_glitch(img, int(2 + 7 * math.sin(math.pi * t)))
        out.append(img)
    return out



def power_off(mask, size, color, n=90, **k):
    """CRT-выключение: держим -> схлоп по вертикали в яркую линию -> гаснет -> снова включаемся (бесшовно)."""
    base = mask.convert("L").resize((size, size), Image.LANCZOS)
    out = []
    for i in range(n):
        phase = easing.loop_phase(i, n)
        if phase < 0.5:
            sy, gl = 1.0, 0.95
        elif phase < 0.60:
            u = easing.BRAND((phase - 0.5) / 0.10); sy = 1.0 - 0.97 * u; gl = 0.9 + 0.7 * u
        elif phase < 0.78:
            sy, gl = 0.03, 0.35
        else:
            u = easing.BRAND((phase - 0.78) / 0.22); sy = 0.03 + 0.97 * u; gl = 0.5 + 0.45 * u
        h = max(1, int(size * sy))
        m = Image.new("L", (size, size), 0)
        m.paste(base.resize((size, h), Image.LANCZOS), (0, (size - h) // 2))
        out.append(phosphor2(m, size=size, color=color, glow=gl, phase=phase))
    return out


def rocket_launch(mask, size, color, n=84, **k):
    """Ракета вибрирует + подрагивает вверх + выхлоп-искры (маска уже диагональная)."""
    import random as _r
    base = mask.convert("L").resize((size, size), Image.LANCZOS)
    out = []
    if not _NUMPY:
        for i in range(n):
            phase = easing.loop_phase(i, n)
            dx = int(_r.uniform(-1.6, 1.6)); dy = int(_r.uniform(-1.6, 1.6)) - int(size * 0.02 * math.sin(2 * math.pi * phase))
            m = Image.new("L", (size, size), 0); m.paste(base, (dx, dy))
            out.append(phosphor2(m, size=size, color=color, glow=0.95, phase=phase))
        return out
    col = raster.hex_to_linear(color)
    emb = particles.ember_loop(size, col, n, seed=777, rate=14, cx=size * 0.40, cy=size * 0.60)
    for i in range(n):
        phase = easing.loop_phase(i, n)
        dx = int(_r.uniform(-1.8, 1.8)); dy = int(_r.uniform(-1.8, 1.8)) - int(size * 0.02 * math.sin(2 * math.pi * phase))
        m = Image.new("L", (size, size), 0); m.paste(base, (dx, dy))
        glyph = _pil_to_buf(phosphor2(m, size=size, color=color, glow=0.95, phase=phase, crt_post=False))
        e = bloom.apply(emb[i], levels=4, base_sigma=1.0, intensity=1.2)
        comp = raster.add(raster.new_buffer(size, size), e, gain=0.9)
        comp = raster.over(comp, glyph)
        comp = crt.apply_crt(comp, phase=phase, barrel_k=0.07, chroma=1.0,
                             scan_depth=0.28, scan_period=2.2, vig=0.36, noise=0.03)
        out.append(raster.to_pil(comp))
    return out



# ===== ДИСТОРШН-ВАРПЫ: гнём/тянем один кадр (без покадровой генерации) =====
def _warp(mask, srcfn, res=256):
    """Сэмплим source-координаты -> гнём изображение. Бесшовно при t in [0,1)."""
    if not _NUMPY:
        return mask
    from scipy.ndimage import map_coordinates
    a = np.asarray(mask.convert("L").resize((res, res), Image.LANCZOS), dtype=np.float32)
    h, w = a.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sx, sy = srcfn(xx, yy, w, h)
    out = map_coordinates(a, [sy, sx], order=1, mode="constant", cval=0.0)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"), "L")


def jelly(mask, size, color, n=90, amp=0.05, freq=1.6, **k):
    """Желейный вобл: синусный сдвиг по x и y -> гуттаперчевое дрожание."""
    out = []
    for i in range(n):
        t = i / n
        def f(xx, yy, w, h, t=t):
            dx = amp * w * np.sin(2 * np.pi * (yy / h * freq + t))
            dy = amp * h * np.sin(2 * np.pi * (xx / w * freq + t))
            return xx - dx, yy - dy
        out.append(phosphor2(_warp(mask, f), size=size, color=color, glow=0.95, phase=t))
    return out


def wave(mask, size, color, n=90, amp=0.07, freq=2.2, **k):
    """Колыхание: бегущая волна, верх ходит сильнее (язык пламени/флаг)."""
    out = []
    for i in range(n):
        t = i / n
        def f(xx, yy, w, h, t=t):
            top = ((h - yy) / h) ** 1.5
            dx = amp * w * np.sin(2 * np.pi * (yy / h * freq - t)) * top
            return xx - dx, yy
        out.append(phosphor2(_warp(mask, f), size=size, color=color, glow=0.95, phase=t))
    return out


def sway(mask, size, color, n=90, amp=0.10, **k):
    """Качание: верх наклоняется из стороны в сторону."""
    out = []
    for i in range(n):
        t = i / n
        def f(xx, yy, w, h, t=t):
            dx = amp * w * np.sin(2 * np.pi * t) * ((h - yy) / h) ** 2
            return xx - dx, yy
        out.append(phosphor2(_warp(mask, f), size=size, color=color, glow=0.95, phase=t))
    return out


def pump(mask, size, color, n=90, amp=0.12, **k):
    """Пульс: squash&stretch через варп вокруг центра (площадь ~сохр.)."""
    out = []
    for i in range(n):
        t = i / n
        sca = amp * math.sin(2 * np.pi * t)
        def f(xx, yy, w, h, sca=sca):
            cx, cy = w / 2.0, h / 2.0
            return cx + (xx - cx) / (1 + sca), cy + (yy - cy) / (1 - sca)
        gl = 0.9 + 0.25 * abs(math.sin(2 * np.pi * t))
        out.append(phosphor2(_warp(mask, f), size=size, color=color, glow=gl, phase=t))
    return out


def twist(mask, size, color, n=90, amp=0.7, **k):
    """Кручение: свирл вокруг центра, угол растёт к краю и осциллирует."""
    out = []
    for i in range(n):
        t = i / n
        a0 = amp * math.sin(2 * np.pi * t)
        def f(xx, yy, w, h, a0=a0):
            cx, cy = w / 2.0, h / 2.0
            dx, dy = xx - cx, yy - cy
            r = np.sqrt(dx * dx + dy * dy)
            ang = a0 * (1 - np.clip(r / (w * 0.5), 0, 1))
            ca, sa = np.cos(ang), np.sin(ang)
            return cx + ca * dx + sa * dy, cy - sa * dx + ca * dy
        out.append(phosphor2(_warp(mask, f), size=size, color=color, glow=0.95, phase=t))
    return out


def blink_warp(mask, size, color, n=90, **k):
    """Моргание сжатием по вертикали: открыто долго, быстрый «хлоп»."""
    out = []
    for i in range(n):
        t = i / n
        def closepulse(c):
            return max(0.0, math.sin(math.pi * (c - 0.42) / 0.12)) ** 2 if 0.42 <= c <= 0.54 else 0.0
        cl = closepulse(t)
        scy = 1.0 - 0.93 * cl
        def f(xx, yy, w, h, scy=scy):
            cy = h / 2.0
            return xx, cy + (yy - cy) / max(0.07, scy)
        out.append(phosphor2(_warp(mask, f), size=size, color=color, glow=0.95, phase=t))
    return out


def shake_warp(mask, size, color, n=90, amp=0.03, **k):
    """Вибрация/тряска: высокочастотный сдвиг + лёгкое качание (ракета)."""
    out = []
    for i in range(n):
        t = i / n
        ddx = amp * math.sin(2 * np.pi * t * 11) + 0.04 * math.sin(2 * np.pi * t)
        ddy = amp * math.sin(2 * np.pi * t * 13)
        def f(xx, yy, w, h, ddx=ddx, ddy=ddy):
            return xx - ddx * w, yy - ddy * h
        out.append(phosphor2(_warp(mask, f), size=size, color=color, glow=0.95, phase=t))
    return out



# ===== СТРОГИЕ CRT/MS-DOS ДИСТОРШНЫ (не jelly/cartoon) =====
def corner_pin(mask, size, color, n=90, amp=0.18, corner="tr", **k):
    """Corner-pin / PowerPin: один угол слоя тянется крупнее/мельче, как экранная
    перспектива. Сдержанный AE-style distortion, не пьяное wobble."""
    corners={"tl":(0,0),"tr":(1,0),"br":(1,1),"bl":(0,1)}
    cxn,cyn=corners.get(corner,(1,0))
    out=[]
    for i in range(n):
        t=i/n
        m=amp*math.sin(2*math.pi*t)
        def f(xx,yy,w,h,m=m,cxn=cxn,cyn=cyn):
            x=xx/(w-1); y=yy/(h-1)
            wx=(1-x) if cxn==0 else x
            wy=(1-y) if cyn==0 else y
            wt=(wx*wy)**1.35
            cx=cxn*(w-1); cy=cyn*(h-1)
            denom=np.maximum(0.72,1+m*wt)
            sx=cx+(xx-cx)/denom
            sy=cy+(yy-cy)/denom
            return sx,sy
        out.append(phosphor2(_warp(mask,f),size=size,color=color,glow=0.95,phase=t))
    return out


def keystone(mask, size, color, n=90, amp=0.16, **k):
    """Keystone/экран под углом: верх/низ масштабируются по-разному, как плоскость
    терминального экрана, без резиновой органики."""
    out=[]
    for i in range(n):
        t=i/n
        a=amp*math.sin(2*math.pi*t)
        def f(xx,yy,w,h,a=a):
            cx=w/2; y=(yy/(h-1)-0.5)
            scale=np.maximum(0.70,1+a*y)
            return cx+(xx-cx)/scale, yy
        out.append(phosphor2(_warp(mask,f),size=size,color=color,glow=0.95,phase=t))
    return out


def hsync_tear(mask, size, color, n=90, amp=0.13, **k):
    """H-sync tear: горизонтальные строки уезжают волной/полосой, как сбой синхры
    на CRT. Строго сигналовый эффект."""
    out=[]
    for i in range(n):
        t=i/n
        def f(xx,yy,w,h,t=t):
            y=yy/(h-1)
            band=np.exp(-((y-((t*1.15)%1.0))**2)/(2*0.035**2))
            wig=0.20*np.sin(2*np.pi*(y*7+t*2))
            dx=w*amp*band*(1+wig)
            return xx-dx, yy
        out.append(phosphor2(_warp(mask,f),size=size,color=color,glow=0.95,phase=t))
    return out


def crt_refresh(mask, size, color, n=90, **k):
    """CRT refresh/beam line: форма стабильна, по ней проходит яркая строка развёртки."""
    out=[]
    base=mask.convert("L").resize((size,size),Image.LANCZOS)
    for i in range(n):
        t=i/n
        img=phosphor2(mask,size=size,color=color,glow=0.92,phase=t)
        if _NUMPY:
            a=np.asarray(base).astype(np.float32)
            y=np.arange(size)[:,None]
            edge=(t*size)
            band=np.exp(-((y-edge)**2)/(2*3.0**2))*a
            bm=Image.fromarray(np.clip(band,0,255).astype("uint8"),"L")
            sweep=phosphor2(bm,size=size,color="#FFFFFF",glow=0.65,scanlines=False,crt_post=False)
            img.alpha_composite(sweep)
        out.append(img)
    return out



def _homography(src, dst):
    """Матрица H: src -> dst по 4 точкам."""
    A=[]
    for (x,y),(u,v) in zip(src,dst):
        A.append([x,y,1,0,0,0,-u*x,-u*y])
        A.append([0,0,0,x,y,1,-v*x,-v*y])
    A=np.asarray(A,dtype=np.float64)
    b=np.asarray([p for uv in dst for p in uv],dtype=np.float64)
    h=np.linalg.solve(A,b)
    return np.array([[h[0],h[1],h[2]],[h[3],h[4],h[5]],[h[6],h[7],1.0]],dtype=np.float64)


def _projective_mask(mask, dst, res=256):
    """Настоящий Corner Pin: исходный прямоугольник -> dst quad, сэмплим обратной H."""
    if not _NUMPY:
        return mask
    from scipy.ndimage import map_coordinates
    src=np.array([[0,0],[res-1,0],[res-1,res-1],[0,res-1]],dtype=np.float64)
    H=_homography(src,np.asarray(dst,dtype=np.float64))
    Hi=np.linalg.inv(H)
    a=np.asarray(mask.convert("L").resize((res,res),Image.LANCZOS),dtype=np.float32)
    yy,xx=np.mgrid[0:res,0:res].astype(np.float64)
    ones=np.ones_like(xx)
    p=np.stack([xx,yy,ones],axis=0).reshape(3,-1)
    q=Hi@p
    q=q/q[2:3]
    sx=q[0].reshape(res,res); sy=q[1].reshape(res,res)
    out=map_coordinates(a,[sy,sx],order=1,mode="constant",cval=0.0)
    return Image.fromarray(np.clip(out,0,255).astype("uint8"),"L")


def projective_pin(mask, size, color, n=90, corner="tr", amp=0.16, **k):
    """Настоящий AE Corner Pin / Power Pin: один угол тянется наружу/внутрь,
    противоположные слегка компенсируют перспективу. Сдержанно, экранно, MS-DOS."""
    out=[]; res=256
    for i in range(n):
        t=i/n
        a=amp*math.sin(2*math.pi*t)
        # tl,tr,br,bl в пикселях output-квадрата
        tl=np.array([12,10],float); tr=np.array([res-13,12],float)
        br=np.array([res-10,res-12],float); bl=np.array([10,res-10],float)
        # pull выбранного угла: наружу + вверх/вбок, обратная фаза делает smaller
        if corner=="tr": tr += np.array([res*0.42*a, -res*0.24*a]); br += np.array([res*0.12*a,res*0.08*a])
        elif corner=="tl": tl += np.array([-res*0.42*a, -res*0.24*a]); bl += np.array([-res*0.12*a,res*0.08*a])
        elif corner=="br": br += np.array([res*0.42*a, res*0.24*a]); tr += np.array([res*0.12*a,-res*0.08*a])
        else: bl += np.array([-res*0.42*a, res*0.24*a]); tl += np.array([-res*0.12*a,-res*0.08*a])
        m=_projective_mask(mask,[tl,tr,br,bl],res=res)
        out.append(phosphor2(m,size=size,color=color,glow=0.95,phase=t))
    return out


def signal_pull(mask, size, color, n=90, amp=0.10, **k):
    """Не резина, а аналоговый сбой: несколько горизонтальных полос растягивают слой."""
    out=[]
    for i in range(n):
        t=i/n
        def f(xx,yy,w,h,t=t):
            y=yy/(h-1)
            band1=np.exp(-((y-((t*1.0)%1.0))**2)/(2*0.020**2))
            band2=np.exp(-((y-((t*1.0+0.37)%1.0))**2)/(2*0.014**2))
            dx=w*amp*(band1-band2)*np.sin(2*np.pi*(t*2+y*3))
            sx=xx-dx
            return sx,yy
        out.append(phosphor2(_warp(mask,f),size=size,color=color,glow=0.95,phase=t))
    return out



# ===== ДИНАМИКА РАЗМЕРОВ / SCALE MOTION (MS-DOS/CRT, без пьяной резины) =====
def snap_zoom(mask, size, color, n=90, min_s=0.72, max_s=1.03, **k):
    """Boot-pop: иконка появляется масштабом 72% -> overshoot -> стабилизация.
    Чистый size-change, без кривого organic warp."""
    out=[]
    for i in range(n):
        p=i/n
        if p < 0.18:
            u=easing.BRAND(p/0.18); sc=min_s+(max_s+0.08-min_s)*u
        elif p < 0.32:
            u=easing.BRAND((p-0.18)/0.14); sc=(max_s+0.08)+(max_s-(max_s+0.08))*u
        else:
            sc=max_s+0.015*math.sin(2*math.pi*(p-0.32))*math.exp(-4*(p-0.32))
        m=_scale_xy(mask,size,sc,sc)
        out.append(phosphor2(m,size=size,color=color,glow=0.85+0.25*min(1,p/0.18),phase=p))
    return out


def platform_pop(mask, size, color, n=90, **k):
    """Для платформ: crisp scale-in + короткий CRT refresh sweep. Как логотип OS
    вспыхнул на старом мониторе."""
    out=[]
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    for i in range(n):
        p=i/n
        # two-stage: small -> big -> stable, then subtle second pulse
        if p < 0.22:
            u=easing.SNAP(p/0.22); sc=0.62+0.46*u
        elif p < 0.36:
            u=easing.BRAND((p-0.22)/0.14); sc=1.08-0.08*u
        else:
            sc=1.0+0.025*math.sin(2*math.pi*(p-0.36))*math.exp(-3*(p-0.36))
        m=_scale_xy(mask,size,sc,sc)
        img=phosphor2(m,size=size,color=color,glow=0.9+0.25*(p<0.36),phase=p)
        # короткая белая строка в момент boot-pop
        if 0.16 < p < 0.32 and _NUMPY:
            y=np.arange(size)[:,None]; edge=((p-0.16)/0.16)*size
            a=np.asarray(base).astype(np.float32)
            band=np.exp(-((y-edge)**2)/(2*2.5**2))*a
            bm=Image.fromarray(np.clip(band,0,255).astype('uint8'),'L')
            sweep=phosphor2(bm,size=size,color='#FFFFFF',glow=0.45,scanlines=False,crt_post=False)
            img.alpha_composite(sweep)
        out.append(img)
    return out


def anchor_scale(mask, size, color, n=90, anchor='bottom', **k):
    """Масштаб от якоря (как окно/иконка всплывает с панели): низ/центр остаётся
    почти на месте, верх растёт. Под платформы/доки/мониторы."""
    out=[]
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    for i in range(n):
        p=i/n
        u=easing.BRAND(min(1,p/0.28)) if p<0.28 else 1.0
        sc=0.65+0.38*u
        w=max(1,int(size*sc)); h=max(1,int(size*sc))
        r=base.resize((w,h),Image.LANCZOS)
        m=Image.new('L',(size,size),0)
        x=(size-w)//2
        y=size-h-4 if anchor=='bottom' else (size-h)//2
        m.paste(r,(x,y))
        out.append(phosphor2(m,size=size,color=color,glow=0.85+0.2*u,phase=p))
    return out



def platform_scale(mask, size, color, n=90, **k):
    """Платформенный boot-scale: ТОЛЬКО изменение размера, никакой деформации.
    Маленькое -> крупное -> overshoot -> hold -> мягкий reset. MS-DOS/CRT pop."""
    out=[]
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    for i in range(n):
        p=i/n
        if p < 0.16:
            u=easing.SNAP(p/0.16); sc=0.42+0.72*u          # резкий вход
        elif p < 0.26:
            u=easing.BRAND((p-0.16)/0.10); sc=1.14-0.14*u # overshoot settle
        elif p < 0.76:
            sc=1.0+0.025*math.sin(2*math.pi*(p-0.26)/0.50) # живой hold без кривизны
        else:
            u=easing.BRAND((p-0.76)/0.24); sc=1.0-0.58*u  # уход к началу, бесшовно
        w=max(1,int(size*sc)); h=max(1,int(size*sc))
        r=base.resize((w,h),Image.LANCZOS)
        m=Image.new('L',(size,size),0)
        m.paste(r,((size-w)//2,(size-h)//2))
        img=phosphor2(m,size=size,color=color,glow=0.82+0.25*min(1,sc),phase=p)
        # строгая refresh-line только в момент boot-pop
        if 0.08 < p < 0.24 and _NUMPY:
            y=np.arange(size)[:,None]; edge=((p-0.08)/0.16)*size
            a=np.asarray(m).astype(np.float32)
            band=np.exp(-((y-edge)**2)/(2*2.2**2))*a
            bm=Image.fromarray(np.clip(band,0,255).astype('uint8'),'L')
            sweep=phosphor2(bm,size=size,color='#FFFFFF',glow=0.45,scanlines=False,crt_post=False)
            img.alpha_composite(sweep)
        out.append(img)
    return out



# ===== 120 BPM / 2Hz РИТМ: 6 ударов за 3 секунды при 30fps =====
def _bpm_hit(phase, bpm=120):
    """Возвращает (beat_phase, hit envelope). 120 BPM => 2Hz => 6 ударов/3с."""
    bp=(phase*6.0)%1.0
    # короткая атака + спад, как электронный click/boot hit
    hit=math.exp(-bp*7.0) if bp < 0.55 else 0.0
    return bp, hit


def bpm_scale(mask, size, color, n=90, **k):
    """Чистый scale pulse на 120 BPM: нет кривизны, только размер+CRT line."""
    out=[]; base=mask.convert('L').resize((size,size),Image.LANCZOS)
    for i in range(n):
        p=i/n; bp,hit=_bpm_hit(p)
        sc=1.0+0.18*hit
        m=_scale_xy(mask,size,sc,sc)
        img=phosphor2(m,size=size,color=color,glow=0.85+0.45*hit,phase=p)
        # микрорефреш на каждом beat
        if hit>0.25 and _NUMPY:
            y=np.arange(size)[:,None]; edge=bp*size*1.8
            a=np.asarray(base).astype(np.float32)
            band=np.exp(-((y-edge)**2)/(2*2.0**2))*a*hit
            bm=Image.fromarray(np.clip(band,0,255).astype('uint8'),'L')
            sweep=phosphor2(bm,size=size,color='#FFFFFF',glow=0.35,scanlines=False,crt_post=False)
            img.alpha_composite(sweep)
        out.append(img)
    return out


def bpm_jump(mask, size, color, n=90, **k):
    """Прыжок на 120 BPM: подскок вверх + squash на приземлении. Чёткий, не пьяный."""
    out=[]
    for i in range(n):
        p=i/n; bp,hit=_bpm_hit(p)
        up=math.sin(math.pi*min(1,bp/0.62)) if bp<0.62 else 0.0
        land=hit
        sx=1.0+0.10*land-0.05*up
        sy=1.0-0.08*land+0.08*up
        m=_scale_xy(mask,size,sx,sy)
        m=_shift(m,0,-size*0.10*up)
        out.append(phosphor2(m,size=size,color=color,glow=0.9+0.25*hit,phase=p))
    return out


def bpm_refresh(mask, size, color, n=90, **k):
    """6 refresh-ударов/луп: форма стабильна, каждый beat проходит яркая CRT-строка."""
    out=[]; base=mask.convert('L').resize((size,size),Image.LANCZOS)
    for i in range(n):
        p=i/n; bp,hit=_bpm_hit(p)
        img=phosphor2(mask,size=size,color=color,glow=0.9+0.35*hit,phase=p)
        if _NUMPY:
            y=np.arange(size)[:,None]; edge=bp*size
            a=np.asarray(base).astype(np.float32)
            band=np.exp(-((y-edge)**2)/(2*2.5**2))*a*(0.25+hit)
            bm=Image.fromarray(np.clip(band,0,255).astype('uint8'),'L')
            sweep=phosphor2(bm,size=size,color='#FFFFFF',glow=0.45,scanlines=False,crt_post=False)
            img.alpha_composite(sweep)
        out.append(img)
    return out



# ===== REQUEST-SPECIFIC EFFECTS =====
def power_on(mask, size, color, n=90, **k):
    """ON-включение: точка/линия -> быстрое раскрытие -> яркий CRT hit -> стабильное ON."""
    out=[]
    for i in range(n):
        p=i/n
        if p < 0.12:
            u=easing.BRAND(p/0.12); sx=0.18+0.82*u; sy=0.08+0.92*u
        elif p < 0.22:
            u=easing.BRAND((p-0.12)/0.10); sx=1.12-0.12*u; sy=1.04-0.04*u
        else:
            bp,hit=_bpm_hit(p); sx=1.0+0.035*hit; sy=1.0
        m=_scale_xy(mask,size,sx,sy)
        img=phosphor2(m,size=size,color=color,glow=0.9+0.35*(p<0.22),phase=p)
        out.append(img)
    return out


def diagonal_fly(mask, size, color, n=90, **k):
    """Ракета улетает по диагонали: bottom-left -> top-right, с afterimage trail."""
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    out=[]
    prev=[]
    for i in range(n):
        p=i/n
        # 0..0.70 летит, 0.70..1 reset/hold offscreen -> loop
        u=easing.BRAND(min(1,p/0.70)) if p<0.70 else 1.0
        x=int(-18 + 48*u); y=int(18 - 52*u)
        sc=0.78+0.22*u
        w=max(1,int(size*sc)); h=max(1,int(size*sc))
        r=base.resize((w,h),Image.LANCZOS)
        m=Image.new('L',(size,size),0); m.paste(r,((size-w)//2+x,(size-h)//2+y))
        # короткий trail из предыдущих 3 масок
        comp=m
        if _NUMPY and prev:
            arr=np.asarray(m).astype(np.float32)
            for j,pm in enumerate(prev[-3:]):
                arr=np.maximum(arr, np.asarray(pm).astype(np.float32)*(0.22+0.16*j))
            comp=Image.fromarray(np.clip(arr,0,255).astype('uint8'),'L')
        prev.append(m)
        out.append(phosphor2(comp,size=size,color=color,glow=0.95+0.25*(p<0.70),phase=p))
    return out


def left_reveal(mask, size, color, n=90, **k):
    """Появление слева-направо (signal bars): reveal -> hold -> clear -> repeat."""
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    out=[]
    for i in range(n):
        p=i/n
        if p < 0.42:
            u=easing.BRAND(p/0.42); cut=int(size*u)
        elif p < 0.78:
            cut=size
        else:
            u=easing.BRAND((p-0.78)/0.22); cut=int(size*(1-u))
        m=Image.new('L',(size,size),0); m.paste(base.crop((0,0,cut,size)),(0,0))
        out.append(phosphor2(m,size=size,color=color,glow=0.9+0.15*(p<0.42),phase=p))
    return out


def stretch_pulse(mask, size, color, n=90, **k):
    """Строгое растянуть/сжать на 120 BPM: без волны, только геометрия sx/sy."""
    out=[]
    for i in range(n):
        p=i/n; bp,hit=_bpm_hit(p)
        sx=1.0+0.13*hit; sy=1.0-0.10*hit
        m=_scale_xy(mask,size,sx,sy)
        out.append(phosphor2(m,size=size,color=color,glow=0.9+0.30*hit,phase=p))
    return out



def download_drop(mask, size, color, n=90, **k):
    """Чистая геометрическая загрузка: стрелка падает вниз, бьёт в линию, вспышка.
    Без AI-морфа, поэтому не кривая."""
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    out=[]
    for i in range(n):
        p=i/n
        if p < 0.45:
            u=easing.BRAND(p/0.45); dy=int(size*(0.18*(1-u)))
        elif p < 0.58:
            u=easing.BRAND((p-0.45)/0.13); dy=int(size*(0.02*math.sin(math.pi*u)))
        elif p < 0.78:
            dy=0
        else:
            u=easing.BRAND((p-0.78)/0.22); dy=int(size*(0.18*u))
        m=Image.new('L',(size,size),0); m.paste(base,(0,dy))
        img=phosphor2(m,size=size,color=color,glow=0.9+0.35*(0.42<p<0.60),phase=p)
        # hit-line в момент приземления
        if 0.42 < p < 0.60 and _NUMPY:
            a=np.zeros((size,size),dtype=np.float32)
            y=int(size*0.82); a[max(0,y-2):min(size,y+2), int(size*0.22):int(size*0.78)] = 255
            bm=Image.fromarray(a.astype('uint8'),'L')
            sweep=phosphor2(bm,size=size,color='#FFFFFF',glow=0.5,scanlines=False,crt_post=False)
            img.alpha_composite(sweep)
        out.append(img)
    return out



# ===== TARGETED FIXES =====
def vertical_wrap(mask, size, color, n=90, **k):
    """Объект уползает вниз и вылезает сверху (wrap-scroll), как DOS screen scroll."""
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    out=[]
    for i in range(n):
        p=i/n
        y=int(size * p)
        m=Image.new('L',(size,size),0)
        m.paste(base,(0,y))
        m.paste(base,(0,y-size))
        out.append(phosphor2(m,size=size,color=color,glow=0.92,phase=p))
    return out


def rotate_reverse(mask, size, color, n=90, **k):
    """Обратное вращение (если стандартный rotate крутит не туда)."""
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    out=[]
    for i in range(n):
        p=i/n
        m=base.rotate(-360*p, resample=Image.BICUBIC, fillcolor=0)
        out.append(phosphor2(m,size=size,color=color,glow=0.95,phase=p))
    return out


def shrink_loop(mask, size, color, n=90, min_s=0.46, **k):
    """Уменьшение: крупный -> маленький -> резкий CRT-pop назад."""
    out=[]
    for i in range(n):
        p=i/n
        if p < 0.68:
            u=easing.BRAND(p/0.68); sc=1.0-(1.0-min_s)*u
        elif p < 0.82:
            sc=min_s
        else:
            u=easing.SNAP((p-0.82)/0.18); sc=min_s+(1.0-min_s)*u
        m=_scale_xy(mask,size,sc,sc)
        out.append(phosphor2(m,size=size,color=color,glow=0.85+0.18*(1-sc),phase=p))
    return out



def helix_bottom_bpm(mask, size, color, n=90, **k):
    """Helix: на каждом BPM-ударе нижняя часть растягивается к нижнему левому и
    нижнему правому углу, потом возвращается. 120 BPM, без потери ритма."""
    out=[]
    for i in range(n):
        p=i/n; bp,hit=_bpm_hit(p)
        def f(xx,yy,w,h,hit=hit):
            y=yy/(h-1); x=xx/(w-1)
            bottom=np.clip((y-0.35)/0.65,0,1)**1.7
            # растянуть низ от центра к углам: left half -> влево, right half -> вправо
            direction=np.where(x<0.5,-1.0,1.0)
            dx=direction*w*0.46*hit*bottom
            dy=h*0.30*hit*bottom
            return xx-dx, yy-dy
        m=_warp(mask,f)
        out.append(phosphor2(m,size=size,color=color,glow=0.9+0.35*hit,phase=p))
    return out



def dark_jump(mask, size, color, n=90, **k):
    """Выпрыгивает из темноты: чёрный экран -> видимый рост размера с подскоком вверх
    и овершутом -> стабилизация -> уход обратно в темноту (бесшовно)."""
    out=[]
    base=mask.convert('L').resize((size,size),Image.LANCZOS)
    for i in range(n):
        p=i/n
        if p < 0.12:
            sc=0.22; alpha=0.0; yoff=28
        elif p < 0.40:
            u=easing.SNAP((p-0.12)/0.28)
            sc=0.25+0.95*u; alpha=min(1.0,u*1.4); yoff=int(28-36*u)
        elif p < 0.52:
            u=easing.BRAND((p-0.40)/0.12)
            sc=1.20-0.20*u; alpha=1.0; yoff=int(-8+8*u)
        elif p < 0.76:
            bp,hit=_bpm_hit(p); sc=1.0+0.035*hit; alpha=1.0; yoff=0
        else:
            u=easing.BRAND((p-0.76)/0.24)
            sc=1.0-0.78*u; alpha=1.0-u; yoff=int(28*u)
        w=max(1,int(size*sc)); h=max(1,int(size*sc))
        r=base.resize((w,h),Image.LANCZOS).point(lambda v, a=alpha: int(v*a))
        m=Image.new('L',(size,size),0)
        m.paste(r,((size-w)//2,(size-h)//2+yoff))
        out.append(phosphor2(m,size=size,color=color,glow=0.7+0.7*alpha,phase=p))
    return out



def matrix_rain(mask, size, color, n=90, cell=7, **k):
    """Матрица: падающий зелёный код с яркими белыми головами. Если есть маска —
    дождь идёт только внутри силуэта (иконка собрана из падающего кода)."""
    if not _NUMPY:
        return [phosphor2(mask,size=size,color=color,glow=0.9,phase=i/n) for i in range(n)]
    cols=size//cell; rows=size//cell
    rng=np.random.default_rng(1337)
    glyph=(rng.random((rows*2,cols))>0.25).astype(np.float32)   # плотность символов
    speed=rng.integers(1,3,size=cols)                            # cells/loop-step множитель
    offset=rng.integers(0,rows*2,size=cols)
    taillen=rng.integers(4,9,size=cols)
    sil=None
    if mask is not None:
        a=np.asarray(mask.convert('L').resize((size,size),Image.LANCZOS))
        sil=(a>40).astype(np.float32)
    out=[]
    for f in range(n):
        tailL=np.zeros((size,size),np.float32); headL=np.zeros((size,size),np.float32)
        for c in range(cols):
            head=int((offset[c]+ f*speed[c]*(rows*2)/n)) % (rows*2)
            for t in range(taillen[c]):
                rr=(head - t)
                gy=rr % (rows*2)
                if gy>=rows: 
                    continue
                if glyph[rr % (rows*2), c] < 0.5:
                    continue
                y0=gy*cell; x0=c*cell
                val=255*max(0.0,(1-t/taillen[c]))
                if t==0:
                    headL[y0:y0+cell-1, x0:x0+cell-1]=255
                else:
                    tailL[y0:y0+cell-1, x0:x0+cell-1]=val
        tL=Image.fromarray(tailL.astype('uint8'),'L')
        hL=Image.fromarray(headL.astype('uint8'),'L')
        if sil is not None:
            tL=Image.fromarray((tailL*sil).astype('uint8'),'L')
            hL=Image.fromarray((headL*sil).astype('uint8'),'L')
        tail=phosphor2(tL,size=size,color=color,glow=0.8,scanlines=True,phase=f/n)
        head=phosphor2(hL,size=size,color='#D8FFE2',glow=0.5,scanlines=False,crt_post=False)
        tail.alpha_composite(head)
        out.append(tail)
    return out



def warn_bpm(mask, size, color, n=90, **k):
    """120 BPM пульс + перелив цвета зелёный->жёлтый->красный (тревога)."""
    pal=["#00DE52","#FFD400","#FF2A2A"]
    out=[]
    for i in range(n):
        p=i/n; bp,hit=_bpm_hit(p)
        f=p*len(pal); ai=int(f)%len(pal); bi=(ai+1)%len(pal)
        c=_lerp_hex(pal[ai],pal[bi],f-int(f))
        sc=1.0+0.12*hit
        m=_scale_xy(mask,size,sc,sc)
        out.append(phosphor2(m,size=size,color=c,glow=0.9+0.45*hit,phase=p))
    return out



def hacker_rain(mask, size, color, n=90, **k):
    """Хакер остаётся видимым + код-дождь во весь кадр позади (приглушённый)."""
    full = Image.new('L', (size, size), 255)
    rain = matrix_rain(full, size, color, n=n)
    out=[]
    for i in range(n):
        bg = rain[i].copy()
        bg.putalpha(bg.getchannel('A').point(lambda x: int(x*0.5)))
        icon = phosphor2(mask, size=size, color=color, glow=0.98, phase=i/n)
        bg.alpha_composite(icon)
        out.append(bg)
    return out



def _mushroom_base(size):
    from PIL import ImageDraw as _ID
    cx=size/2
    cap=Image.new('L',(size,size),0); dc=_ID.Draw(cap)
    dc.pieslice([cx-size*0.40, size*0.16, cx+size*0.40, size*0.70], 180, 360, fill=255)
    dc.rectangle([cx-size*0.40, size*0.42, cx+size*0.40, size*0.50], fill=255)
    stem=Image.new('L',(size,size),0); ds=_ID.Draw(stem)
    ds.rounded_rectangle([cx-size*0.22, size*0.48, cx+size*0.22, size*0.85], radius=int(size*0.06), fill=255)
    ds.ellipse([cx-size*0.14, size*0.58, cx-size*0.05, size*0.74], fill=0)
    ds.ellipse([cx+size*0.05, size*0.58, cx+size*0.14, size*0.74], fill=0)
    spots=Image.new('L',(size,size),0); dp=_ID.Draw(spots)
    dp.ellipse([cx-size*0.06, size*0.22, cx+size*0.06, size*0.34], fill=255)
    dp.ellipse([cx-size*0.31, size*0.32, cx-size*0.20, size*0.43], fill=255)
    dp.ellipse([cx+size*0.20, size*0.32, cx+size*0.31, size*0.43], fill=255)
    capR=phosphor2(cap,size=size,color='#00DE52',glow=0.9,crt_post=False)
    spotR=phosphor2(spots,size=size,color='#FFFFFF',glow=0.5,crt_post=False,scanlines=False)
    stemR=phosphor2(stem,size=size,color='#00DE52',glow=0.8,crt_post=False)
    base=Image.new('RGBA',(size,size),(0,0,0,0))
    base.alpha_composite(capR); base.alpha_composite(spotR); base.alpha_composite(stemR)
    return base


def mushroom_anim(mask, size, color, n=90, **k):
    """Цветной гриб (Mario power-up): прыгает на 120 BPM."""
    base=_mushroom_base(size)
    out=[]
    for i in range(n):
        p=i/n; bp,hit=_bpm_hit(p)
        up=math.sin(math.pi*min(1,bp/0.6)) if bp<0.6 else 0.0
        sx=1.0+0.06*hit-0.04*up; sy=1.0-0.06*hit+0.08*up
        w=max(1,int(size*sx)); h=max(1,int(size*sy))
        r=base.resize((w,h),Image.LANCZOS)
        f=Image.new('RGBA',(size,size),(0,0,0,0))
        f.alpha_composite(r, ((size-w)//2, (size-h)//2 - int(size*0.10*up)))
        out.append(f)
    return out


EFFECTS2 = {
    "ember_breath": ember_breath,
    "spin3d": spin3d,
    "shock_ring": shock_ring,
    "impulse": impulse,
    "glitch_crt": glitch_crt,
    "color_cycle2": color_cycle2,
    "beat": beat,
    "bounce": bounce,
    "assemble": assemble,
    "sequence": sequence,
    "power_off": power_off,
    "rocket_launch": rocket_launch,
    "jelly": jelly,
    "wave": wave,
    "sway": sway,
    "pump": pump,
    "twist": twist,
    "blink_warp": blink_warp,
    "shake_warp": shake_warp,
    "corner_pin": corner_pin,
    "keystone": keystone,
    "hsync_tear": hsync_tear,
    "crt_refresh": crt_refresh,
    "projective_pin": projective_pin,
    "signal_pull": signal_pull,
    "snap_zoom": snap_zoom,
    "platform_pop": platform_pop,
    "anchor_scale": anchor_scale,
    "platform_scale": platform_scale,
    "bpm_scale": bpm_scale,
    "bpm_jump": bpm_jump,
    "bpm_refresh": bpm_refresh,
    "power_on": power_on,
    "diagonal_fly": diagonal_fly,
    "left_reveal": left_reveal,
    "stretch_pulse": stretch_pulse,
    "download_drop": download_drop,
    "vertical_wrap": vertical_wrap,
    "rotate_reverse": rotate_reverse,
    "shrink_loop": shrink_loop,
    "helix_bottom_bpm": helix_bottom_bpm,
}


if __name__ == "__main__":
    from PIL import ImageDraw
    size = 100
    m = Image.new("L", (512, 512), 0)
    ImageDraw.Draw(m).ellipse([150, 150, 362, 362], fill=255)
    for name, fn in EFFECTS2.items():
        frames = fn(m, size, "#00DE52", n=20)
        f0, fl = frames[0], frames[-1]
        assert all(f.size == (size, size) and f.mode == "RGBA" for f in frames)
        print("%-12s OK  frames=%d  size=%s  numpy=%s"
              % (name, len(frames), f0.size, _NUMPY))

EFFECTS2["dark_jump"] = dark_jump

EFFECTS2["matrix_rain"] = matrix_rain

EFFECTS2["warn_bpm"] = warn_bpm

EFFECTS2["hacker_rain"] = hacker_rain

EFFECTS2["mushroom_anim"] = mushroom_anim
