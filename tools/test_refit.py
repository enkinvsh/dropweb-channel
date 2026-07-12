"""Offline tests for universal sticker resize (/api/refit vector fallback).

Run: `.venv/bin/python3 -m unittest tools.test_refit -v`
Pure geometry helpers + read-only real-base fixture. The handler tests spin an
in-process ThreadingHTTPServer on loopback (127.0.0.1:0) — no external network,
no API key (vector refit needs none).
"""
import copy
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any

from PIL import Image

from . import studio_server as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dropweb_bases() -> Any:
    with open(os.path.join(ROOT, "packs", "dropweb", "bases.json")) as f:
        return json.load(f)


def _tr(sx=100, sy=100, px=0.0, py=0.0, r=0, sk=None) -> Any:
    t = {"ty": "tr", "a": {"a": 0, "k": [0, 0]}, "p": {"a": 0, "k": [px, py]},
         "s": {"a": 0, "k": [sx, sy]}, "r": {"a": 0, "k": r},
         "o": {"a": 0, "k": 100}}
    if sk is not None:
        t["sk"] = {"a": 0, "k": sk}
    return t


def _ks() -> Any:
    return {"a": {"a": 0, "k": [0, 0]}, "p": {"a": 0, "k": [0, 0]},
            "s": {"a": 0, "k": [100, 100]}, "r": {"a": 0, "k": 0},
            "o": {"a": 0, "k": 100}}


def _sh(x0, y0, x1, y1, itan=None, otan=None, closed=True) -> Any:
    v = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    i = [list(itan or [0, 0]) for _ in v]
    o = [list(otan or [0, 0]) for _ in v]
    return {"ty": "sh", "ks": {"a": 0, "k": {"c": closed, "v": v, "i": i, "o": o}}}


def _fl() -> Any:
    return {"ty": "fl", "o": {"a": 0, "k": 100}, "c": {"a": 0, "k": [0, 1, 0, 1]}}


def _base(outer_tr, sh) -> Any:
    inner = {"ty": "gr", "it": [sh, _fl(), _tr()]}
    outer = {"ty": "gr", "it": [inner, outer_tr]}
    return {"layers": [{"ty": 4, "ks": _ks(), "shapes": [outer]}]}


def _bbox(base) -> Any:
    bb = ss._canvas_bbox(ss._collect_sh(base))
    assert bb is not None
    return bb


def _span(base) -> float:
    bb = _bbox(base)
    return max(bb[2] - bb[0], bb[3] - bb[1])


def _center(base) -> Any:
    bb = _bbox(base)
    return ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)


class OccupancyTests(unittest.TestCase):
    def test_identity_square_occupancy(self):
        base = _base(_tr(), _sh(156, 156, 356, 356))
        self.assertAlmostEqual(ss._occupancy_of_base(base), 200 / 512.0, places=6)

    def test_transform_aware_occupancy(self):
        # raw square 0..400 through outer tr scale 50% + translate 156 ->
        # canvas 156..356 -> same 200/512 despite raw 400-span vertices
        base = _base(_tr(sx=50, sy=50, px=156, py=156), _sh(0, 0, 400, 400))
        self.assertAlmostEqual(ss._occupancy_of_base(base), 200 / 512.0, places=6)


