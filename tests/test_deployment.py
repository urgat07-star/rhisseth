import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
from fastapi.testclient import TestClient
from main import app


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)
        self.user={'user_id':2,'user_login':'player','role_alias':'user','csrf':'test'}
        self.headers={'X-CSRF-Token':'test'}

    def test_rejects_two_units_on_same_cell_before_database_access(self):
        body={'positions':[{'id':1,'x':1,'y':1},{'id':2,'x':1,'y':1}]}
        with patch('main.current_user',return_value=self.user),patch('battle.connect',side_effect=AssertionError('no database')):
            response=self.client.post('/api/game/battles/1/deployment',headers=self.headers,json=body)
        self.assertEqual(response.status_code,400)

    def test_accepted_deployment_locks_positions_and_saves_template(self):
        battle={'id':1,'attacker_user_id':2,'general_id':7,'status':'active','round_number':1,
                'deployment_locked':False}
        units=[{'id':11,'side':'attacker','health':10,'is_general':True,'assignment_id':None,'x':0,'y':5},
               {'id':12,'side':'attacker','health':5,'is_general':False,'assignment_id':20,'x':1,'y':1}]
        conn=MagicMock()
        conn.execute.return_value.fetchall.return_value=[(20,1)]
        body={'positions':[{'id':11,'x':0,'y':4},{'id':12,'x':1,'y':2}]}
        with patch('main.current_user',return_value=self.user),patch('battle.connect') as connect,\
             patch('battle._battle',return_value=battle),patch('battle._units',return_value=units),\
             patch('battle._drive_ai'),patch('battle._state',return_value={'battle':{'deployment_locked':True}}):
            connect.return_value.__enter__.return_value=conn
            response=self.client.post('/api/game/battles/1/deployment',headers=self.headers,json=body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(sum('INSERT INTO game_deployment_template' in call.args[0] for call in conn.execute.call_args_list),2)
        self.assertTrue(battle['deployment_locked'])


if __name__=='__main__':unittest.main()
