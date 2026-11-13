"""The text size setting reaches the page."""
import unittest

from tests import fake_streamlit

class TextSizeTests(unittest.TestCase):
    def test_css_has_desktop_and_phone_sizes(self):
        fake, undo = fake_streamlit.install()
        self.addCleanup(undo)
        from ui.styles import build_css
        css = build_css(18, 16)
        self.assertIn("font-size: 18px", css)
        self.assertIn("max-width: 640px", css)
        self.assertIn("font-size: 16px", css)

    def test_apply_text_size_writes_the_style_block(self):
        fake, undo = fake_streamlit.install()
        self.addCleanup(undo)
        from ui.styles import apply_text_size
        apply_text_size()
        self.assertIn("<style>", fake.output())

if __name__ == "__main__":
    unittest.main()
