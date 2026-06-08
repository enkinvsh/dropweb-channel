"""Vectorized RGBA raster core (numpy + scipy) for the CRT engine.

Everything works in **linear, premultiplied, float32** internally — that's the
correct space for additive glow and bloom (sRGB-additive looks muddy/clipped).
We convert to/from sRGB 8-bit only at the PIL boundary.

Canonical buffer shape: (H, W, 4) float32, channels = premultiplied R,G,B,A,
each in [0, +inf) for color (HDR-ish, lets bloom bloom) and A in [0,1].

Why a separate core? Pillow can't do additive blending, multi-tap blur cheaply,
per-pixel warps, or HDR accumulation. numpy does all of it in a few ms at 100px.

CPU-only, no GPU. scipy.ndimage.gaussian_filter is the blur workhorse; a pure
numpy box-blur fallback is provided if scipy is ever unavailable.
"""
import numpy as np

try:
    from scipy.ndimage import gaussian_filter, map_coordinates
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover - fallback path
    _HAVE_SCIPY = False

from PIL import Image

# sRGB <-> linear ------------------------------------------------------------
# Standard sRGB transfer function (not the gamma-2.2 approximation) so colors
# match the brand hex exactly when nothing is blooming.


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float32)
    a = 0.055
    return np.where(c <= 0.04045, c / 12.92,
                    ((c + a) / (1 + a)) ** 2.4).astype(np.float32)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float32), 0.0, 1.0)
    a = 0.055
    return np.where(c <= 0.0031308, c * 12.92,
                    (1 + a) * np.power(c, 1 / 2.4) - a).astype(np.float32)


# buffer factories -----------------------------------------------------------


def new_buffer(h, w):
    """Empty premultiplied linear RGBA buffer."""
    return np.zeros((h, w, 4), dtype=np.float32)


def hex_to_linear(h):
    h = h.lstrip("#")
    rgb = np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)
    return srgb_to_linear(rgb)


def mask_to_buffer(mask01, color_linear, intensity=1.0):
    """Mask (H,W) float [0,1] + linear RGB -> premultiplied linear RGBA buffer.

    Premultiplied means stored RGB already = color * alpha, which makes additive
    and over-compositing both trivial and correct.
    """
    m = np.asarray(mask01, dtype=np.float32)
    a = np.clip(m, 0.0, 1.0)
    buf = np.empty(m.shape + (4,), dtype=np.float32)
    col = np.asarray(color_linear, dtype=np.float32) * float(intensity)
    buf[..., 0] = col[0] * a
    buf[..., 1] = col[1] * a
    buf[..., 2] = col[2] * a
    buf[..., 3] = a
    return buf


# blend modes (all on premultiplied buffers) ---------------------------------


def over(dst, src):
    """Porter-Duff source-over, premultiplied. Returns new buffer."""
    sa = src[..., 3:4]
    return src + dst * (1.0 - sa)


def add(dst, src, gain=1.0):
    """Additive (linear-dodge). The heart of neon glow. Color & alpha sum.

    Alpha is clamped to 1.0 (a pixel can't be more than fully opaque) but RGB
    is left HDR so bloom can pick up the over-bright cores.
    """
    out = dst.copy()
    out[..., :3] += src[..., :3] * gain
    out[..., 3] = np.clip(dst[..., 3] + src[..., 3] * gain, 0.0, 1.0)
    return out


def screen(dst, src):
    """Screen blend on alpha-coverage; softer than add, never clips to white."""
    out = dst.copy()
    out[..., :3] = 1.0 - (1.0 - np.clip(dst[..., :3], 0, 1)) * (1.0 - np.clip(src[..., :3], 0, 1))
    out[..., 3] = np.clip(dst[..., 3] + src[..., 3] * (1.0 - dst[..., 3]), 0.0, 1.0)
    return out


def scale_alpha(buf, k):
    """Scale a premultiplied buffer's coverage (keeps premultiply invariant)."""
    return buf * np.float32(k)


# blur -----------------------------------------------------------------------


def _box_blur_np(a, radius):
    """Separable box blur fallback (no scipy). radius in px, ~gaussian after 3x."""
    if radius < 1:
        return a
    k = 2 * int(radius) + 1
    pad = int(radius)
    out = a
    for axis in (0, 1):
        c = np.cumsum(np.pad(out, [(pad + 1, pad) if ax == axis else (0, 0)
                                   for ax in range(out.ndim)], mode="edge"), axis=axis)
        sl_hi = [slice(None)] * out.ndim
        sl_lo = [slice(None)] * out.ndim
        sl_hi[axis] = slice(k, None)
        sl_lo[axis] = slice(0, -k)
        out = (c[tuple(sl_hi)] - c[tuple(sl_lo)]) / k
    return out.astype(np.float32)


