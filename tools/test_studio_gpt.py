"""Offline tests for the GPT-default studio migration (stdlib unittest only).

Run: `.venv/bin/python3 -m unittest tools.test_studio_gpt -v`
No network, no server: only pure helpers and module-level constants.
"""
import importlib
import os
import re
import unittest

from . import gen_icon, gen_prompt, studio_server

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class IdeaSlugTests(unittest.TestCase):
    def test_ru_phrase(self):
        self.assertEqual(gen_prompt.idea_slug("пингвин с ноутбуком"),
                         "pingvin-s-noutbukom")

    def test_mixed_special_letters(self):
        self.assertEqual(gen_prompt.idea_slug("Жёлтый Щит!"), "zheltyi-schit")

    def test_symbols_and_spaces_collapse(self):
        self.assertEqual(gen_prompt.idea_slug("a   b!!!c"), "a-b-c")
        self.assertEqual(gen_prompt.idea_slug("  --Hello--World--  "),
                         "hello-world")

    def test_truncated_to_32_and_valid(self):
        s = gen_prompt.idea_slug(
            "supercalifragilisticexpialidocious plus even more words here")
        self.assertLessEqual(len(s), 32)
        self.assertRegex(s, SLUG_RE)

    def test_truncation_strips_trailing_dash(self):
        s = gen_prompt.idea_slug("ab cd ef gh ij kl mn op qr st uv wx yz")
        self.assertLessEqual(len(s), 32)
        self.assertFalse(s.endswith("-"))
        self.assertRegex(s, SLUG_RE)

    def test_empty_and_junk_fall_back_to_icon(self):
        self.assertEqual(gen_prompt.idea_slug(""), "icon")
        self.assertEqual(gen_prompt.idea_slug("   "), "icon")
        self.assertEqual(gen_prompt.idea_slug("!!!"), "icon")
        self.assertEqual(gen_prompt.idea_slug(None), "icon")
        self.assertEqual(gen_prompt.idea_slug("ъ ь"), "icon")

    def test_always_valid_for_tricky_inputs(self):
        tricky = [
            "пингвин", "Ёж", "щ", "  ", "!!!", "123abc", "-lead", "trail-",
            "多字节 текст mixed", "UPPER CASE", "a.b.c/d\\e", "emoji 🎉 test",
            "ъъъ", "ЮЯ", "x" * 80, "по-русски с дефисами",
        ]
        for t in tricky:
            with self.subTest(t=t):
                self.assertRegex(gen_prompt.idea_slug(t), SLUG_RE)


class DefaultModelTests(unittest.TestCase):
    def test_image_model_default_gpt(self):
        old = os.environ.pop("DW_IMAGE_MODEL", None)
        try:
            importlib.reload(gen_icon)
            self.assertEqual(gen_icon.MODEL, "gpt-image-2")
        finally:
            if old is not None:
                os.environ["DW_IMAGE_MODEL"] = old
            importlib.reload(gen_icon)

    def test_text_model_default_terra(self):
        old = os.environ.pop("DW_TEXT_MODEL", None)
        try:
            importlib.reload(gen_prompt)
            self.assertEqual(gen_prompt.TEXT_MODEL, "gpt-5.6-terra")
        finally:
            if old is not None:
                os.environ["DW_TEXT_MODEL"] = old
            importlib.reload(gen_prompt)


class RoutingTests(unittest.TestCase):
    def test_gemini_goes_via_chat(self):
        self.assertIs(gen_icon._is_chat_image_model("gemini-3.1-flash-image"),
                      True)

    def test_gpt_image_goes_via_images_endpoint(self):
        self.assertIs(gen_icon._is_chat_image_model("gpt-image-2"), False)


class ServerConstantsTests(unittest.TestCase):
    def test_gen_models_gpt_first(self):
        self.assertEqual(studio_server.GEN_MODELS[0]["id"], "gpt-image-2")

    def test_style_suffix_black_and_no_gradients(self):
        self.assertIn("#000000", studio_server.STYLE_SUFFIX)
        self.assertIn("no gradients", studio_server.STYLE_SUFFIX)


if __name__ == "__main__":
    unittest.main()
