"""Per-ELEMENT vector animation engine: multi-path SVG -> animated .tgs (Lottie).

Each inner element Group (one per SVG path) is animated independently
(stagger / sequential / pulse) via keyframable TransformShape. Seamless loops:
value at frame 0 == value at frame n, so Telegram loops cleanly.

120 BPM aesthetic: beat = 30 frames @ 60fps. n=60 = 2 beats. Flat neon, no FX.
Self-test: `.venv/bin/python3 -m tools.tgs_anim`.
"""
import math
import os

from lottie.parsers.svg import parse_svg_file
from lottie.exporters.core import export_tgs
from lottie.objects import easing
from lottie.objects.layers import color_from_hex
from lottie import objects, Point

EO = easing.EaseOut
EI = easing.EaseIn
S = easing.Sigmoid
LIN = easing.Linear
FPS = 60
BEAT = 30  # 120 BPM

# ---- defaults for preset params ------------------------------------------
DEFAULTS = dict(stagger=6, rise=60, spread=80, turn=25, radius=40, lag=5)

# ---- static background (Lumina bento tile) -------------------------------
BG_DEFAULT = {"rx": 80.0, "fill": "#08090C"}


def _add_bg_layer(an, rx, fill, n, size=512):
    """Append a STATIC rounded-rect ShapeLayer at the BOTTOM of an.layers.

    In Lottie the FIRST layer draws on TOP, the LAST draws at the BOTTOM, so
    appending (add_layer) puts this background BEHIND the animated icon. No
    keyframes: a single rounded Rectangle (size x size, centered) filled flat.
    """
    rect = objects.shapes.Rect()
    rect.size.value = [float(size), float(size)]
    rect.position.value = [size / 2.0, size / 2.0]
    rect.rounded.value = float(rx)

    rgba = color_from_hex(fill)
    fill_shape = objects.shapes.Fill(rgba[:3])

    grp = objects.shapes.Group()
    grp.add_shape(rect)
    grp.add_shape(fill_shape)

    layer = objects.layers.ShapeLayer()
    layer.add_shape(grp)
    layer.in_point = 0
    layer.out_point = n

    an.add_layer(layer)
    return layer


def _p(params, key):
    return params.get(key, DEFAULTS[key])


# ---- structure helpers ----------------------------------------------------
def element_groups(an):
    """Return the inner element Groups (one per SVG path).

    Structure: layer.shapes == [outer Group]; outer.shapes ==
    [Group(el0..elN), TransformShape(outer)]. We collect the Group instances
    inside the outer group, excluding the trailing outer TransformShape.
    Robust to a single-path SVG (returns >=1 group).
    """
    groups = []
    for layer in an.layers:
        shapes = getattr(layer, "shapes", None)
        if not shapes:
            continue
        for outer in shapes:
            inner = getattr(outer, "shapes", None)
            if not inner:
                continue
            for s in inner:
                if isinstance(s, objects.Group):
                    groups.append(s)
        if groups:
            break
    if not groups:
        # Fallback: any Group anywhere in the first layer's shapes.
        for layer in an.layers:
            for s in getattr(layer, "shapes", []) or []:
                if isinstance(s, objects.Group):
                    groups.append(s)
            if groups:
                break
    return groups


def _elem_transform(g):
    """Return the element Group's TransformShape."""
    tr = getattr(g, "transform", None)
    if isinstance(tr, objects.TransformShape):
        return tr
    for s in getattr(g, "shapes", []) or []:
        if isinstance(s, objects.TransformShape):
            return s
    return tr


def _center(g):
    """Element bbox center as a Point (in svg path-coordinate space)."""
    bb = g.bounding_box(0)
    c = bb.center()
    return Point(c[0], c[1])


def _pivot(tr, center):
    """Pivot scale/rotation around the element's own center."""
    tr.anchor_point.value = center
    tr.position.value = center


# ---- presets: fn(tr, index, count, n, params, center) ---------------------
def stagger_rise(tr, index, count, n, params, center):
    stagger = _p(params, "stagger")
    rise = _p(params, "rise")
    d = index * stagger
    cx, cy = center[0], center[1]
    tr.anchor_point.value = center
    # position.y: start below + low opacity, rise to place, hold, return by n.
    tr.position.add_keyframe(0, Point(cx, cy + rise), EO())
    tr.position.add_keyframe(min(d + 12, n), Point(cx, cy), EO())
    tr.position.add_keyframe(max(n - 12, d + 13), Point(cx, cy), EI())
    tr.position.add_keyframe(n, Point(cx, cy + rise), EI())
    tr.opacity.add_keyframe(0, 15, EO())
    tr.opacity.add_keyframe(min(d + 12, n), 100, EO())
    tr.opacity.add_keyframe(max(n - 12, d + 13), 100, EI())
    tr.opacity.add_keyframe(n, 15, EI())