class VectorScaleTests(unittest.TestCase):
    def test_scale_grows_bbox_by_factor(self):
        base = _base(_tr(), _sh(156, 156, 356, 356, itan=[3, 4], otan=[-2, 5]))
        current = ss._occupancy_of_base(base)          # 200/512
        target = 1.25 * current
        out, cur = ss._resize_base_vector(base, target)
        self.assertLess(abs(float(cur) - current), 1e-6)
        self.assertLess(abs(_span(out) - 1.25 * 200), 1e-4)
        self.assertLess(abs(ss._occupancy_of_base(out) - target), 1e-6)

    def test_center_preserved(self):
        base = _base(_tr(), _sh(156, 156, 356, 356))
        out, _ = ss._resize_base_vector(base, 1.25 * ss._occupancy_of_base(base))
        cx, cy = _center(out)
        self.assertAlmostEqual(cx, 256.0, places=4)
        self.assertAlmostEqual(cy, 256.0, places=4)

    def test_tangents_scaled(self):
        base = _base(_tr(), _sh(156, 156, 356, 356, itan=[3, 4], otan=[-2, 5]))
        factor = 1.25
        out, _ = ss._resize_base_vector(base, factor * ss._occupancy_of_base(base))
        k = out["layers"][0]["shapes"][0]["it"][0]["it"][0]["ks"]["k"]
        self.assertAlmostEqual(k["i"][0][0], 3 * factor, places=6)
        self.assertAlmostEqual(k["i"][0][1], 4 * factor, places=6)
        self.assertAlmostEqual(k["o"][0][0], -2 * factor, places=6)
        self.assertAlmostEqual(k["o"][0][1], 5 * factor, places=6)

    def test_structure_unchanged(self):
        base = _base(_tr(), _sh(156, 156, 356, 356))
        out, _ = ss._resize_base_vector(base, 1.25 * ss._occupancy_of_base(base))
        self.assertEqual(len(out["layers"]), 1)
        outer = out["layers"][0]["shapes"][0]
        self.assertEqual(outer["ty"], "gr")
        inner = outer["it"][0]
        self.assertEqual([x["ty"] for x in inner["it"]], ["sh", "fl", "tr"])
        self.assertEqual(inner["it"][1]["c"]["k"], [0, 1, 0, 1])
        self.assertIs(inner["it"][0]["ks"]["k"]["c"], True)
        self.assertEqual(outer["it"][1], _tr())

    def test_source_not_mutated(self):
        base = _base(_tr(), _sh(156, 156, 356, 356))
        snapshot = copy.deepcopy(base)
        ss._resize_base_vector(base, 0.9)
        self.assertEqual(base, snapshot)


class ClampAndModeTests(unittest.TestCase):
    def test_clamp_bounds(self):
        self.assertEqual(ss._clamp_fit(1.5), 0.98)
        self.assertEqual(ss._clamp_fit(0.05), 0.30)
        self.assertEqual(ss._clamp_fit(0.7), 0.7)

    def test_delta_clamped_up(self):
        t = ss._refit_target(None, 0.10, 0.95)
        assert t is not None
        self.assertLess(abs(t - 0.98), 1e-9)

    def test_delta_relative(self):
        t = ss._refit_target(None, -0.05, 0.80)
        assert t is not None
        self.assertLess(abs(t - 0.75), 1e-9)

    def test_absolute_fit(self):
        t = ss._refit_target(0.8, None, None)
        assert t is not None
        self.assertLess(abs(t - 0.8), 1e-9)

    def test_neither_returns_none(self):
        self.assertIsNone(ss._refit_target(None, None, 0.5))

    def test_both_is_error(self):
        with self.assertRaises(ss.BadRequest):
            ss._refit_target(0.8, 0.05, 0.5)


class WorkingBaseTests(unittest.TestCase):
    def test_body_base_used(self):
        base = _base(_tr(), _sh(156, 156, 356, 356))
        got = ss._working_base(ROOT, {"base": base}, "dropweb", "whatever")
        self.assertIs(got, base)

    def test_missing_returns_none(self):
        got = ss._working_base(ROOT, {}, "dropweb", "no-such-id-zzz-000")
        self.assertIsNone(got)

    def test_stored_base_loaded(self):
        order = _load_dropweb_bases()["order"]
        got = ss._working_base(ROOT, {}, "dropweb", order[0])
        assert got is not None
        self.assertIn("layers", got)


