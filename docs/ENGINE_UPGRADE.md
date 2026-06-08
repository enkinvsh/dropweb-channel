# Engine Upgrade Proposal — Premium Neon-CRT Emoji Renderer

**Status:** prototype complete + verified. All new modules are additive (no
existing file was modified). Drop-in path preserves the public interface and the
alpha-webm encode.

**TL;DR recommendation:** **Stay on Pillow for I/O, add `numpy` + `scipy` as the
effects core.** Do **not** adopt skia-python or moderngl as required paths.

---

## 1. Stack recommendation

| Option | Verdict for *our* constraints (100×100, ≤3s, ≤256KB alpha webm, ~32×≤90 frames, macOS CPU) |
|---|---|
| **Pillow only (current)** | Safe but capped. 8-bit clipping kills additive bloom; no coordinate-aware per-pixel CRT; per-pixel ops via `getpixel` are slow/clumsy. Keep it — but only as the I/O + source-rasterization layer. |
| **numpy + scipy (CHOSEN)** | Best fit. Float32 linear premultiplied buffers give correct additive neon, HDR bloom accumulation, and shader-style CRT in vectorized native code. 100×100 is ~10k px — array math is sub-ms; full 60-frame premium effect renders in **3.9–15 s** (measured). Zero GPU/context risk. `scipy.ndimage.gaussian_filter` is the blur workhorse. |
| **skia-python** | Viable on CPU (raster backend) and powerful for vector/text/blend-modes, but **overkill at 100px** and adds a premultiplied-alpha foot-gun at the ffmpeg boundary. Not worth the dependency for bloom/CRT math that numpy does in a few lines. Optional future upgrade *only* if we need antialiased vector drawing. |
| **moderngl (GLSL offscreen)** | **Rejected as a required path.** It needs a real OpenGL context; on macOS that means CGL/GPU, and "headless" ≠ "CPU". No reliable EGL/OSMesa CPU fallback on macOS. Directly violates the "must run on macOS CPU / must-not-break encode" constraint. Acceptable only as an *optional* accelerated path with a numpy fallback — not recommended given numpy already meets perf needs. |

### Why numpy wins here specifically
- **Correct neon:** additive glow must accumulate in **linear light** without
  clipping at every step. Pillow's `ImageChops.add` clips to 0–255 per op →
  muddy. numpy float32 stays HDR until the final tonemap.
- **CPU-only, deterministic, headless** — exactly the constraint.
- **Tiny frames** make the "GPU is faster" argument irrelevant; context setup +
  readback would cost more than the whole numpy render.
- **Graceful degradation:** if numpy/scipy are ever missing, the renderer falls
  back to the original Pillow phosphor automatically (verified).

### Install
```bash
pip install "numpy>=1.24" "scipy>=1.10"   # add to requirements.txt
```
Verified installed clean on this machine: **arm64, Python 3.9.6, numpy 2.0.2,
scipy 1.13.1, Pillow 11.3.0**.

---

## 2. Reusable working modules (all delivered + verified)

All live in `tools/`. Each has a `python -m tools.<mod>` self-test.

| Module | What it provides | Self-test result |
|---|---|---|
| `tools/easing.py` | `CubicBezier` sampler (Newton+bisection), brand curve `Cubic(0.2,0.8,0.2,1.0)`, `spring`/`overshoot`/`elastic_out`, seamless-loop helpers (`ping_pong`, `loop_sin`, `loop_ease`). Pure-Python, no deps. | `brand(0.5)=0.9461`, seamless asserts pass |
| `tools/raster.py` | numpy RGBA core: sRGB↔linear, premultiplied buffers, `over`/`add`/`screen` blends, `gblur` (scipy + pure-numpy box fallback), `remap` (bilinear warp), `to_pil` with Reinhard tonemap. | center px = exact `#00DE52` `(0,222,82,255)` |
| `tools/bloom.py` | Multi-pass **downsample** additive bloom (mip pyramid → upsample-accumulate). Wide cinematic halo + tight core, cheap because widest blur runs at 1/16 res. | 6px bar leaks glow 44px out; soft falloff |
| `tools/particles.py` | Vectorized `ParticleField` (scatter-add splat + feedback trails) and `ember_loop`. Sparks/embers with fade trails + additive blend. Deterministic seed, warm-up for seamless loops. | 571 lit ember px, no warnings |
| `tools/crt.py` | Per-pixel CRT: `barrel`, `chromatic` (radial), rolling `scanlines`, `shadow_mask` (aperture grille), `vignette`, `film_noise`, `apply_crt`. **Coverage-aware** — never paints the transparent void. | scan roll seam = **0.0000**; void alpha = **0** |
| `tools/phosphor2.py` | Drop-in for `phosphor()` — same signature + extras (`phase`, `crt_post`, `bloom_intensity`). numpy core+bloom+CRT, **auto Pillow fallback**. Plus `motion_blur()` (linear-space subframe accumulation). | numpy + fallback paths both produce 100×100 RGBA |
| `tools/animate2.py` | 3 premium demo effects (`ember_breath`, `spin3d` w/ motion blur, `shock_ring` w/ SNAP bezier), same `fn(mask,size,color,**kw)->[RGBA]` contract, registered in `EFFECTS2`. | all 3 loop, 100×100 RGBA |

### Key code patterns

**Additive bloom (multi-pass downsample)** — `tools/bloom.py`:
```python
src = bright_pass(buf, threshold=0.0)        # keep lit pixels
pyramid = []                                  # downsample chain
cur = src
for _ in range(levels):
    cur = raster.gblur(cur, base_sigma)
    cur = _downsample(cur)                     # half-res each step
    pyramid.append(cur)
acc = raster.new_buffer(h, w)                  # upsample-accumulate back up
for lvl in reversed(pyramid):
    acc[..., :3] += _upsample_to(lvl, (h, w))[..., :3] * weight
```

