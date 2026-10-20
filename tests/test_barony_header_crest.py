import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BaronyHeaderCrestTests(unittest.TestCase):
    def test_header_has_accessible_barony_crest_link(self):
        html = (ROOT / 'app/frontend/index.html').read_text(encoding='utf-8')
        self.assertIn('id="barony-menu-link"', html)
        self.assertIn('href="cabinet.html#barony"', html)
        self.assertIn('class="barony-menu-link js-modal-page"', html)
        self.assertIn('id="barony-menu-crest"', html)

    def test_player_crest_is_selected_from_loaded_map_rows(self):
        script = (ROOT / 'app/frontend/app.js').read_text(encoding='utf-8')
        self.assertIn('function updateBaronyMenuCrest(rows)', script)
        self.assertIn("String(row['Владелец'] || '') === String(userId)", script)
        self.assertIn('updateBaronyMenuCrest(rows);', script)

    def test_crest_button_has_interaction_styles(self):
        css = (ROOT / 'app/frontend/styles.css').read_text(encoding='utf-8')
        self.assertIn('.barony-menu-link:hover', css)
        self.assertIn('.barony-menu-link:focus-visible', css)

if __name__ == '__main__':
    unittest.main()