class RealBaseTests(unittest.TestCase):
    base: Any = None

    def setUp(self):
        doc = _load_dropweb_bases()
        self.base = doc["bases"][doc["order"][0]]

    def test_occupancy_in_range(self):
        occ = ss._occupancy_of_base(self.base)
        self.assertGreater(occ, 0.30)
        self.assertLess(occ, 1.0)

    def test_roundtrip_up_then_down(self):
        occ = ss._occupancy_of_base(self.base)
        bb0 = _bbox(self.base)
        up, _ = ss._resize_base_vector(self.base, min(0.98, occ * 1.2))
        down, _ = ss._resize_base_vector(up, occ)
        bb1 = _bbox(down)
        for a, b in zip(bb0, bb1):
            self.assertAlmostEqual(a, b, places=3)


class UnsupportedTests(unittest.TestCase):
    def test_animated_path_rejected(self):
        sh = _sh(156, 156, 356, 356)
        sh["ks"]["a"] = 1
        with self.assertRaises(ss.VectorResizeUnsupported):
            ss._occupancy_of_base(_base(_tr(), sh))

    def test_skew_rejected(self):
        base = _base(_tr(sk=30), _sh(156, 156, 356, 356))
        with self.assertRaises(ss.VectorResizeUnsupported):
            ss._occupancy_of_base(base)

    def test_animated_transform_rejected(self):
        outer_tr = _tr()
        outer_tr["s"]["a"] = 1
        with self.assertRaises(ss.VectorResizeUnsupported):
            ss._occupancy_of_base(_base(outer_tr, _sh(156, 156, 356, 356)))


class RefitHandlerTests(unittest.TestCase):
    """Handler routing: delta mode must NEVER touch the mask pipeline and must
    converge step by step (regression for the fit=65-forever bug)."""

    httpd: Any = None
    port: Any = None
    thread: Any = None

    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ss.make_handler("dropweb", ROOT))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def _post(self, payload):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/refit" % self.port,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req, timeout=10)
            return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    @staticmethod
    def _base_at(occupancy):
        half = occupancy * 512 / 2.0
        return _base(_tr(), _sh(256 - half, 256 - half, 256 + half, 256 + half))

    def test_delta_never_uses_mask_pipeline(self):
        # gen png present -> old code would route delta through mask pipeline
        genp = os.path.join(ROOT, "build", "gen", "test-refit-masked.png")
        os.makedirs(os.path.dirname(genp), exist_ok=True)
        Image.new("L", (64, 64), 255).save(genp)
        called = []
        orig = ss._pipeline_from_mask
        ss._pipeline_from_mask = lambda *a, **k: called.append(1) or (_ for _ in ()).throw(
            AssertionError("mask pipeline must not run in delta mode"))
        try:
            status, out = self._post({
                "id": "test-refit-masked", "pack": "dropweb",
                "delta": 0.05, "base": self._base_at(0.60)})
        finally:
            ss._pipeline_from_mask = orig
            if os.path.exists(genp):
                os.remove(genp)
        self.assertEqual(called, [])
        self.assertEqual(status, 200)
        self.assertEqual(out["fit"], 65)

    def test_delta_converges_across_calls(self):
        s1, o1 = self._post({"id": "conv", "pack": "dropweb",
                             "delta": 0.05, "base": self._base_at(0.60)})
        self.assertEqual(s1, 200)
        self.assertEqual(o1["fit"], 65)
        self.assertAlmostEqual(ss._occupancy_of_base(o1["base"]), 0.65, places=4)
        # feed the RETURNED base into the next call -> must advance, not stick
        s2, o2 = self._post({"id": "conv", "pack": "dropweb",
                             "delta": 0.05, "base": o1["base"]})
        self.assertEqual(s2, 200)
        self.assertEqual(o2["fit"], 70)
        self.assertAlmostEqual(ss._occupancy_of_base(o2["base"]), 0.70, places=4)

    def test_delta_and_fit_together_rejected(self):
        status, out = self._post({"id": "conv", "pack": "dropweb",
                                  "delta": 0.05, "fit": 0.8,
                                  "base": self._base_at(0.60)})
        self.assertEqual(status, 400)
        self.assertIn("fit", out["error"])

    def test_delta_without_base_or_mask_404(self):
        status, out = self._post({"id": "zzz-absent-000", "pack": "dropweb",
                                  "delta": 0.05})
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
