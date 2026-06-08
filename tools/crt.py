"""Per-pixel CRT post-processing (numpy, CPU). The "character" layer.

Pipeline order matters; this is the cinematic-correct order:

    barrel distortion -> chromatic aberration -> scanlines (rolling)
    -> vignette -> film grain/noise

ALPHA DISCIPLINE (important for transparent webm):
Every operation here *modulates existing coverage* — it multiplies brightness or
warps geometry, but it NEVER introduces opaque pixels into the transparent void.
Scanlines/vignette darken via RGB on premultiplied buffers (so they ride the
alpha), and noise is masked by current alpha. That keeps the emoji clean on any
chat background while still reading as a CRT.

All functions take and return premultiplied linear RGBA float32 buffers.
Effects are time-parameterised by `phase` in [0,1) so they LOOP seamlessly:
the scanline roll completes an integer number of cycles over the clip.
"""
import numpy as np

from . import raster


def _grid(h, w):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx / (w - 1)) * 2.0 - 1.0   # [-1,1]
    ny = (yy / (h - 1)) * 2.0 - 1.0
    return yy, xx, nx, ny


def barrel(buf, strength=0.12):
    """Lens/barrel distortion: bulge the center, pull the corners. CPU remap.

    strength 0 = none, ~0.12 = subtle CRT curve, >0.3 = fisheye.
    """
    if strength <= 0:
        return buf
    h, w = buf.shape[:2]
    _, _, nx, ny = _grid(h, w)
    r2 = nx * nx + ny * ny
    f = 1.0 + strength * r2                 # radial scale
    sx = nx * f
    sy = ny * f
    map_x = (sx * 0.5 + 0.5) * (w - 1)
    map_y = (sy * 0.5 + 0.5) * (h - 1)
    return raster.remap(buf, map_y, map_x)


def chromatic(buf, amount=1.2, *, center=True):
    """Chromatic aberration: split R/B radially outward from center.

    Works on premultiplied RGB *and* keeps alpha as the max of shifted coverage
    so the colored fringe stays visible at the silhouette edge.
    amount in pixels at the rim.
    """
    if amount <= 0:
        return buf
    h, w = buf.shape[:2]
    _, _, nx, ny = _grid(h, w)
    if center:
        # shift proportional to radius -> stronger fringe at edges (real lens)
        off_x = nx * amount
        off_y = ny * amount
    else:
        off_x = np.full((h, w), amount, np.float32)
        off_y = np.zeros((h, w), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    out = buf.copy()
    # red sampled shifted out, blue shifted in (opposite) -> classic split
    r = raster.remap(buf, yy + off_y, xx + off_x)
    b = raster.remap(buf, yy - off_y, xx - off_x)
    out[..., 0] = r[..., 0]
    out[..., 2] = b[..., 2]
    out[..., 3] = np.maximum.reduce([buf[..., 3], r[..., 3], b[..., 3]])
    return out


def scanlines(buf, phase=0.0, *, period=2.4, depth=0.35, roll=1.0):
    """Rolling horizontal scanlines. `phase` in [0,1) -> vertical scroll.

    For a seamless loop, the line pattern scrolls `roll` whole periods over the
    clip, so the texture is identical at phase 0 and phase 1.
    period = px between line centers, depth = darkening amount (0..1).
    """
    h, w = buf.shape[:2]
    y = np.arange(h, dtype=np.float32)[:, None]
    scroll = phase * roll * period
    line = 0.5 * (1.0 + np.cos(((y + scroll) / period) * 2.0 * np.pi))
    factor = (1.0 - depth) + depth * line   # in [1-depth, 1]
    out = buf.copy()
    out[..., :3] *= factor                  # darken RGB (premult -> rides alpha)
    return out


def shadow_mask(buf, strength=0.10):
    """Aperture-grille: faint vertical RGB triad modulation (real CRT phosphor)."""
    if strength <= 0:
        return buf
    h, w = buf.shape[:2]
    x = np.arange(w)
    mask = np.ones((w, 3), np.float32)
    mask[x % 3 == 0, 0] = 1.0 + strength    # R columns
    mask[x % 3 == 1, 1] = 1.0 + strength    # G columns
    mask[x % 3 == 2, 2] = 1.0 + strength    # B columns
    mask -= strength / 3.0                   # keep average ~1
    out = buf.copy()
    out[..., :3] *= mask[None, :, :]
    return out


def vignette(buf, strength=0.45, *, softness=1.1):
    """Darken toward the corners. Multiplies RGB so it respects alpha."""
    if strength <= 0:
        return buf
    h, w = buf.shape[:2]
    _, _, nx, ny = _grid(h, w)
    r = np.sqrt(nx * nx + ny * ny) / np.sqrt(2.0)
    v = np.clip(1.0 - strength * (r ** softness), 0.0, 1.0)
    out = buf.copy()
    out[..., :3] *= v[..., None]
    return out


def film_noise(buf, amount=0.05, *, seed=None, rng=None):
    """Additive film grain, masked by current coverage (never lights the void)."""
    if amount <= 0:
        return buf
    h, w = buf.shape[:2]
    rng = rng or np.random.default_rng(seed)
    n = rng.normal(0.0, amount, (h, w, 1)).astype(np.float32)
    out = buf.copy()
    cov = buf[..., 3:4]                       # only where something is lit
    out[..., :3] = np.maximum(out[..., :3] + n * cov, 0.0)
    return out


def apply_crt(buf, phase=0.0, *, barrel_k=0.10, chroma=1.0, scan_depth=0.32,
              scan_period=2.4, scan_roll=1.0, mask=0.08, vig=0.40,
              noise=0.04, rng=None):
    """Full CRT chain in correct order. `phase` drives the seamless scan roll."""
    b = barrel(buf, barrel_k)
    b = chromatic(b, chroma)
    b = scanlines(b, phase, period=scan_period, depth=scan_depth, roll=scan_roll)
    b = shadow_mask(b, mask)
    b = vignette(b, vig)
    b = film_noise(b, noise, rng=rng)
    return b


if __name__ == "__main__":
    h = w = 100
    col = raster.hex_to_linear("#00DE52")
    mask = np.zeros((h, w), np.float32)
    mask[20:80, 20:80] = 1.0
    base = raster.mask_to_buffer(mask, col)
    # seamless check: scanline factor identical at phase 0 and 1
    a = scanlines(base, 0.0)
    z = scanlines(base, 1.0)
    seam = float(np.abs(a[..., 1] - z[..., 1]).max())
    out = apply_crt(base, phase=0.3, rng=np.random.default_rng(1))
    img = raster.to_pil(out)
    px = np.asarray(img)
    # transparent void stays transparent (corner outside the square)
    void_alpha = int(px[5, 5, 3])
    print("crt OK  size=%s  scan_seam=%.4f  void_alpha=%d  center_rgb=%s"
          % (img.size, seam, void_alpha, tuple(px[50, 50, :3])))
    assert seam < 1e-4, "scanline roll not seamless"
    assert void_alpha == 0, "CRT leaked into transparent void"
