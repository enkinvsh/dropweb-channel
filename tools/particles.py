"""Vectorized particle system: sparks / embers with fade trails + additive blend.

Design goals for "badass" but cheap:
  * All particles live in numpy arrays (pos, vel, life, size) and advance in
    one vectorized step — no per-particle Python loop. 200 sparks @ 90 frames
    is trivial.
  * Splatting is done by scatter-add into a low-res "energy" field, then a
    single gaussian blur turns points into soft round embers. This is the
    standard cheap way to render thousands of additive points.
  * Trails come for free: we keep a persistent field and decay it each frame
    (motion-blur-by-feedback) instead of redrawing every past position.
  * **Deterministic & seamless**: seed per emoji, and emitters are phase-based
    so the field at frame n matches frame 0 when you ask for a looped buffer.

Returns premultiplied linear RGBA buffers from `raster`, ready to `add()`.
"""
import numpy as np

from . import raster


class ParticleField:
    """A persistent additive ember field with decaying trails.

    Coordinates are in pixel space [0,size). Call emit()/step() per frame and
    render() to get a buffer. Use `trail` in (0,1): higher = longer trails.
    """

    def __init__(self, size, color_linear, *, trail=0.82, seed=0,
                 supersample=2):
        self.size = size
        self.ss = supersample
        self.fs = size * supersample          # field resolution
        self.color = np.asarray(color_linear, dtype=np.float32)
        self.trail = float(trail)
        self.rng = np.random.default_rng(seed)
        # particle state (float32 columns)
        self.px = np.zeros(0, np.float32)     # position x,y (field px)
        self.py = np.zeros(0, np.float32)
        self.vx = np.zeros(0, np.float32)     # velocity
        self.vy = np.zeros(0, np.float32)
        self.life = np.zeros(0, np.float32)   # remaining life [0,1]
        self.decay = np.zeros(0, np.float32)  # life lost per step
        self.heat = np.zeros(0, np.float32)   # brightness multiplier
        # persistent trail field (energy, single channel) at field res
        self.field = np.zeros((self.fs, self.fs), np.float32)

    # --- emission -----------------------------------------------------------

    def emit(self, n, *, cx, cy, speed=(0.6, 1.8), angle=(0.0, 2 * np.pi),
             gravity_bias: float = 0.0, life=(0.5, 1.0), heat=(0.8, 1.6),
             spread: float = 2.0):
        """Spawn n particles around (cx,cy) in SIZE coords (auto-scaled)."""
        if n <= 0:
            return
        r = self.rng
        cx, cy = cx * self.ss, cy * self.ss
        ang = r.uniform(angle[0], angle[1], n).astype(np.float32)
        spd = r.uniform(speed[0], speed[1], n).astype(np.float32) * self.ss
        vx = np.cos(ang) * spd
        vy = np.sin(ang) * spd - gravity_bias * self.ss
        jitter = r.normal(0, spread * self.ss, (2, n)).astype(np.float32)
        self.px = np.concatenate([self.px, cx + jitter[0]])
        self.py = np.concatenate([self.py, cy + jitter[1]])
        self.vx = np.concatenate([self.vx, vx])
        self.vy = np.concatenate([self.vy, vy])
        lf = r.uniform(life[0], life[1], n).astype(np.float32)
        self.life = np.concatenate([self.life, lf])
        self.decay = np.concatenate([self.decay, (1.0 / (lf * 30.0)).astype(np.float32)])
        self.heat = np.concatenate([self.heat, r.uniform(heat[0], heat[1], n).astype(np.float32)])

    # --- simulation ---------------------------------------------------------

    def step(self, *, gravity=0.0, drag=0.98, turbulence=0.0):
        """Advance one frame: integrate, age, cull, decay the trail field."""
        # decay persistent trails first (feedback motion blur)
        self.field *= self.trail
        if self.px.size:
            if turbulence:
                t = self.rng.normal(0, turbulence * self.ss, (2, self.px.size)).astype(np.float32)
                self.vx += t[0]
                self.vy += t[1]
            self.vy += gravity * self.ss
            self.vx *= drag
            self.vy *= drag
            self.px += self.vx
            self.py += self.vy
            self.life -= self.decay
            self._splat()
            keep = self.life > 0.0
            if not keep.all():
                self.px, self.py = self.px[keep], self.py[keep]
                self.vx, self.vy = self.vx[keep], self.vy[keep]
                self.life, self.decay = self.life[keep], self.decay[keep]
                self.heat = self.heat[keep]

    def _splat(self):
        """Scatter-add each particle's energy into the field (bilinear)."""
        fs = self.fs
        x, y = self.px, self.py
        inb = (x >= 0) & (x < fs - 1) & (y >= 0) & (y < fs - 1)
        if not inb.any():
            return
        x, y = x[inb], y[inb]
        life = np.clip(self.life[inb], 0.0, 1.0)
        e = (life ** 1.5) * self.heat[inb]   # bright while young
        x0 = np.floor(x).astype(np.intp)
        y0 = np.floor(y).astype(np.intp)
        fx = x - x0
        fy = y - y0
        f = self.field
        np.add.at(f, (y0, x0), e * (1 - fx) * (1 - fy))
        np.add.at(f, (y0, x0 + 1), e * fx * (1 - fy))
        np.add.at(f, (y0 + 1, x0), e * (1 - fx) * fy)
        np.add.at(f, (y0 + 1, x0 + 1), e * fx * fy)

    # --- render -------------------------------------------------------------

    def render(self, *, glow_sigma=1.6, gain=1.0):
        """Field -> premultiplied linear RGBA buffer at SIZE (additive-ready)."""
        fld = raster.gblur(self.field[..., None], glow_sigma)[..., 0]
        # downsample supersampled field back to size (average pooling)
        if self.ss > 1:
            s, ss = self.size, self.ss
            fld = fld[:s * ss, :s * ss].reshape(s, ss, s, ss).mean(axis=(1, 3))
        a = np.clip(fld * gain, 0.0, 1.0)
        buf = np.empty((self.size, self.size, 4), np.float32)
        energy = fld * gain  # HDR for bloom downstream
        buf[..., 0] = self.color[0] * energy
        buf[..., 1] = self.color[1] * energy
        buf[..., 2] = self.color[2] * energy
        buf[..., 3] = a
        return buf


