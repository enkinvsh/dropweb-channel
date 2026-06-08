"""Маска -> чистый центрированный 512-SVG (potrace+picosvg+wrap). Резко на любом размере."""
import os, re, subprocess, sys
from PIL import Image
PICO = os.path.join(os.path.dirname(sys.executable), "picosvg")

def make_clean_svg(mask_png, name, color="#00DE52", content_frac=0.60, thr=90, turd=2):
    os.makedirs("build/svg", exist_ok=True); os.makedirs("build/svgwrap", exist_ok=True)
    m = Image.open(mask_png).convert("L")
    bw = m.point(lambda v: 0 if v > thr else 255).convert("1")
    pbm = f"build/svg/{name}.pbm"; bw.save(pbm)
    psvg = f"build/svg/{name}.svg"
    subprocess.run(["potrace", pbm, "-s", "--tight", "-t", str(turd), "-o", psvg], check=True)
    fl = subprocess.run([PICO, psvg], capture_output=True, text=True).stdout
    vb = re.search(r'viewBox="([-\d.eE ]+)"', fl)
    x, y, w, h = [float(v) for v in vb.group(1).split()]
    paths = "".join(re.findall(r"<path[^>]*/>", fl)) or "".join(re.findall(r"<path.*?</path>", fl, flags=re.S))
    paths = re.sub(r'fill="[^"]*"', f'fill="{color}"', paths)
    if "fill=" not in paths:
        paths = paths.replace("<path", f'<path fill="{color}"')
    s = 512 * content_frac / max(w, h)
    tx = 256 - s * (x + w / 2); ty = 256 - s * (y + h / 2)
    out = (f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
           f'viewBox="0 0 512 512"><g transform="translate({tx} {ty}) scale({s})">{paths}</g></svg>')
    wpath = f"build/svgwrap/{name}.svg"; open(wpath, "w").write(out)
    return wpath


if __name__ == "__main__":
    import random
    from PIL import ImageDraw

    tmp = "build/_noise_selftest.png"
    os.makedirs("build", exist_ok=True)
    im = Image.new("L", (256, 256), 0)
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 196, 196], fill=255)  # big clean disk
    random.seed(0)
    for _ in range(200):  # ~200 random 1-3px speckles
        x, y = random.randint(0, 252), random.randint(0, 252)
        s = random.randint(1, 3)
        d.rectangle([x, y, x + s, y + s], fill=255)
    im.save(tmp)

    svg2 = make_clean_svg(tmp, "_noise", turd=2)
    svg40 = make_clean_svg(tmp, "_noise2", turd=40)
    n2 = open(svg2).read().count("<path")
    n40 = open(svg40).read().count("<path")
    assert n40 < n2, f"expected turd40 paths < turd2, got turd2={n2} turd40={n40}"

    for f in (tmp, svg2, svg40,
              "build/svg/_noise.pbm", "build/svg/_noise.svg",
              "build/svg/_noise2.pbm", "build/svg/_noise2.svg"):
        try:
            os.remove(f)
        except OSError:
            pass

    print("vectorize OK  paths turd2=%d turd40=%d" % (n2, n40))
