"""Фосфорный CRT пост-процесс: монохромная маска -> неоновый светящийся RGBA-кадр.

Рецепт выжат из dropweb-app/lib/common/lumina.dart и dropweb_gen.py:
  фон #030305, неон #22C55E (ядро) / #15803D (глубина), слоёный gaussian-глоу,
  сканлайны только по светящимся областям. По умолчанию вывод прозрачный, чтобы
  эмодзи чисто ложилось на любой фон чата; CRT-ощущение даёт само свечение.
"""
from PIL import Image, ImageFilter, ImageDraw, ImageChops

VOID = (3, 3, 5)  # #030305


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def phosphor(mask, size=100, color="#22C55E", glow=1.0,
             scanlines=True, transparent=True, supersample=4):
    """mask: PIL 'L' (белое = светится). Возвращает RGBA size x size."""
    col = hex_rgb(color)
    ss = size * supersample
    m = mask.convert("L").resize((ss, ss), Image.LANCZOS)

    # светящийся слой: цвет там где маска, прозрачность в остальном
    lit = Image.composite(
        Image.new("RGBA", (ss, ss), (*col, 255)),
        Image.new("RGBA", (ss, ss), (0, 0, 0, 0)),
        m,
    )

    # глоу: слоёный gaussian-blur формы
    r = max(2, int(ss * 0.045 * glow))
    glow_src = Image.composite(
        Image.new("RGBA", (ss, ss), (*col, 170)),
        Image.new("RGBA", (ss, ss), (0, 0, 0, 0)),
        m,
    )
    g1 = glow_src.filter(ImageFilter.GaussianBlur(r))
    g2 = glow_src.filter(ImageFilter.GaussianBlur(max(1, r // 4)))

    canvas = Image.new("RGBA", (ss, ss),
                       (0, 0, 0, 0) if transparent else (*VOID, 255))
    canvas.alpha_composite(g1)
    canvas.alpha_composite(g2)
    canvas.alpha_composite(lit)

    if scanlines:
        sl = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(sl)
        step = max(2, supersample * 2)
        for y in range(0, ss, step):
            d.line([(0, y), (ss, y)], fill=(0, 0, 0, 75), width=1)
        # затемнение сканлайнами только по светящимся зонам (через альфу канваса)
        sl.putalpha(ImageChops.multiply(sl.getchannel("A"),
                                        canvas.getchannel("A")))
        canvas.alpha_composite(sl)

    return canvas.resize((size, size), Image.LANCZOS)
