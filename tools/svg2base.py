"""SVG -> Lottie-base dict (same shape as a studio BASES[id] value).

A base value is `{"layers": [<ty:4 shape layers>]}`. We parse the SVG via
lottie's svg parser, take the Animation's dict, and keep only `layers`,
ensuring each layer is a ty:4 shape layer with a `shapes` list.
"""
import json
import os
import re

from lottie.parsers.svg import parse_svg_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _normalize_layers(layers):
    """Keep only ty:4 shape layers and ensure they carry a `shapes` list."""
    out = []
    for layer in layers:
        if layer.get("ty") != 4:
            continue
        if "shapes" not in layer or layer.get("shapes") is None:
            layer["shapes"] = []
        out.append(layer)
    return out


def svg_to_base(svg_path):
    """Return a Lottie base dict `{"layers": [...]}` for the given SVG path."""
    an = parse_svg_file(svg_path)
    d = an.to_dict()
    layers = _normalize_layers(d.get("layers", []))
    return {"layers": layers}


def _count_path_groups(shapes):
    """Count `gr` groups that (recursively) contain an `sh` (path) item."""
    n = 0
    for sh in shapes:
        if sh.get("ty") == "gr":
            items = sh.get("it", []) or []
            if any(x.get("ty") == "sh" for x in items):
                n += 1
            n += _count_path_groups([x for x in items if x.get("ty") == "gr"])
    return n


def _load_one_base_from_js():
    """Extract the first base value's first layer keys from studio/bases.js."""
    js_path = os.path.join(ROOT, "studio", "bases.js")
    with open(js_path) as f:
        for line in f:
            if line.startswith("window.BASES="):
                payload = line[line.index("=") + 1:].rstrip().rstrip(";")
                bases = json.loads(payload)
                first = next(iter(bases.values()))
                return set(first["layers"][0].keys())
    return set()


def _main():
    svg = os.path.join(ROOT, "build", "svgwrap", "signal.svg")
    base = svg_to_base(svg)
    assert base["layers"], "base has no layers"
    first = base["layers"][0]
    assert "shapes" in first, "first layer missing shapes"

    # structural parity check against an existing base layer
    ref_keys = _load_one_base_from_js()
    for k in ("ty", "shapes", "ks"):
        assert k in first, f"layer missing key {k}"
        if ref_keys:
            assert k in ref_keys, f"reference layer missing key {k}"

    groups = 0
    for layer in base["layers"]:
        groups += _count_path_groups(layer.get("shapes", []))
    assert groups >= 4, f"expected >=4 path groups, got {groups}"

    # round-trip: re-load via the lottie Animation object without error
    from lottie.objects import Animation
    Animation.load({
        "v": "5.5.2", "fr": 60, "ip": 0, "op": 60, "w": 512, "h": 512,
        "assets": [], "layers": base["layers"],
    })

    print(f"svg2base OK  groups={groups}")


if __name__ == "__main__":
    _main()
