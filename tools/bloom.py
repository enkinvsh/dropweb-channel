"""High-quality additive bloom via multi-pass downsample/upsample.

This is the single biggest "premium" upgrade vs. the old two-GaussianBlur glow.
Real-engine bloom (Unreal/COD style) works on a mip pyramid:

  1. Bright-pass: keep only the over-bright (HDR) part of the image.
  2. Downsample to a pyramid (each level half-res, blurred) -> wide, cheap glow.
  3. Upsample-accumulate back up, adding each level -> energy at every scale,
     so you get both a tight halo AND a soft wide wash with no banding.
  4. Add the result to the original (linear, premultiplied).

Operating on a pyramid means the *widest* blur costs almost nothing (it's done
at 1/16 res), which is what makes big cinematic glow CPU-affordable at 100px.

All buffers are linear premultiplied RGBA float32 from `raster`.
"""
import numpy as np

from . import raster


def _downsample(buf):
    """2x box-downsample (average 2x2). Halves H and W (handles odd via crop)."""
    h, w = buf.shape[:2]
    h2, w2 = h - (h % 2), w - (w % 2)
    b = buf[:h2, :w2]
    return (b[0::2, 0::2] + b[1::2, 0::2] + b[0::2, 1::2] + b[1::2, 1::2]) * 0.25


def _upsample_to(buf, shape):
    """Nearest-ish bilinear upsample to a target (H,W) using raster.remap."""
    th, tw = shape
    sh, sw = buf.shape[:2]
    ys = np.linspace(0, sh - 1, th, dtype=np.float32)[:, None] * np.ones((1, tw), np.float32)
    xs = np.linspace(0, sw - 1, tw, dtype=np.float32)[None, :] * np.ones((th, 1), np.float32)
    return raster.remap(buf, ys, xs)


def bright_pass(buf, threshold=0.0, knee=0.5):
    """Soft-knee bright extraction. threshold=0 -> bloom everything (neon glows
    even at nominal brightness, which is what we want for phosphor)."""
    lum = (0.2126 * buf[..., 0] + 0.7152 * buf[..., 1] + 0.0722 * buf[..., 2])
    if threshold <= 0:
        w = np.ones_like(lum)
    else:
        soft = np.clip((lum - threshold + knee) / (2 * knee + 1e-5), 0, 1)
        w = np.maximum(soft * soft, np.clip(lum - threshold, 0, 1)) / (lum + 1e-5)
    out = buf.copy()
    out[..., :3] *= w[..., None]
    out[..., 3] *= np.clip(w, 0, 1)
    return out


def bloom(buf, *, levels=5, base_sigma=1.2, intensity=1.0, threshold=0.0,
          spread=1.0):
    """Multi-pass downsample bloom.

    levels      number of mip levels (5 @ 100px reaches ~32px-wide glow)
    base_sigma  blur applied at each level before downsampling
    intensity   how much bloom to add back (>1 = blown-out neon)
    threshold   bright-pass cutoff (0 = bloom all lit pixels)
    spread      multiplies per-level contribution as we go wider

    Returns a premultiplied linear RGBA *bloom-only* buffer (add it yourself,
    or use `apply` for the common case).
    """
    src = bright_pass(buf, threshold=threshold)
    # build pyramid (downsample chain), blurring a touch at each step
    pyramid = []
    cur = src
    for _ in range(levels):
        cur = raster.gblur(cur, base_sigma)
        cur = _downsample(cur)
        if cur.shape[0] < 2 or cur.shape[1] < 2:
            break
        pyramid.append(cur)
    # upsample-accumulate from smallest to largest, summing energy each level
    h, w = buf.shape[:2]
    acc = raster.new_buffer(h, w)
    weight = 1.0
    total = 0.0
    for i, lvl in enumerate(reversed(pyramid)):
        up = _upsample_to(lvl, (h, w))
        acc[..., :3] += up[..., :3] * weight
        acc[..., 3] = np.clip(acc[..., 3] + up[..., 3] * weight, 0, 1)
        total += weight
        weight *= spread
    if total > 0:
        acc[..., :3] *= (intensity / total)
        acc[..., 3] = np.clip(acc[..., 3] * (intensity / total), 0, 1)
    return acc


def apply(buf, **kw):
    """Convenience: original buffer + its bloom, additively combined."""
    glow = bloom(buf, **kw)
    return raster.add(buf.copy(), glow, gain=1.0)


if __name__ == "__main__":
    h = w = 100
    col = raster.hex_to_linear("#00DE52")
    mask = np.zeros((h, w), np.float32)
    mask[47:53, 20:80] = 1.0  # thin bar -> should bloom into a wide bar of glow
    base = raster.mask_to_buffer(mask, col)
    out = apply(base, levels=5, base_sigma=1.3, intensity=1.6)
    img = raster.to_pil(out)
    px = np.asarray(img)
    # glow must leak well beyond the 6px-tall bar (rows ~30 and ~70 should light)
    leak = int(px[30, 50, 1]) + int(px[70, 50, 1])
    print("bloom OK  size=%s  bar_g=%d  leak_g(30,70)=%d  alpha_at_row30=%d"
          % (img.size, px[50, 50, 1], leak, px[30, 50, 3]))
    assert leak > 0, "bloom did not spread"
