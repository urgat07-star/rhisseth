import unittest
from pathlib import Path


class BattleFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script=(Path(__file__).resolve().parents[1]/'app/frontend/app.js').read_text(encoding='utf-8')

    def test_partial_move_preserves_current_ranged_unit_selection(self):
        self.assertIn('async function battleCommand(path,payload,preserveUnitId=null)',self.script)
        self.assertIn('data.eligible_unit_ids.includes(preserveUnitId)',self.script)
        self.assertIn('},movingUnitId);',self.script)


if __name__=='__main__':
    unittest.main()
