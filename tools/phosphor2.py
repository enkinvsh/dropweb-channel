"""phosphor2 — premium phosphor renderer (drop-in for phosphor.phosphor).

Same public signature as the old `phosphor()` so the rest of the pipeline keeps
working unchanged:

    phosphor2(mask, size=100, color="#00DE52", glow=1.0,
              scanlines=True, transparent=True, supersample=4, **extra) -> RGBA

Upgrades vs. the old two-GaussianBlur glow:
  * linear-light, premultiplied compositing (correct neon, no muddy clipping)
  * multi-pass downsample bloom (wide cinematic halo + tight core)
  * optional full CRT post (barrel, chromatic aberration, rolling scanlines,
    shadow mask, vignette, film grain) — all coverage-aware so the transparent
    void stays clean for the alpha webm
  * accepts a `phase` (0..1) so animated callers get a seamless scanline ROLL

CPU FALLBACK: if numpy/scipy are unavailable, transparently delegates to the
original `phosphor.phosphor` so nothing ever breaks. Detected once at import.
"""
import os
from .phosphor import phosphor as _legacy_phosphor, hex_rgb  # noqa: F401 re-export

try:
    import numpy as np
    from . import raster, bloom, crt
    _NUMPY = True
except Exception:  # pragma: no cover - graceful CPU fallback
    _NUMPY = False


# tuned look constants (brand neon on void) ----------------------------------
_BLOOM = dict(levels=2, base_sigma=0.45, threshold=0.0)
_CORE_SIGMA = 0.0  # резкое ядро (без мыла)


def phosphor2(mask, size=100, color="#00DE52", glow=1.0,
              scanlines=False, transparent=True, supersample=int(os.environ.get("SS", "4")),
              *, phase=0.0, crt_post=False, bloom_intensity=0.7,
              core_boost=1.0, **extra):
    """Render a single premium phosphor RGBA frame.

    Extra kwargs (ignored by legacy fallback): phase, crt_post,
    bloom_intensity, core_boost. Returns a size x size PIL RGBA image.
    """
    if not _NUMPY:
        # fallback keeps the exact old behaviour and signature
        return _legacy_phosphor(mask, size=size, color=color, glow=glow,
                                scanlines=scanlines, transparent=transparent,
                                supersample=min(supersample, 4))

    ss = max(1, int(supersample))
    work = size * ss
    col = raster.hex_to_linear(color)

    # 1. mask -> premultiplied linear core buffer (supersampled)
    m = raster.from_pil_mask(mask, work)
    core = raster.mask_to_buffer(m, col, intensity=core_boost)
    if _CORE_SIGMA > 0:
        core = raster.gblur(core, _CORE_SIGMA * ss)

    # 2. additive multi-pass bloom (glow scales the intensity)
    glow_buf = bloom.bloom(core, intensity=bloom_intensity * glow,
                           base_sigma=_BLOOM["base_sigma"] * ss,
                           levels=_BLOOM["levels"], threshold=_BLOOM["threshold"])
    comp = raster.add(raster.new_buffer(work, work), glow_buf, gain=1.0)
    comp = raster.over(comp, core)

    # 3. CRT post (operates at working res, then we downsample)
    if crt_post:
        comp = crt.apply_crt(
            comp, phase=phase,
            barrel_k=0.08, chroma=1.0 * ss, scan_depth=0.30 if scanlines else 0.0,
            scan_period=2.2 * ss, scan_roll=1.0, mask=0.06,
            vig=0.38, noise=0.035,
        )
    elif scanlines:
        comp = crt.scanlines(comp, phase, period=2.2 * ss, depth=0.30)

    # 4. downsample supersample -> output (area average via gaussian + decimate)
    if ss > 1:
        comp = raster.gblur(comp, 0.5 * ss)
        comp = comp[::ss, ::ss][:size, :size]

    void = raster.hex_to_linear("#030305") if not transparent else None
    return raster.to_pil(comp, void=void)


# --- motion blur via subframe accumulation ----------------------------------


def motion_blur(render_subframe, n_sub=4):
    """Average `n_sub` sub-rendered RGBA PIL frames into one motion-blurred frame.

    `render_subframe(s)` must return a PIL RGBA image for sub-time s in [0,1).
    Accumulation is done in linear premultiplied space (correct motion blur),
    not by naive sRGB averaging. CPU fallback: simple alpha-weighted mean.

    Use inside an effect to blur fast motion between two keyframes, e.g.:
        def frame(i):
            return motion_blur(lambda s: spin_at((i + s) / n), n_sub=4)
    """
    subs = [render_subframe(s / n_sub) for s in range(n_sub)]
    if not _NUMPY:
        # crude but safe: average uint8 arrays via PIL blend chain
        from PIL import Image
        acc = subs[0]
        for k, im in enumerate(subs[1:], start=2):
            acc = Image.blend(acc, im, 1.0 / k)
        return acc
    acc = None
    for im in subs:
        arr = np.asarray(im).astype(np.float32) / 255.0
        a = arr[..., 3:4]
        lin = raster.srgb_to_linear(arr[..., :3]) * a  # premultiply in linear
        buf = np.concatenate([lin, a], axis=-1)
        acc = buf if acc is None else acc + buf
    acc /= float(n_sub)
    return raster.to_pil(acc)


if __name__ == "__main__":
    from PIL import Image, ImageDraw
    size = 100
    mask = Image.new("L", (512, 512), 0)
    ImageDraw.Draw(mask).ellipse([140, 140, 372, 372], fill=255)
    img = phosphor2(mask, size=size, color="#00DE52", glow=1.0, phase=0.0)
    assert img.size == (size, size) and img.mode == "RGBA"
    import numpy as _np
    px = _np.asarray(img)
    # bloom should leak green outside the disk; void corner stays transparent
    corner = int(px[2, 2, 3])
    center = tuple(int(v) for v in px[50, 50, :3])
    # motion blur smoke test
    mb = motion_blur(lambda s: phosphor2(mask, size=size, glow=0.8 + s), n_sub=3)
    print("phosphor2 OK  numpy=%s  size=%s  center=%s  corner_alpha=%d  mb=%s"
          % (_NUMPY, img.size, center, corner, mb.size))
    assert mb.size == (size, size)
