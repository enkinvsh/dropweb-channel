"""Easing & seamless-loop helpers for the CRT motion engine.

Pure-Python (no deps) so it can be imported anywhere in the pipeline.

Two families:
  * Cubic-bezier sampler matching the app's CSS-style timing
    (incl. the brand curve Cubic(0.2, 0.8, 0.2, 1.0)).
  * Spring / overshoot for "badass" snappy motion.

Plus loop utilities so every effect breathes on a perfectly seamless cycle:
frame i in [0, n) maps to a phase that returns to its start at i == n.
"""
import math

# --- cubic bezier (CSS cubic-bezier semantics: P0=(0,0) P3=(1,1)) -----------


class CubicBezier:
    """y = f(x) for a CSS cubic-bezier(x1,y1,x2,y2).

    Solves t from x with Newton + bisection fallback (the same approach
    browsers use), then evaluates y(t). Cheap enough to call per-frame.
    """

    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

    @staticmethod
    def _bez(t, a, b):  # value of a 1-D bezier with P0=0,P3=1
        mt = 1.0 - t
        return 3 * mt * mt * t * a + 3 * mt * t * t * b + t * t * t

    @staticmethod
    def _dbez(t, a, b):  # derivative wrt t
        mt = 1.0 - t
        return 3 * mt * mt * a + 6 * mt * t * (b - a) + 3 * t * t * (1 - b)

    def _solve_t(self, x):
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        t = x  # good initial guess
        for _ in range(8):  # Newton-Raphson
            err = self._bez(t, self.x1, self.x2) - x
            if abs(err) < 1e-6:
                return t
            d = self._dbez(t, self.x1, self.x2)
            if abs(d) < 1e-6:
                break
            t -= err / d
        lo, hi = 0.0, 1.0  # bisection fallback
        t = x
        for _ in range(20):
            v = self._bez(t, self.x1, self.x2)
            if abs(v - x) < 1e-6:
                return t
            if v < x:
                lo = t
            else:
                hi = t
            t = 0.5 * (lo + hi)
        return t

    def __call__(self, x):
        return self._bez(self._solve_t(x), self.y1, self.y2)


# Brand curve from dropweb-app (Cubic(0.2,0.8,0.2,1.0)) + common presets.
BRAND = CubicBezier(0.2, 0.8, 0.2, 1.0)
EASE_OUT = CubicBezier(0.0, 0.0, 0.2, 1.0)
EASE_IN = CubicBezier(0.8, 0.0, 1.0, 1.0)
EASE_IN_OUT = CubicBezier(0.42, 0.0, 0.58, 1.0)
SNAP = CubicBezier(0.16, 1.0, 0.3, 1.0)  # fast snap, soft settle


# --- spring / overshoot ------------------------------------------------------


def spring(t, *, freq=2.6, damp=4.0):
    """Critically-ish damped spring step response, t in [0,1] -> ~[0,1].

    Overshoots slightly then settles at 1.0 (great for "pop" entrances).
    freq = oscillation frequency, damp = decay rate. Tuned for punch.
    """
    if t <= 0.0:
        return 0.0
    return 1.0 - math.exp(-damp * t) * math.cos(freq * math.tau * t * 0.5)


def overshoot(t, k=1.70158):
    """Back-ease-out: shoots past 1.0 then comes back. t in [0,1]."""
    t -= 1.0
    return t * t * ((k + 1) * t + k) + 1.0


def elastic_out(t, *, amp=1.0, period=0.3):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    s = period / 4.0
    return amp * math.pow(2, -10 * t) * math.sin((t - s) * math.tau / period) + 1.0


# --- seamless loop helpers ---------------------------------------------------


def loop_phase(i, n):
    """Frame index -> phase in [0,1) that wraps perfectly (i==n => 0)."""
    return (i % n) / float(n)


def ping_pong(i, n, ease=None):
    """0->1->0 over the cycle, seamless. Optional easing applied to the ramp.

    Use for breath/pulse where the value must return to start with no jump.
    """
    p = loop_phase(i, n)
    tri = 1.0 - abs(2.0 * p - 1.0)  # triangle 0->1->0
    return ease(tri) if ease else tri


def loop_sin(i, n, phase=0.0):
    """Smooth seamless 0..1 sine (no triangle kink). phase shifts the start."""
    return 0.5 * (1.0 - math.cos(math.tau * (loop_phase(i, n) + phase)))


def loop_ease(i, n, curve=BRAND):
    """Seamless 0->1->0 driven through a cubic-bezier for branded feel."""
    return ping_pong(i, n, ease=curve)


def wrap_offset(value, span):
    """Wrap a scalar into [0, span) for rolling textures (e.g. scanline roll)."""
    return value % span


if __name__ == "__main__":  # quick self-check
    b = BRAND
    assert abs(b(0.0)) < 1e-6 and abs(b(1.0) - 1.0) < 1e-6
    assert all(0.0 <= b(x / 20) <= 1.0001 for x in range(21))
    # seamless: phase 0 at i=0 equals phase at i=n
    assert abs(ping_pong(0, 30) - ping_pong(30, 30)) < 1e-9
    assert abs(loop_sin(0, 30) - loop_sin(30, 30)) < 1e-9
    print("easing OK  brand(0.5)=%.4f spring(0.4)=%.4f overshoot(0.6)=%.4f"
          % (b(0.5), spring(0.4), overshoot(0.6)))
