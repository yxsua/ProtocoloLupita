"""Pruebas estaticas de seguridad sobre plantillas HTML y citizen.js."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

_ROOT = Path(__file__).resolve().parents[1]


class UiSafetyTests(unittest.TestCase):
    def test_templates_never_render_clickable_http_links(self) -> None:
        templates = [
            _ROOT / "app" / "templates" / "sms" / "inbox.html",
            _ROOT / "app" / "templates" / "citizen" / "portal.html",
        ]
        for tpl in templates:
            content = tpl.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r'<a\s+[^>]*href\s*=\s*["\']https?://', content, re.IGNORECASE),
                f"Se encontro enlace HTTP clickable en {tpl.name}",
            )

    def test_citizen_js_avoids_innerhtml_and_external_navigation(self) -> None:
        js_path = _ROOT / "app" / "static" / "citizen.js"
        js_text = js_path.read_text(encoding="utf-8")
        # El comentario superior menciona innerHTML; verificamos que no exista asignacion real
        self.assertNotIn(".innerHTML", js_text)
        self.assertNotIn("window.open", js_text)
        self.assertNotIn("location.href", js_text)


if __name__ == "__main__":
    unittest.main()
