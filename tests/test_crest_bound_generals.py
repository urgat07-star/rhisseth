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
        self.assertIn("pg.icon LIKE '%gen-03%'",sql)
        self.assertIn('FROM player_baronies',sql)
        self.assertIn("data->>'Герб баронии'",sql)
        self.assertIn("WHERE gc.crest IS NULL",sql)
        self.assertIn('RAISE EXCEPTION',sql)

    def test_api_filters_listing_and_purchase_by_barony_crest(self):
        source=(ROOT/'app/backend/army.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(source.count('active AND crest=%s'),3)
        self.assertIn('def barony_crest(conn, user_id):',source)


if __name__=='__main__':unittest.main()
