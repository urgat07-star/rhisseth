import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
from battle_rules import damage,distance,reachable,encounter,defense_budget,choose_defenders
from battle import _next_actor,_drive_ai
from unittest.mock import MagicMock,patch


class BattleRuleTests(unittest.TestCase):
    def test_damage_uses_d6_comparison_armor_and_minimum(self):
        self.assertEqual(damage(2,2,0,2,2),0)
        self.assertEqual(damage(2,1,99,2,1),1)
        self.assertEqual(damage(3,1,1,6,1),16)

    def test_movement_cannot_cross_occupied_hex(self):
        self.assertEqual(distance((0,0),(1,1)),2)
        self.assertTrue(reachable((0,0),(2,0),2,set()))
        self.assertFalse(reachable((0,0),(2,0),2,{(1,0)}))
        self.assertTrue(reachable((6,7),(7,7),1,set()))
        self.assertFalse(reachable((7,7),(8,7),1,set()))
        self.assertFalse(reachable((7,7),(7,8),1,set()))

    def test_wall_blocks_passage_but_spear_and_archer_reach_across(self):
        wall=(6,5)
        attacker=(5,5)
        defender=(7,5)
        self.assertFalse(reachable(attacker,wall,3,{wall}))
        self.assertFalse(reachable(attacker,defender,2,{wall}))
        self.assertEqual(distance(attacker,defender),2)
        self.assertLessEqual(distance(attacker,defender),2)  # spear range
        self.assertLessEqual(distance(attacker,defender),3)  # bow range

    def test_encounter_respects_building_and_capital(self):
        self.assertEqual(encounter(6,0,0,'neutral'),'animals')
        self.assertIsNone(encounter(6,0,4,'neutral'))
        self.assertIsNone(encounter(6,5,7,'own'))
        self.assertEqual(encounter(6,2,0,'enemy'),'bandits')

    def test_defender_budget_and_cap(self):
        self.assertEqual(defense_budget(0,0),1)
        units=[{'combat_level':1},{'combat_level':2},{'combat_level':4}]
        selected=choose_defenders(units,7,random.Random(4))
        self.assertLessEqual(len(selected),5)
        self.assertLessEqual(sum(2**(unit['combat_level']-1) for unit in selected),7)

    def test_initiative_bonus_and_alternating_tie(self):
        units=[{'id':1,'side':'attacker','initiative':2,'active':True,'health':5,'attacked':False,'attack_range':1,'moved':False},
               {'id':2,'side':'defender','initiative':3,'active':True,'health':5,'attacked':False,'attack_range':1,'moved':False}]
        self.assertEqual(_next_actor({'round_number':1,'last_side':''},units)[0],'attacker')
        self.assertEqual(_next_actor({'round_number':3,'last_side':''},units)[0],'defender')
        units[1]['initiative']=2
        self.assertEqual(_next_actor({'round_number':3,'last_side':'attacker'},units)[0],'defender')

    def test_defender_action_runs_before_lower_initiative_attacker(self):
        battle={'id':8,'round_number':3,'last_side':'','status':'active'}
        units=[{'id':1,'side':'attacker','is_general':False,'initiative':1,'active':True,'health':5,'attacked':False,
                'attack_range':1,'moved':False,'x':1,'y':1,'defense':0,'armor':0},
               {'id':2,'side':'defender','is_general':False,'initiative':4,'active':True,'health':5,'attacked':False,
                'attack_range':1,'moved':False,'x':2,'y':1,'attack':1,'speed':1}]
        with patch('battle.random.randint',return_value=1),patch('battle._event'):
            _drive_ai(MagicMock(),battle,units)
        self.assertEqual(units[0]['health'],4)
        self.assertTrue(units[1]['attacked'])
        self.assertEqual(_next_actor(battle,units)[0],'attacker')


if __name__=='__main__':unittest.main()