**Particle splat (vectorized, no per-particle loop)** — `tools/particles.py`:
```python
self.field *= self.trail                       # decay trails (feedback blur)
np.add.at(f, (y0, x0),     e * (1-fx) * (1-fy)) # bilinear scatter-add
np.add.at(f, (y0, x0 + 1), e * fx     * (1-fy))
# ... then one gaussian turns points into round embers
```

**CRT post (coverage-aware, seamless roll)** — `tools/crt.py`:
```python
scroll = phase * roll * period                 # integer cycles over the loop
line   = 0.5*(1 + np.cos(((y+scroll)/period)*2*np.pi))
out[..., :3] *= (1-depth) + depth*line          # darken RGB on premult buffer
# -> rides existing alpha, void stays transparent
```

**Seamless cubic-bezier easing** — `tools/easing.py`:
```python
BRAND = CubicBezier(0.2, 0.8, 0.2, 1.0)        # app signature curve
def ping_pong(i, n, ease=None):                 # 0->1->0, wraps perfectly
    tri = 1.0 - abs(2.0*(i % n)/n - 1.0)
    return ease(tri) if ease else tri
```

**Motion blur (linear subframe accumulation)** — `tools/phosphor2.py`:
```python
for s in range(n_sub):
    arr = srgb_to_linear(sub_rgb) * sub_a        # premultiply in linear
    acc += concat([arr, sub_a])
return to_pil(acc / n_sub)                        # correct, not naive sRGB mean
```

---

## 3. Concrete refactor proposal for the existing modules

**Principle: additive, reversible, interface-preserving.** Nothing existing was
touched in this prototype; the new files sit alongside.

### Phase A — adopt the renderer (zero behaviour change for callers)
`tools/animate.py` currently does `from .phosphor import phosphor`. Switch the
import to the upgraded renderer, which keeps the identical signature:
```python
# tools/animate.py
from .phosphor2 import phosphor2 as phosphor   # drop-in; same (mask,size,color,glow,...)
```
Every existing effect (`breath`, `spin`, `ring`, `glitch`, …) immediately gains
bloom + CRT character with **no other change**, because `phosphor2` accepts the
same args and ignores extras. If numpy is absent it silently uses the old code.

Optionally thread `phase` into the existing effects' phosphor calls so their
scanlines roll seamlessly (one-line change per effect):
```python
out.append(phosphor(mask, size=size, color=color, glow=g,
                    phase=easing.loop_phase(i, n)))
```

### Phase B — upgrade the childish motions
Fold `animate2.py`'s patterns into `animate.py`, replacing weak effects:
- `spin` → `spin3d` (subframe motion blur on the fast edge)
- `ring` → `shock_ring` (SNAP cubic-bezier, fading additive shock)
- `flicker`/`fire` → `ember_breath` (real particle embers + additive bloom)
- Replace `random.random()` brightness jitter with `easing.spring`/`loop_sin`
  so motion reads intentional, not nervous.

Then merge registries:
```python
from .animate2 import EFFECTS2
EFFECTS.update(EFFECTS2)
```
`build_emoji.py` needs **no change** — it already looks effects up by name in
`animate.EFFECTS` and feeds frames to `encode.encode_webm` unchanged.

### Phase C — perf budget (measured, fits 32×90)
`spin3d` (motion blur ×3, supersample ×3) is the heaviest at ~15 s / 60 frames.
For the full set, drop `supersample` to 2 for motion-blurred effects, or cache
the base glyph render across subframes. Static-glyph effects (`ember_breath`)
run at ~4 s/60f. Whole 32-emoji set well within a normal build.

### Encode step — unchanged and verified
`tools/encode.py` is **not modified**. Verified end-to-end:

| Effect | Frames | Render | Size | ≤256KB | 100×100 | Alpha preserved |
|---|---|---|---|---|---|---|
| ember_breath | 60 | 3.9s | 102.1 KB | ✅ | ✅ | ✅ |
| spin3d | 60 | 15.2s | 11.5 KB | ✅ | ✅ | ✅ |
| shock_ring | 60 | 9.4s | 17.6 KB | ✅ | ✅ | ✅ |

> **Alpha note (important for whoever QAs):** `ffprobe` shows `pix_fmt=yuv420p`
> but the stream carries `TAG:alpha_mode=1` (VP9 stores alpha in a side layer).
> To *verify* alpha on decode you must use the libvpx decoder:
> `ffmpeg -c:v libvpx-vp9 -i x.webm -pix_fmt rgba ...`. The native vp9 decoder
> drops the alpha layer on probe — that is a decoder quirk, not a data loss.
> Confirmed: decoded frame has 4217 transparent + 1313 opaque px, matching the
> source. Telegram renders the alpha correctly.

### Migration safety
- **No GPU dependency.** numpy/scipy are CPU; moderngl/skia not used.
- **CPU fallback proven:** running under system Python (no numpy) → phosphor2
  delegates to legacy phosphor, still emits valid 100×100 RGBA (verified).
- **Legacy intact:** `phosphor`, `animate.breath`, `encode_webm`, registry of
  17 effects all still pass after adding the new files.

---

## 4. Demo artifacts
- `build/demo/compare_old_vs_new.png` — flat disk (old) vs bloom+grille+vignette
  (new), 6× nearest-upscaled.
- `build/demo/ember_breath.webm`, `spin3d.webm`, `shock_ring.webm` — alpha webm,
  all <256KB, encoded through the unchanged `encode.py`.

## 5. requirements.txt change
```diff
 Pillow>=10.0
 requests>=2.31
+numpy>=1.24
+scipy>=1.10
```
(Both optional at runtime — absence triggers the Pillow fallback path.)
