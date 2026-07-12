"""Offline tests for «Пак из референсов» backend (stdlib unittest only).

Run: `.venv/bin/python3 -m unittest tools.test_pack_plan -v`
No network, no server: requests.post is monkeypatched per test.
"""
import base64
import json
import os
import re
import tempfile
import unittest
from io import BytesIO
from unittest import mock

from PIL import Image

from . import gen_icon, pack_plan, studio_server

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def _png_bytes():
    buf = BytesIO()
    Image.new("RGB", (2, 2), (0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


PNG = _png_bytes()
PNG_B64 = base64.b64encode(PNG).decode()


class FakeResp:
    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.text = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)

    def json(self):
        return self._payload


def _chat_resp(content):
    return FakeResp({"choices": [{"message": {"content": content}}]})


def _plan_json(n, uses_ref_values=None, slugs=None, summary="Сервис доступа к AI."):
    items = []
    for i in range(n):
        ur = uses_ref_values[i] if uses_ref_values else (i % 3 == 0)
        slug = slugs[i] if slugs else "concept-%d" % (i + 1)
        items.append({
            "slug": slug,
            "idea_ru": "Идея номер %d" % (i + 1),
            "prompt_en": "A bold centered emblem number %d" % (i + 1),
            "uses_ref": ur,
        })
    return json.dumps({"service_summary_ru": summary, "items": items})


class PlanValidationTests(unittest.TestCase):
    def _run(self, content, count=6, existing=()):
        with mock.patch.object(pack_plan.requests, "post",
                               return_value=_chat_resp(content)), \
                mock.patch.dict(os.environ, {"CLIPROXY_KEY": "sk-test"}):
            return pack_plan.make_plan([PNG, PNG], "Theme", count,
                                       existing_slugs=existing)

    def test_two_png_count_6_returns_6_valid(self):
        out = self._run(_plan_json(6), count=6)
        self.assertEqual(len(out["plan"]), 6)
        for it in out["plan"]:
            self.assertRegex(it["slug"], SLUG_RE)
            self.assertTrue(it["idea_ru"])
            self.assertTrue(it["prompt_en"])
            self.assertIsInstance(it["uses_ref"], bool)

    def test_count_12(self):
        out = self._run(_plan_json(12), count=12)
        self.assertEqual(len(out["plan"]), 12)

    def test_fenced_json_is_cleaned(self):
        fenced = "```json\n" + _plan_json(6) + "\n```"
        out = self._run(fenced, count=6)
        self.assertEqual(len(out["plan"]), 6)

    def test_prose_wrapped_json_extracted(self):
        wrapped = "Here you go:\n" + _plan_json(6) + "\nHope this helps!"
        out = self._run(wrapped, count=6)
        self.assertEqual(len(out["plan"]), 6)

    def test_garbage_raises_invalid_json(self):
        with self.assertRaises(pack_plan.PlannerInvalidJSON):
            self._run("totally not json at all", count=6)

    def test_too_few_items_raises_invalid_json(self):
        with self.assertRaises(pack_plan.PlannerInvalidJSON):
            self._run(_plan_json(4), count=6)

    def test_more_items_truncated_to_count(self):
        out = self._run(_plan_json(9), count=6)
        self.assertEqual(len(out["plan"]), 6)

    def test_missing_field_raises_invalid_json(self):
        bad = json.dumps({"service_summary_ru": "x", "items": [
            {"slug": "a", "idea_ru": "", "prompt_en": "p", "uses_ref": True}]})
        with self.assertRaises(pack_plan.PlannerInvalidJSON):
            self._run(bad, count=1)

    def test_non_bool_uses_ref_raises(self):
        bad = json.dumps({"service_summary_ru": "x", "items": [
            {"slug": "a", "idea_ru": "i", "prompt_en": "p", "uses_ref": "yes"}]})
        with self.assertRaises(pack_plan.PlannerInvalidJSON):
            self._run(bad, count=1)

    def test_prompt_en_has_no_style_suffix(self):
        out = self._run(_plan_json(6), count=6)
        for it in out["plan"]:
            self.assertNotIn("#000000", it["prompt_en"])
            self.assertNotIn("neon", it["prompt_en"].lower())


class SlugNormalizationTests(unittest.TestCase):
    def _run(self, content, count, existing=()):
        with mock.patch.object(pack_plan.requests, "post",
                               return_value=_chat_resp(content)), \
                mock.patch.dict(os.environ, {"CLIPROXY_KEY": "sk-test"}):
            return pack_plan.make_plan([PNG, PNG], "", count, existing_slugs=existing)

    def test_duplicate_slugs_deduped(self):
        out = self._run(_plan_json(3, slugs=["dup", "dup", "dup"]), count=3)
        slugs = [it["slug"] for it in out["plan"]]
        self.assertEqual(len(set(slugs)), 3)
        self.assertEqual(slugs[0], "dup")
        self.assertEqual(slugs[1], "dup-2")
        self.assertEqual(slugs[2], "dup-3")

    def test_collision_with_existing_pack_order(self):
        out = self._run(_plan_json(1, slugs=["brand-signal"]), count=1,
                        existing=["brand-signal"])
        self.assertEqual(out["plan"][0]["slug"], "brand-signal-2")

    def test_dirty_slug_normalized(self):
        out = self._run(_plan_json(1, slugs=["Brand Signal!!!"]), count=1)
        self.assertRegex(out["plan"][0]["slug"], SLUG_RE)

    def test_empty_slug_falls_back_to_idea(self):
        out = self._run(_plan_json(1, slugs=[""]), count=1)
        self.assertRegex(out["plan"][0]["slug"], SLUG_RE)
        self.assertNotEqual(out["plan"][0]["slug"], "")


class RatioTests(unittest.TestCase):
    def _run(self, content, count):
        with mock.patch.object(pack_plan.requests, "post",
                               return_value=_chat_resp(content)), \
                mock.patch.dict(os.environ, {"CLIPROXY_KEY": "sk-test"}):
            return pack_plan.make_plan([PNG, PNG], "", count)

    def test_all_true_clamped_down(self):
        out = self._run(_plan_json(6, uses_ref_values=[True] * 6), count=6)
        n_true = sum(1 for it in out["plan"] if it["uses_ref"])
        self.assertLessEqual(n_true, 4)
        self.assertGreaterEqual(n_true, 2)

    def test_all_false_clamped_up(self):
        out = self._run(_plan_json(6, uses_ref_values=[False] * 6), count=6)
        n_true = sum(1 for it in out["plan"] if it["uses_ref"])
        self.assertGreaterEqual(n_true, 2)
        self.assertLessEqual(n_true, 4)

    def test_count_12_band(self):
        out = self._run(_plan_json(12, uses_ref_values=[True] * 12), count=12)
        n_true = sum(1 for it in out["plan"] if it["uses_ref"])
        self.assertGreaterEqual(n_true, 4)
        self.assertLessEqual(n_true, 8)


class MissingKeyTests(unittest.TestCase):
    def test_no_key_raises_missing_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(pack_plan.MissingKeyError):
                pack_plan.make_plan([PNG, PNG], "", 6)


class UpstreamTests(unittest.TestCase):
    def test_http_500_raises_upstream(self):
        with mock.patch.object(pack_plan.requests, "post",
                               return_value=FakeResp({"error": {"message": "boom"}}, status=500)), \
                mock.patch.dict(os.environ, {"CLIPROXY_KEY": "sk-test"}):
            with self.assertRaises(pack_plan.PlannerUpstreamError):
                pack_plan.make_plan([PNG, PNG], "", 6)


class RefSetIdTests(unittest.TestCase):
    def test_valid_ids(self):
        self.assertTrue(studio_server._valid_ref_set("refs-7f4c19a2"))
        self.assertTrue(studio_server._valid_ref_set("refs-00000000"))

    def test_invalid_ids(self):
        for bad in ["refs-7F4C19A2", "refs-123", "refs-1234567", "refs-123456789",
                    "sets-7f4c19a2", "refs-7f4c19az", "../refs-7f4c19a2", "", None, 42]:
            self.assertFalse(studio_server._valid_ref_set(bad))


class SaveSpecKeysTests(unittest.TestCase):
    def test_batch_draft_metadata_in_whitelist(self):
        for k in ("idea_ru", "uses_ref", "ref_set"):
            self.assertIn(k, studio_server.SAVE_SPEC_KEYS)

    def test_legacy_keys_preserved(self):
        for k in ("source", "prompt", "color", "tgs", "anchor", "label", "anim"):
            self.assertIn(k, studio_server.SAVE_SPEC_KEYS)


class GenerateEditShapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p1 = os.path.join(self.tmp, "ref-01.png")
        self.p2 = os.path.join(self.tmp, "ref-02.png")
        self.p3 = os.path.join(self.tmp, "ref-03.png")
        for p in (self.p1, self.p2, self.p3):
            with open(p, "wb") as f:
                f.write(PNG)
        self.out = os.path.join(self.tmp, "out.png")

    def _fake_post(self, captor):
        def _post(url, **kw):
            captor["url"] = url
            captor["files"] = kw.get("files")
            captor["data"] = kw.get("data")
            return FakeResp({"data": [{"b64_json": PNG_B64}]})
        return _post

    def test_str_path_uses_single_image_field(self):
        captor = {}
        with mock.patch.object(gen_icon.requests, "post", self._fake_post(captor)), \
                mock.patch.dict(os.environ, {"CLIPROXY_KEY": "sk-test"}):
            gen_icon.generate_edit(self.p1, "prompt", self.out, model="gpt-image-2")
        self.assertIsInstance(captor["files"], dict)
        self.assertIn("image", captor["files"])

    def test_two_paths_use_repeated_image_bracket_field(self):
        captor = {}
        with mock.patch.object(gen_icon.requests, "post", self._fake_post(captor)), \
                mock.patch.dict(os.environ, {"CLIPROXY_KEY": "sk-test"}):
            gen_icon.generate_edit([self.p1, self.p2], "prompt", self.out,
                                   model="gpt-image-2")
        files = captor["files"]
        self.assertIsInstance(files, list)
        self.assertEqual(len(files), 2)
        self.assertTrue(all(field == "image[]" for field, _ in files))
        names = [tup[0] for _field, tup in files]
        self.assertEqual(names, ["ref-01.png", "ref-02.png"])

    def test_three_paths_work(self):
        captor = {}
        with mock.patch.object(gen_icon.requests, "post", self._fake_post(captor)), \
                mock.patch.dict(os.environ, {"CLIPROXY_KEY": "sk-test"}):
            gen_icon.generate_edit([self.p1, self.p2, self.p3], "prompt", self.out,
                                   model="gpt-image-2")
        self.assertEqual(len(captor["files"]), 3)
        self.assertTrue(all(field == "image[]" for field, _ in captor["files"]))

    def test_gemini_multi_ref_rejected_before_network(self):
        called = {"n": 0}

        def _post(url, **kw):
            called["n"] += 1
            return FakeResp({"choices": [{"message": {"images": []}}]})

        with mock.patch.object(gen_icon.requests, "post", _post), \
                mock.patch.dict(os.environ, {"CLIPROXY_KEY": "sk-test"}):
            with self.assertRaises(gen_icon.MultiRefUnsupported):
                gen_icon.generate_edit([self.p1, self.p2], "prompt", self.out,
                                       model="gemini-3.1-flash-image")
        self.assertEqual(called["n"], 0)

    def test_multi_ref_code_attribute(self):
        self.assertEqual(gen_icon.MultiRefUnsupported.code, "model_no_multi_ref")


if __name__ == "__main__":
    unittest.main()