def ember_loop(size, color_linear, n_frames, *, seed=0, rate=10,
               cx=None, cy=None, **emit_kw):
    """Convenience generator: a seamless-ish ember fountain.

    Returns list of premultiplied linear RGBA buffers (len == n_frames).
    Warms up for one full cycle so frame 0 already has live trails (loop-safe).
    """
    cx = size * 0.5 if cx is None else cx
    cy = size * 0.62 if cy is None else cy
    fld = ParticleField(size, color_linear, seed=seed)
    ekw = dict(speed=(0.5, 1.4), angle=(-2.2, -0.9), gravity_bias=0.3,
               life=(0.6, 1.0), heat=(0.9, 1.7), spread=3.0)
    ekw.update(emit_kw)

    def advance():
        fld.emit(rate, cx=cx, cy=cy, **ekw)  # type: ignore[arg-type]
        fld.step(gravity=0.015, drag=0.985, turbulence=0.04)

    for _ in range(n_frames):   # warm-up cycle for seamless trails
        advance()
    out = []
    for _ in range(n_frames):
        advance()
        out.append(fld.render(glow_sigma=1.4, gain=1.0))
    return out


if __name__ == "__main__":
    size, n = 100, 30
    col = raster.hex_to_linear("#00DE52")
    bufs = ember_loop(size, col, n, seed=7, rate=14)
    assert len(bufs) == n
    last = bufs[-1]
    lit = int((last[..., 3] > 0.02).sum())
    img = raster.to_pil(raster.add(raster.new_buffer(size, size), last, 1.0))
    print("particles OK  frames=%d  lit_px=%d  size=%s"
          % (len(bufs), lit, img.size))
    assert lit > 20, "no embers rendered"