def gblur(buf, sigma):
    """Gaussian blur each channel of an (H,W,C) buffer. sigma in px."""
    if sigma <= 0:
        return buf
    if _HAVE_SCIPY:
        return gaussian_filter(buf, sigma=(sigma, sigma, 0), mode="constant").astype(np.float32)
    # 3 box passes approximate a gaussian
    r = max(1, int(round(sigma * 1.5)))
    out = buf
    for _ in range(3):
        out = _box_blur_np(out, r)
    return out


# geometric warp (for CRT barrel distortion / chromatic aberration) ----------


def remap(buf, map_y, map_x):
    """Sample buf at floating (y,x) coords. map_* shape (H,W). Bilinear."""
    h, w = buf.shape[:2]
    oh, ow = map_y.shape  # output shape follows the coordinate grid, not buf
    if _HAVE_SCIPY:
        out = np.empty((oh, ow, buf.shape[2]), dtype=np.float32)
        coords = np.stack([map_y, map_x])
        for c in range(buf.shape[2]):
            out[..., c] = map_coordinates(buf[..., c], coords, order=1,
                                          mode="constant", cval=0.0)
        return out
    # pure-numpy bilinear fallback
    y0 = np.clip(np.floor(map_y).astype(int), 0, h - 1)
    x0 = np.clip(np.floor(map_x).astype(int), 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    x1 = np.clip(x0 + 1, 0, w - 1)
    wy = np.clip(map_y - y0, 0, 1)[..., None]
    wx = np.clip(map_x - x0, 0, 1)[..., None]
    return (buf[y0, x0] * (1 - wy) * (1 - wx) + buf[y0, x1] * (1 - wy) * wx +
            buf[y1, x0] * wy * (1 - wx) + buf[y1, x1] * wy * wx).astype(np.float32)


# PIL boundary ---------------------------------------------------------------


def to_pil(buf, *, void=None):
    """Linear premultiplied buffer -> 8-bit sRGB RGBA PIL Image.

    Un-premultiplies, tonemaps HDR softly (Reinhard) so bloom cores stay colored
    instead of blowing to flat white, converts to sRGB. If `void` (linear rgb)
    is given the result is flattened onto it (opaque); else stays transparent.
    """
    b = buf
    a = np.clip(b[..., 3:4], 0.0, 1.0)
    rgb = b[..., :3]
    safe_a = np.where(a > 1e-4, a, 1.0)
    straight = rgb / safe_a  # un-premultiply
    # soft HDR rolloff keeps hue, tames >1 cores from additive stacking
    straight = straight / (1.0 + 0.25 * np.maximum(straight - 1.0, 0.0))
    straight = np.clip(straight, 0.0, 1.0)
    if void is not None:
        v = np.asarray(void, dtype=np.float32)
        straight = straight * a + v * (1.0 - a)
        a = np.ones_like(a)
    out = np.empty(b.shape[:2] + (4,), dtype=np.uint8)
    rgb8 = np.nan_to_num(linear_to_srgb(straight) * 255.0, nan=0.0)
    a8 = np.nan_to_num(a[..., 0] * 255.0, nan=0.0)
    out[..., :3] = np.clip(np.round(rgb8), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(np.round(a8), 0, 255).astype(np.uint8)
    return Image.fromarray(out)  # uint8 (H,W,4) -> RGBA


def from_pil_mask(img, size):
    """PIL image/L mask -> float [0,1] (H,W) at `size`, LANCZOS."""
    m = img.convert("L").resize((size, size), Image.LANCZOS)
    return np.asarray(m, dtype=np.float32) / 255.0


if __name__ == "__main__":
    h = w = 100
    col = hex_to_linear("#00DE52")
    mask = np.zeros((h, w), np.float32)
    mask[40:60, 40:60] = 1.0
    base = mask_to_buffer(mask, col)
    glow = gblur(base, 6.0)
    comp = add(new_buffer(h, w), glow, gain=2.0)
    comp = over(comp, base)
    img = to_pil(comp)
    assert img.size == (100, 100) and img.mode == "RGBA"
    px = np.asarray(img)
    print("raster OK  scipy=%s  center_rgba=%s  max_alpha=%d"
          % (_HAVE_SCIPY, tuple(px[50, 50]), px[..., 3].max()))
