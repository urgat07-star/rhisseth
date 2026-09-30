import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
import editable_snapshot

class EditableSnapshotTests(unittest.TestCase):
    def test_applies_every_admin_editable_section(self):
        data={'format':1,'hexes':[{'q':1,'r':2,'data':{'Q':'1','R':'2'}}],
              'extractable_resources':[{'code':'wood','name':'Дерево','typical_locations':'лес','purpose':'найм','is_food':False,'active':True}],
              'produced_resources':[],'buildings':[],'hex_buildings':[],
              'generals':[{'id':1,'name':'Генерал','description':'','image_path':'general/gen-01.webp','health':10,'attack':1,'defense':1,'initiative':1,'speed':1,'logistics':10,'skills':'','experience_per_level':100,'max_level':10,'max_attack_bonus':5,'max_defense_bonus':5,'active':True}],
              'units':[{'id':2,'name':'Ополченец','troop_type':'Пехота','health':10,'armor':0,'defense':1,'attack':1,'attack_range':1,'speed':1,'initiative':1,'morale':100,'description':'','image_path':'units/unit-001.webp','price':'1 дерево','building':'','note':'','active':True,'combat_level':1,'purchasable':True,'predecessor_unit_id':None,'cost':{'wood':1}}]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshot.json';path.write_text(json.dumps(data),encoding='utf-8')
            conn=MagicMock()
            with patch.object(editable_snapshot,'SNAPSHOT',path):result=editable_snapshot.apply_editable_snapshot(conn)
        self.assertTrue(result['applied']);self.assertEqual(result['hexes'],1)
        sql='\n'.join(call.args[0] for call in conn.execute.call_args_list)
        for table in ('hexes','extractable_resources','general_catalog','unit_catalog','unit_resource_costs','hex_additional_buildings'):
            self.assertIn(table,sql)
        self.assertIn('OVERRIDING SYSTEM VALUE',sql)

    def test_pull_vds_exports_all_editable_sections(self):
        script=(Path(__file__).resolve().parents[1]/'tools/Sync-FromVds.ps1').read_text(encoding='utf-8')
        for section in ('hexes','units','extractable_resources','produced_resources','buildings','hex_buildings','generals'):
            self.assertIn("'"+section+"'",script)
        self.assertIn('editable-database.json',script)
