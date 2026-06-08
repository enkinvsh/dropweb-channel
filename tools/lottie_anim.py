"""Центр-512-SVG -> анимированный .tgs, 120 BPM (60fps, бит=30 кадров), overshoot, бесшовный цикл.
Фикс цикла: in/out на всех слоях. Хиты на битах, snappy через overshoot в значениях."""
from lottie.parsers.svg import parse_svg_file
from lottie.exporters.core import export_tgs
from lottie.objects import easing
from lottie import objects, Point

EO = easing.EaseOut; EI = easing.EaseIn; S = easing.Sigmoid; LIN = easing.Linear
FPS = 60; BEAT = 30  # 120 BPM

def _loops(kind):
    return {"spin": 60, "blink": 60, "swing": 60}.get(kind, 30)

def build_tgs(svg, tgs, kind="beat", fps=FPS):
    an = parse_svg_file(svg)
    n = _loops(kind)
    an.frame_rate = fps; an.in_point = 0; an.out_point = n
    base = objects.NullLayer(); base.index = 9000
    base.in_point = 0; base.out_point = n
    base.transform.anchor_point.value = Point(256, 256)
    base.transform.position.value = Point(256, 256)
    for layer in list(an.layers):
        layer.parent_index = 9000
        layer.in_point = 0; layer.out_point = n
    an.add_layer(base)
    t = base.transform; sc = t.scale; ro = t.rotation; op = t.opacity; po = t.position
    def P(x, y): return Point(x, y)

    if kind == "beat":            # снап-пульс на бит + overshoot
        for f, v, e in [(0,100,EO),(5,116,EI),(12,96,S),(20,101,S),(30,100,None)]:
            sc.add_keyframe(f, P(v, v), e() if e else None)
    elif kind == "heartbeat":     # lub-dub за один бит
        for f, v, e in [(0,100,EO),(3,122,EI),(7,100,EO),(11,114,EI),(16,99,S),(30,100,None)]:
            sc.add_keyframe(f, P(v, v), e() if e else None)
    elif kind == "twinkle":       # вспышка+поворот на бит
        for f, v, e in [(0,100,EO),(6,124,EO),(16,100,EO),(30,100,None)]:
            sc.add_keyframe(f, P(v, v), e() if e else None)
        for f, v in [(0,0),(15,22),(30,0)]: ro.add_keyframe(f, v, S())
    elif kind == "spin":          # 360 за 2 бита, плавно
        ro.add_keyframe(0, 0, LIN()); ro.add_keyframe(60, 360, LIN())
    elif kind == "ring":          # звон-затухание на бит
        for f, v in [(0,0),(3,17,),(9,-13),(15,9),(21,-5),(26,2),(30,0)]:
            ro.add_keyframe(f, v, EO())
    elif kind == "blink":         # моргание раз в 2 бита
        for f, v, e in [(0,100,S),(46,100,S),(50,10,EO),(55,100,EO),(60,100,None)]:
            sc.add_keyframe(f, P(100, v), e() if e else None)
    elif kind == "swing":         # маятник за 2 бита
        for f, v in [(0,0),(15,11),(30,0),(45,-11),(60,0)]: ro.add_keyframe(f, v, S())
    elif kind == "bounce":        # прыжок на бит + squash
        for f, v, e in [(0,256,EO),(9,222,EI),(17,256,EO),(23,243,EI),(30,256,None)]:
            po.add_keyframe(f, Point(256, v), e() if e else None)
        for f, sx, sy, e in [(0,100,100,S),(15,112,90,EO),(20,98,102,S),(30,100,100,None)]:
            sc.add_keyframe(f, P(sx, sy), e() if e else None)
    elif kind == "flicker":       # дрожь огня
        for f, v in [(0,100),(5,111),(10,95),(15,113),(20,98),(25,106),(30,100)]:
            sc.add_keyframe(f, P(v, v+4), S())
    elif kind == "shake":         # вибрация на бит
        for f, v in [(0,256),(4,248),(9,264),(14,250),(19,262),(24,256),(30,256)]:
            po.add_keyframe(f, Point(v, 256), S())
    else:
        for f, v in [(0,100),(6,113),(16,100),(30,100)]: sc.add_keyframe(f, P(v, v), EO())
    export_tgs(an, tgs)
    return tgs
