import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
FRONTEND=ROOT/'app/frontend'


class CrestBoundGeneralTests(unittest.TestCase):
    def test_two_ready_icons_exist_for_every_catalogue_crest(self):
        crests=sorted((FRONTEND/'crests').glob('gerb_*.webp'))
        self.assertEqual(len(crests),18)
        for crest in crests:
            number=int(crest.stem.split('_')[1])
            for pose in ('foot','mounted'):
                icon=FRONTEND/'general'/f'general-gerb-{number:02d}-{pose}.svg'
                self.assertTrue(icon.is_file(),icon)
                source=icon.read_text(encoding='utf-8')
                self.assertIn(f'data-crest="{crest.name}"',source)
                self.assertIn('href="data:image/png;base64,',source)
                self.assertIn('href="data:image/webp;base64,',source)

    def test_three_transparent_base_icons_are_saved(self):
        for number in range(1,4):
            path=FRONTEND/'general'/f'gen-{number:02d}-transparent.png'
            self.assertTrue(path.is_file(),path)
            self.assertGreater(path.stat().st_size,100_000)

    def test_migration_creates_36_crest_scoped_catalogue_entries(self):
        sql=(ROOT/'data/migrations/048_barony_crest_generals.sql').read_text(encoding='utf-8')
        self.assertIn("ADD COLUMN IF NOT EXISTS crest text",sql)
        self.assertIn("('foot','Пеший'),('mounted','Конный')",sql)
        self.assertIn('FROM crests CROSS JOIN poses',sql)
        self.assertIn('UPDATE general_catalog SET active=false WHERE crest IS NULL',sql)
        self.assertIn('UPDATE player_generals pg',sql)
        self.assertIn('SET catalog_id=replacements.catalog_id,icon=replacements.image_path',sql)
        drop_constraint=sql.index('DROP CONSTRAINT IF EXISTS player_generals_icon_check')
        update_existing=sql.index('UPDATE player_generals pg')
        self.assertLess(drop_constraint,update_existing)
        self.assertIn("CHECK (icon ~ '^general/[a-zA-Z0-9_-]+\\.(webp|png|svg)$')",sql)
        self.assertIn("pg.icon LIKE '%gen-03%'",sql)
        self.assertIn('FROM player_baronies',sql)
        self.assertIn("data->>'Герб баронии'",sql)
        self.assertNotIn('RAISE EXCEPTION',sql)

    def test_api_filters_listing_and_purchase_by_barony_crest(self):
        source=(ROOT/'app/backend/army.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(source.count('active AND crest=%s'),2)
        self.assertIn('def barony_crest(conn, user_id):',source)
        self.assertIn('def crest_catalog_supported(conn):',source)
        self.assertIn("item['crest_available']",source)

    def test_cabinet_keeps_sections_visible_and_marks_restricted_hires(self):
        source=(ROOT/'app/frontend/cabinet.js').read_text(encoding='utf-8')
        self.assertIn('Promise.allSettled',source)
        self.assertIn("general.crest_available===false",source)
        self.assertIn('Часть данных недоступна',source)


if __name__=='__main__':unittest.main()
