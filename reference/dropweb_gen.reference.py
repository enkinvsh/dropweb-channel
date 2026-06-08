#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1920
OUT = "/Users/oen/Documents/projects/dropweb-ad.png"
FD = "/Users/oen/Documents/projects/dropweb-fonts"

BG = (8, 8, 8)
NEON = (57, 255, 20)
TXT = (226, 226, 226)
MUTED = (85, 85, 85)
PAD = 72


def fnt(face, size, weight=400):
    path = (
        f"{FD}/Unbounded-variable.ttf" if face == "ub" else f"{FD}/Onest-variable.ttf"
    )
    f = ImageFont.truetype(path, size)
    f.set_variation_by_axes([weight])
    return f


def tw(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def th(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[3] - b[1]


def fit(draw, text, face, size, weight, max_w):
    f = fnt(face, size, weight)
    w = tw(draw, text, f)
    if w <= max_w:
        return f
    return fnt(face, max(16, int(size * max_w / w * 0.91)), weight)


def xctr(draw, text, font):
    return (W - tw(draw, text, font)) // 2


def glow(img, draw, text, x, y, font, color, radius=18):
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    gd.text((x, y), text, font=font, fill=(*color, 165))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(radius=radius)))
    img.alpha_composite(g.filter(ImageFilter.GaussianBlur(radius=max(2, radius // 4))))
    draw.text((x, y), text, font=font, fill=(*color, 255))


def sep(draw, y, alpha=44):
    draw.line([(PAD, y), (W - PAD, y)], fill=(*NEON, alpha), width=1)


def card_box(img, draw, y1, y2, radius=14):
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gld = ImageDraw.Draw(gl)
    gld.rounded_rectangle(
        [PAD - 6, y1 - 6, W - PAD + 6, y2 + 6],
        radius=radius + 6,
        outline=(*NEON, 18),
        width=12,
    )
    img.alpha_composite(gl.filter(ImageFilter.GaussianBlur(radius=14)))
    draw.rounded_rectangle(
        [PAD, y1, W - PAD, y2],
        radius=radius,
        fill=(*NEON, 7),
        outline=(*NEON, 68),
        width=1,
    )


def clover_icon(img, draw, cx_pos, cy_pos, r=32):
    d = int(r * 0.58)
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    for dx, dy in [(0, -d), (d, 0), (0, d), (-d, 0)]:
        gd.ellipse(
            [cx_pos + dx - r, cy_pos + dy - r, cx_pos + dx + r, cy_pos + dy + r],
            fill=(*NEON, 120),
        )
    img.alpha_composite(glow_layer.filter(ImageFilter.GaussianBlur(radius=14)))
    for dx, dy in [(0, -d), (d, 0), (0, d), (-d, 0)]:
        draw.ellipse(
            [cx_pos + dx - r, cy_pos + dy - r, cx_pos + dx + r, cy_pos + dy + r],
            fill=(*NEON, 240),
        )
    draw.rounded_rectangle(
        [cx_pos - 3, cy_pos + d + r - 6, cx_pos + 3, cy_pos + d + r + 10],
        radius=3,
        fill=(*NEON, 200),
    )


def draw_card_section(img, draw, lines, y_start, pad_top=28, pad_bot=24, gap=18):
    max_w = W - PAD * 2 - 48
    rendered = []
    for text, face, size, weight, color, do_glow in lines:
        f = fit(draw, text, face, size, weight, max_w)
        h = th(draw, text, f)
        rendered.append((text, f, color, do_glow, h))

    total_inner = sum(r[4] for r in rendered) + gap * (len(rendered) - 1)
    card_h = pad_top + total_inner + pad_bot

    card_box(img, draw, y_start, y_start + card_h)

    y = y_start + pad_top
    for text, f, color, do_glow, h in rendered:
        x = xctr(draw, text, f)
        if do_glow:
            glow(img, draw, text, x, y, f, color, radius=20 if color == NEON else 8)
        else:
            draw.text((x, y), text, font=f, fill=(*color, 255))
        y += h + gap

    return y_start + card_h


def main():
    img = Image.new("RGBA", (W, H), (*BG, 255))
    draw = ImageDraw.Draw(img)

    for sy in range(0, H, 4):
        draw.line([(0, sy), (W, sy)], fill=(255, 255, 255, 6))

    for gx in range(36, W, 54):
        for gy in range(36, H, 54):
            draw.point((gx, gy), fill=(*NEON, 10))

    draw.rectangle([6, 6, W - 7, H - 7], outline=(*NEON, 28), width=1)

    f_or30 = fnt("on", 30, 400)
    y = 95

    dw_text = "dropweb"
    f_dw = fnt("ub", 80, 900)
    dw_w = tw(draw, dw_text, f_dw)
    clov_r = 36
    clov_gap = 26
    row_w = clov_r * 2 + clov_gap + dw_w
    sx = (W - row_w) // 2
    clover_icon(img, draw, sx + clov_r, y + 48, r=clov_r)
    glow(img, draw, dw_text, sx + clov_r * 2 + clov_gap, y + 8, f_dw, NEON, radius=30)
    y += 108

    s1 = "— VPN для нейросетей"
    f_s1 = fit(draw, s1, "ub", 40, 600, W - PAD * 2)
    glow(img, draw, s1, xctr(draw, s1, f_s1), y, f_s1, NEON, radius=14)
    y += th(draw, s1, f_s1) + 18

    s2 = "...и не только"
    f_s2 = fnt("on", 42, 600)
    glow(img, draw, s2, xctr(draw, s2, f_s2), y, f_s2, NEON, radius=10)
    y += th(draw, s2, f_s2) + 62

    sep(draw, y)
    y += 58

    c1_end = draw_card_section(
        img,
        draw,
        [
            ("Claude · ChatGPT · Gemini", "on", 40, 400, TXT, False),
            ("Antigravity · Midjourney · Suno", "on", 40, 400, TXT, False),
            ("Runway · Opencode — работает", "on", 44, 700, NEON, True),
        ],
        y,
        pad_top=30,
        pad_bot=26,
        gap=20,
    )
    y = c1_end

    sep(draw, y + 3)
    y += 58

    c2_end = draw_card_section(
        img,
        draw,
        [
            ("Девственно чистые IP", "on", 52, 700, NEON, True),
            ("для Вайбкодинга", "on", 52, 700, NEON, True),
            ("opencode · oh-my-openagent · claude code", "on", 34, 400, MUTED, False),
            ("cursor · windsurf · cline", "on", 34, 400, MUTED, False),
        ],
        y,
        pad_top=30,
        pad_bot=26,
        gap=14,
    )
    y = c2_end

    sep(draw, y + 3)
    y += 58

    c3_end = draw_card_section(
        img,
        draw,
        [
            ("YouTube без рекламы. Discord и Telegram", "on", 40, 400, TXT, False),
            ("Каскад через RU | CDN | Selfsteal", "on", 40, 400, TXT, False),
            ("+ идет тест Hysteria2 (только для Happ)", "on", 34, 400, MUTED, False),
        ],
        y,
        pad_top=30,
        pad_bot=26,
        gap=18,
    )
    y = c3_end

    sep(draw, y + 3)
    y += 58

    c4_end = draw_card_section(
        img,
        draw,
        [
            ("Автообновление подписки!", "on", 48, 700, NEON, True),
            ("Никаких vless:// и прочего", "on", 40, 400, TXT, False),
        ],
        y,
        pad_top=30,
        pad_bot=26,
        gap=18,
    )
    y = c4_end

    sep(draw, y + 3)
    y += 78

    price_text = "от 150₽/мес"
    f_price = fit(draw, price_text, "ub", 94, 900, W - PAD * 2)
    px = xctr(draw, price_text, f_price)
    g_p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd_p = ImageDraw.Draw(g_p)
    gd_p.text((px, y), price_text, font=f_price, fill=(*NEON, 145))
    img.alpha_composite(g_p.filter(ImageFilter.GaussianBlur(radius=45)))
    img.alpha_composite(g_p.filter(ImageFilter.GaussianBlur(radius=16)))
    img.alpha_composite(g_p.filter(ImageFilter.GaussianBlur(radius=5)))
    draw.text((px, y), price_text, font=f_price, fill=(*NEON, 255))
    y += th(draw, price_text, f_price) + 32

    free_text = "3 дня бесплатно"
    f_free = fnt("on", 44, 600)
    glow(img, draw, free_text, xctr(draw, free_text, f_free), y, f_free, TXT, radius=7)
    y += th(draw, free_text, f_free) + 72

    sep(draw, y)
    y += 55

    for ft in ["dropweb.org", "@dropwebpay_bot"]:
        draw.text((xctr(draw, ft, f_or30), y), ft, font=f_or30, fill=(*MUTED, 255))
        y += th(draw, ft, f_or30) + 16

    print(f"Final y: {y} / {H}  (free: {H - y}px)")
    img.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
