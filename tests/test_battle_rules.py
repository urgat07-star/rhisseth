import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
from battle_rules import battle_neighbors,damage,distance,reachable,shortest_path_steps,encounter,defense_budget,choose_defenders,defender_catalog_pattern
from battle import _counterattacks,_next_actor,_drive_ai
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
        self.assertTrue(reachable((6,5),(7,5),1,set()))
        self.assertFalse(reachable((7,5),(8,5),1,set()))
        self.assertFalse(reachable((7,5),(7,6),1,set()))

    def test_speed_one_reaches_exactly_all_six_visual_neighbours(self):
        for start in ((3,2),(3,3)):
            neighbours=set(battle_neighbors(start))
            self.assertEqual(len(neighbours),6)
            for goal in neighbours:
                self.assertEqual(distance(start,goal),1,(start,goal))
                self.assertTrue(reachable(start,goal,1,set()),(start,goal))
            self.assertFalse(reachable(start,(start[0],start[1]+2),1,set()))

    def test_battle_board_has_only_six_rows(self):
        self.assertFalse(reachable((3,5),(3,6),1,set()))

    def test_shortest_path_reports_spent_movement(self):
        self.assertEqual(shortest_path_steps((1,1),(2,1),3,set()),1)
        self.assertEqual(shortest_path_steps((1,1),(3,1),3,set()),2)

    def test_higher_counterattack_strikes_adjacent_bypass(self):
        battle={'id':1,'round_number':1}
        mover={'id':1,'side':'attacker','health':10,'defense':0,'armor':0,'counterattack':1}
        guard={'id':2,'side':'defender','health':10,'active':True,'is_wall':False,'x':2,'y':2,'attack':1,'counterattack':2}
        conn=MagicMock()
        with patch('battle.random.randint',return_value=1),patch('battle._event') as event:
            self.assertTrue(_counterattacks(conn,battle,mover,(1,2),(1,3),[mover,guard]))
        self.assertEqual(mover['health'],9)
        self.assertEqual(event.call_args.args[2],'counterattack')

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
        self.assertIsNone(encounter(6,5,8,'own'))
        self.assertEqual(encounter(6,2,0,'enemy'),'bandits')

    def test_defender_budget_and_cap(self):
        self.assertEqual(defense_budget(0,0),1)
        units=[{'combat_level':1},{'combat_level':2},{'combat_level':4}]
        selected=choose_defenders(units,7,random.Random(4))
        self.assertLessEqual(len(selected),5)
        self.assertLessEqual(sum(2**(unit['combat_level']-1) for unit in selected),7)

    def test_defender_catalog_follows_owner_and_terrain(self):
        self.assertEqual(defender_catalog_pattern('Игрок','Горы'),'units/unit-%')
        self.assertEqual(defender_catalog_pattern('Компьютерное владение','Густой лес'),'units/unit-%')
        self.assertEqual(defender_catalog_pattern('Ничейная территория','Побережье / Равнина'),'units/unit-%')
        self.assertEqual(defender_catalog_pattern('Ничейная территория','Густой лес'),'units/unit-%')
        self.assertEqual(defender_catalog_pattern('Ничейная территория','Холмы'),'units/unit-%')
        self.assertEqual(defender_catalog_pattern('Ничейная территория','Полупустыня'),'units/unit-%')

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

    def test_ai_attacks_equally_weak_target_from_longest_range(self):
        battle={'id':9,'round_number':3,'last_side':'','status':'active'}
        units=[{'id':1,'side':'attacker','is_general':False,'initiative':1,'active':True,'health':5,'attacked':False,
                'attack_range':1,'moved':False,'x':3,'y':2,'defense':0,'armor':0},
               {'id':2,'side':'attacker','is_general':False,'initiative':1,'active':True,'health':5,'attacked':False,
                'attack_range':1,'moved':False,'x':5,'y':2,'defense':0,'armor':0},
               {'id':3,'side':'defender','is_general':False,'initiative':4,'active':True,'health':5,'attacked':False,
                'attack_range':3,'moved':False,'x':2,'y':2,'attack':1,'speed':1}]
        with patch('battle.random.randint',return_value=1),patch('battle._event') as event:
            _drive_ai(MagicMock(),battle,units)
        attack=next(call.args[3] for call in event.call_args_list if call.args[2]=='attack')
        self.assertEqual(attack['target_id'],2)


if __name__=='__main__':unittest.main()