def sequential_glow(tr, index, count, n, params, center):
    stagger = _p(params, "stagger")
    d = min(index * stagger, max(n - 14, 1))
    tr.opacity.add_keyframe(0, 25, S())
    tr.opacity.add_keyframe(min(d + 10, n), 100, EO())
    tr.opacity.add_keyframe(max(n - 10, d + 11), 100, EI())
    tr.opacity.add_keyframe(n, 25, S())


def pulse_offset(tr, index, count, n, params, center):
    _pivot(tr, center)
    phase = (index / max(count, 1)) * n
    peak = (phase + n * 0.25) % n
    tr.scale.add_keyframe(0, Point(100, 100), S())
    if 0 < peak < n:
        tr.scale.add_keyframe(int(peak), Point(112, 112), EO())
    tr.scale.add_keyframe(n, Point(100, 100), S())


def lead_follow(tr, index, count, n, params, center):
    _pivot(tr, center)
    lag = _p(params, "lag")
    d = index * lag
    a = max(n // 2 - d, 4)
    b = min(n - d, n)
    tr.rotation.add_keyframe(0, 0, S())
    tr.rotation.add_keyframe(min(a, n), 12, EO())
    tr.rotation.add_keyframe(min(b, n), 0, EI())
    tr.rotation.add_keyframe(n, 0, S())


def assemble_in(tr, index, count, n, params, center):
    spread = _p(params, "spread")
    cx, cy = center[0], center[1]
    ang = (index / max(count, 1)) * 2 * math.pi
    ox = cx + math.cos(ang) * spread
    oy = cy + math.sin(ang) * spread
    tr.anchor_point.value = center
    tr.position.add_keyframe(0, Point(ox, oy), EO())
    tr.position.add_keyframe(min(14, n), Point(cx, cy), EO())
    tr.position.add_keyframe(max(n - 14, 15), Point(cx, cy), EI())
    tr.position.add_keyframe(n, Point(ox, oy), EI())
    tr.opacity.add_keyframe(0, 10, EO())
    tr.opacity.add_keyframe(min(14, n), 100, EO())
    tr.opacity.add_keyframe(max(n - 14, 15), 100, EI())
    tr.opacity.add_keyframe(n, 10, EI())


def type_in(tr, index, count, n, params, center):
    stagger = _p(params, "stagger")
    d = min(index * stagger, max(n - 8, 1))
    tr.opacity.add_keyframe(0, 0, EO())
    tr.opacity.add_keyframe(max(d, 1), 0, EO())
    tr.opacity.add_keyframe(min(d + 4, n), 100, EO())
    tr.opacity.add_keyframe(max(n - 6, d + 5), 100, EI())
    tr.opacity.add_keyframe(n, 0, EI())


def segment_rebuild(tr, index, count, n, params, center):
    _pivot(tr, center)
    turn = _p(params, "turn")
    stagger = _p(params, "stagger")
    d = index * stagger
    a = min(d + 14, n)
    tr.rotation.add_keyframe(0, turn, EO())
    tr.rotation.add_keyframe(a, 0, EO())
    tr.rotation.add_keyframe(max(n - 12, a + 1), 0, EI())
    tr.rotation.add_keyframe(n, turn, EI())
    tr.opacity.add_keyframe(0, 20, EO())
    tr.opacity.add_keyframe(a, 100, EO())
    tr.opacity.add_keyframe(max(n - 12, a + 1), 100, EI())
    tr.opacity.add_keyframe(n, 20, EI())


def orbit(tr, index, count, n, params, center):
    radius = _p(params, "radius")
    cx, cy = center[0], center[1]
    phase = (index / max(count, 1)) * 2 * math.pi
    steps = 12
    tr.anchor_point.value = center
    for k in range(steps + 1):
        t = k / steps
        f = int(round(t * n))
        ang = phase + t * 2 * math.pi
        x = cx + math.cos(ang) * radius
        y = cy + math.sin(ang) * radius
        tr.position.add_keyframe(f, Point(x, y), LIN())


PRESETS = {
    "stagger_rise": stagger_rise,
    "sequential_glow": sequential_glow,
    "pulse_offset": pulse_offset,
    "lead_follow": lead_follow,
    "assemble_in": assemble_in,
    "type_in": type_in,
    "segment_rebuild": segment_rebuild,
    "orbit": orbit,
}


# ---- builder --------------------------------------------------------------
def build_elements_tgs(svg_path, out_tgs, preset="sequential_glow",
                       params=None, n=60, sort="x", bg=None):
    an = parse_svg_file(svg_path)
    an.frame_rate = FPS
    an.in_point = 0
    an.out_point = n
    for layer in list(an.layers):
        layer.in_point = 0
        layer.out_point = n

    groups = element_groups(an)
    idx = 0 if sort == "x" else 1
    groups.sort(key=lambda g: g.bounding_box(0).center()[idx])

    count = len(groups)
    fn = PRESETS[preset]
    p = params or {}
    for index, g in enumerate(groups):
        tr = _elem_transform(g)
        center = _center(g)
        fn(tr, index, count, n, p, center)

    if bg:
        cfg = BG_DEFAULT if bg is True else bg
        rx = cfg.get("rx", BG_DEFAULT["rx"])
        fill = cfg.get("fill", BG_DEFAULT["fill"])
        _add_bg_layer(an, rx, fill, n)

    export_tgs(an, out_tgs)
    return out_tgs


# ---- self-test ------------------------------------------------------------
if __name__ == "__main__":
    from lottie.parsers.tgs import parse_tgs

    SIG = "build/svgwrap/signal.svg"
    WIN = "build/svgwrap/windows.svg"
    OUTDIR = "build/tgs2"
    os.makedirs(OUTDIR, exist_ok=True)
    t_sig = os.path.join(OUTDIR, "_t_signal.tgs")
    t_win = os.path.join(OUTDIR, "_t_windows.tgs")
    LIMIT = 64 * 1024

    # 1. element_groups counts
    sig_groups = len(element_groups(parse_svg_file(SIG)))
    win_groups = len(element_groups(parse_svg_file(WIN)))
    assert sig_groups == 4, "signal groups != 4: %d" % sig_groups
    assert win_groups == 4, "windows groups != 4: %d" % win_groups

    # 2. build
    build_elements_tgs(SIG, t_sig, preset="stagger_rise", n=60)
    build_elements_tgs(WIN, t_win, preset="sequential_glow", n=60)

    # 3. files exist and within size limit
    s_sig = os.path.getsize(t_sig)
    s_win = os.path.getsize(t_win)
    assert os.path.exists(t_sig) and s_sig <= LIMIT, "signal size %d" % s_sig
    assert os.path.exists(t_win) and s_win <= LIMIT, "windows size %d" % s_win

    # 4. re-import validity
    for path in (t_sig, t_win):
        a2 = parse_tgs(path)
        assert len(a2.layers) >= 1, "no layers in %s" % path
        assert a2.out_point == 60, "out_point %s in %s" % (a2.out_point, path)

    # 5. seamlessness: first==last keyframe value on a signal element
    an = parse_svg_file(SIG)
    an.frame_rate = FPS
    an.in_point = 0
    an.out_point = 60
    for layer in an.layers:
        layer.in_point = 0
        layer.out_point = 60
    gs = element_groups(an)
    gs.sort(key=lambda g: g.bounding_box(0).center()[0])
    tr = _elem_transform(gs[0])
    c = _center(gs[0])
    stagger_rise(tr, 0, len(gs), 60, {}, c)
    op = tr.opacity.keyframes
    assert list(op[0].start) == list(op[-1].start), \
        "opacity loop not closed: %s != %s" % (op[0].start, op[-1].start)
    pos = tr.position.keyframes
    assert list(pos[0].start) == list(pos[-1].start), \
        "position loop not closed: %s != %s" % (pos[0].start, pos[-1].start)

    sizes = "%d/%d" % (s_sig, s_win)

    # 6. cleanup
    for f in (t_sig, t_win):
        if os.path.exists(f):
            os.remove(f)

    print("tgs_anim OK  presets=%d signal_groups=%d windows_groups=%d sizes=%s"
          % (len(PRESETS), sig_groups, win_groups, sizes))
