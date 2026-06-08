"""CRT motion library. Each effect returns a list of RGBA frames (seamless loop).

Motion echoes the app signature (Cubic(0.2,0.8,0.2,1.0)/400ms feel) via smooth
sine envelopes. All effects accept (mask, size, color, **kw) and ignore extras.
"""
import math
import random

from PIL import Image, ImageChops, ImageDraw

from .phosphor2 import phosphor2 as phosphor, hex_rgb


def lerp_hex(a, b, t):
    ca, cb = hex_rgb(a), hex_rgb(b)
    return "#%02X%02X%02X" % tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))


def breath(mask, size, color, n=40, **k):
    out = []
    for i in range(n):
        t = i / n
        g = 0.8 + 0.30 * 0.5 * (1 + math.sin(2 * math.pi * t))
        out.append(phosphor(mask, size=size, color=color, glow=g))
    return out


def pulse_scan(mask, size, color, n=90, **k):
    out = []
    gm = mask.convert("L").resize((size, size))
    for i in range(n):
        t = i / n
        g = 0.8 + 0.35 * 0.5 * (1 + math.sin(2 * math.pi * t))
        canvas = phosphor(mask, size=size, color=color, glow=g)
        band = Image.new("L", (size, size), 0)
        d = ImageDraw.Draw(band)
        y = int(t * size)
        d.rectangle([0, y, size, y + max(2, int(size * 0.12))], fill=255)
        band = ImageChops.multiply(band, gm)
        sweep = phosphor(band, size=size, color="#FFFFFF", glow=0.5, scanlines=False)
        sweep.putalpha(sweep.getchannel("A").point(lambda a: int(a * 0.5)))
        canvas.alpha_composite(sweep)
        out.append(canvas)
    return out


def scan_fragment(mask, size, color, n=40, **k):
    return pulse_scan(mask, size, color, n=n)  # v1: sweep stands in for SNI split


def cursor_blink(mask, size, color, n=40, **k):
    out = []
    for i in range(n):
        canvas = phosphor(mask, size=size, color=color, glow=0.95)
        if (i // max(1, n // 4)) % 2 == 0:
            cm = Image.new("L", (size, size), 0)
            d = ImageDraw.Draw(cm)
            cw = int(size * 0.14)
            x0 = size - cw - int(size * 0.06)
            d.rectangle([x0, int(size * 0.40), x0 + cw, int(size * 0.62)], fill=255)
            cur = phosphor(cm, size=size, color=color, glow=0.85, scanlines=False)
            canvas.alpha_composite(cur)
        out.append(canvas)
    return out


def ring(mask, size, color, n=45, **k):
    out = []
    for i in range(n):
        t = i / n
        canvas = phosphor(mask, size=size, color=color, glow=0.95)
        rm = Image.new("L", (size, size), 0)
        d = ImageDraw.Draw(rm)
        rad = int((0.18 + 0.32 * t) * size)
        w = max(1, int(size * 0.05 * (1 - t)))
        d.ellipse([size / 2 - rad, size / 2 - rad, size / 2 + rad, size / 2 + rad],
                  outline=255, width=w)
        rl = phosphor(rm, size=size, color=color, glow=0.55, scanlines=False)
        rl.putalpha(rl.getchannel("A").point(lambda a: int(a * (1 - t))))
        canvas.alpha_composite(rl)
        out.append(canvas)
    return out


def crt_boot(mask, size, color, n=45, **k):
    out = []
    for i in range(n):
        t = i / n
        ramp = min(1.0, t * 2.2)
        flick = 1.0 if random.random() > 0.12 else 0.45
        out.append(phosphor(mask, size=size, color=color, glow=0.4 + 0.9 * ramp * flick))
    return out


def color_cycle(mask, size, color, n=60, palette=None, **k):
    palette = palette or ["#22C55E", "#38BDF8", "#A78BFA", "#EF4444", "#F59E0B", "#64748B"]
    out = []
    seg = max(1, n // len(palette))
    for i in range(n):
        f = i / seg
        a = int(f) % len(palette)
        b = (a + 1) % len(palette)
        out.append(phosphor(mask, size=size, color=lerp_hex(palette[a], palette[b], f - int(f)), glow=1.0))
    return out


def spin(mask, size, color, n=40, **k):
    """Псевдо-3D вращение: ширина по |cos| с полом 0.30, задняя грань зеркалится,
    яркость проседает на ребре — читается как поворот, а не схлопывание."""
    out = []
    base = mask.convert("L").resize((size, size))
    for i in range(n):
        c = math.cos(2 * math.pi * (i / n))
        w = max(int(size * 0.30), int(size * abs(c)))
        src = base if c >= 0 else base.transpose(Image.FLIP_LEFT_RIGHT)
        m2 = Image.new("L", (size, size), 0)
        m2.paste(src.resize((w, size)), ((size - w) // 2, 0))
        out.append(phosphor(m2, size=size, color=color, glow=0.6 + 0.4 * abs(c)))
    return out


def bars_fill(mask, size, color, n=40, **k):
    out = []
    base = mask.convert("L").resize((size, size))
    hold = n // 4
    for i in range(n):
        t = 1.0 if i >= n - hold else i / max(1, n - hold)
        rm = Image.new("L", (size, size), 0)
        cut = max(1, int(t * size))
        rm.paste(base.crop((0, 0, cut, size)), (0, 0))
        out.append(phosphor(rm, size=size, color=color, glow=1.0))
    return out


def twinkle(mask, size, color, n=36, **k):
    out = []
    for i in range(n):
        g = 0.7 + 0.6 * abs(math.sin(2 * math.pi * (i / n)))
        out.append(phosphor(mask, size=size, color=color, glow=g))
    return out


EFFECTS = {
    "breath": breath, "pulse_scan": pulse_scan, "scan_fragment": scan_fragment,
    "cursor_blink": cursor_blink, "ring": ring, "crt_boot": crt_boot,
    "color_cycle": color_cycle, "spin": spin, "bars_fill": bars_fill, "twinkle": twinkle,
}


# --- доп. эффекты для набора v2 (32) ---

def rotate(mask, size, color, n=90, **k):
    """Честное вращение на 360° (рефреш/update)."""
    base = mask.convert("L").resize((size, size))
    out = []
    for i in range(n):
        m2 = base.rotate(360 * i / n, resample=Image.BICUBIC, fillcolor=0)
        out.append(phosphor(m2, size=size, color=color, glow=0.95))
    return out


def glitch(mask, size, color, n=40, **k):
    """Цифровой глитч: случайный сдвиг горизонтальных срезов (хакер)."""
    base = mask.convert("L").resize((size, size))
    out = []
    for _ in range(n):
        m2 = base.copy()
        if random.random() < 0.6:
            for _ in range(random.randint(1, 3)):
                y = random.randint(0, size - 2)
                h = random.randint(2, 9)
                dx = random.randint(-9, 9)
                sl = base.crop((0, y, size, min(size, y + h)))
                m2.paste(0, (0, y, size, min(size, y + h)))
                m2.paste(sl, (dx, y))
        out.append(phosphor(m2, size=size, color=color, glow=0.9))
    return out


def shake(mask, size, color, n=24, **k):
    """Тряска + лёгкий наклон (ahah/смех)."""
    base = mask.convert("L").resize((size, size))
    out = []
    for i in range(n):
        t = i / n
        dx = int(size * 0.045 * math.sin(2 * math.pi * t * 2))
        ang = 5 * math.sin(2 * math.pi * t * 2)
        m2 = Image.new("L", (size, size), 0)
        m2.paste(base.rotate(ang, resample=Image.BICUBIC, fillcolor=0), (dx, 0))
        out.append(phosphor(m2, size=size, color=color, glow=0.95))
    return out


def flicker(mask, size, color, n=30, **k):
    """Хаотичное мерцание яркости (огонь)."""
    out = []
    for _ in range(n):
        out.append(phosphor(mask, size=size, color=color, glow=0.7 + random.random() * 0.6))
    return out


def blink(mask, size, color, n=40, **k):
    """Долго горит, коротко гаснет (глаза/моргание)."""
    out = []
    for i in range(n):
        g = 0.12 if (n - 4) <= i < (n - 1) else 1.0
        out.append(phosphor(mask, size=size, color=color, glow=g))
    return out


def strobe(mask, size, color, n=24, **k):
    """Резкий пульс-тревога (warning)."""
    out = []
    for i in range(n):
        g = 1.25 if (i // 3) % 2 == 0 else 0.5
        out.append(phosphor(mask, size=size, color=color, glow=g))
    return out


def rise(mask, size, color, n=30, **k):
    """Покачивание вверх-вниз + дыхание (rocket/запуск)."""
    base = mask.convert("L").resize((size, size))
    out = []
    for i in range(n):
        t = i / n
        dy = int(size * 0.05 * math.sin(2 * math.pi * t))
        m2 = Image.new("L", (size, size), 0)
        m2.paste(base, (0, -dy))
        out.append(phosphor(m2, size=size, color=color, glow=0.85 + 0.25 * abs(math.sin(2 * math.pi * t))))
    return out


EFFECTS.update({
    "rotate": rotate, "glitch": glitch, "shake": shake, "flicker": flicker,
    "blink": blink, "strobe": strobe, "rise": rise,
})

# --- премиум-движок (numpy bloom/CRT/частицы) ---
from .animate2 import EFFECTS2  # noqa: E402
EFFECTS.update(EFFECTS2)
