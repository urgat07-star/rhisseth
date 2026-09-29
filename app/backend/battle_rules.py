"""Pure, deterministic rules used by the transactional battle API."""
from collections import deque

NEIGHBORS=((1,0),(-1,0),(0,1),(0,-1),(1,-1),(-1,1))
BATTLE_SIZE=8
BUILDING_POWER={1:0,2:1,3:2,4:2,5:4,6:3,7:5,8:10}
BUILDING_DANGER={1:0,2:0,3:0,4:0,5:2,6:1,7:3,8:0}
WALL_HEALTH={4:5,5:7,6:9,7:12,8:12}


def defender_catalog_pattern(owner_type, terrain):
    """Select the approved garrison family for capture and raid battles."""
    if owner_type != 'Ничейная территория':
        return 'units/unit-%'
    names={part.strip().casefold() for part in str(terrain or '').split('/')}
    if names & {'горы','высокогорье','холмы','предгорья'}:
        return 'units/barbarians-003.webp'  # Горцы
    if names & {'редколесье','густой лес','тайга','болото'}:
        return 'units/barbarians-001.webp'  # Лесные дикари
    if names & {'пустыня','полупустыня','саванна','вулканическая земля'}:
        return 'units/barbarians-004.webp'  # Дикари южных земель
    if names & {'равнина','луг','степь','тундра','речная долина'}:
        return 'units/barbarians-002.webp'  # Кочевники
    return 'units/barbarians-%'


def distance(a,b):
    dq=a[0]-b[0];dr=a[1]-b[1]
    return max(abs(dq),abs(dr),abs(dq+dr))


def reachable(start,goal,speed,occupied):
    if goal in occupied or not 0<=goal[0]<BATTLE_SIZE or not 0<=goal[1]<BATTLE_SIZE:
        return False
    queue=deque([(start,0)]);seen={start}
    while queue:
        cell,steps=queue.popleft()
        if cell==goal:return True
        if steps>=speed:continue
        for dq,dr in NEIGHBORS:
            point=(cell[0]+dq,cell[1]+dr)
            if 0<=point[0]<BATTLE_SIZE and 0<=point[1]<BATTLE_SIZE and point not in seen and point not in occupied:
                seen.add(point);queue.append((point,steps+1))
    return False


def damage(attack,defense,armor,attack_roll,defense_roll):
    result=attack_roll*attack-defense_roll*defense
    return max(1,result-armor) if result>0 else 0


def encounter(roll,danger,building_level,owner_relation):
    if owner_relation=='own' and building_level==8:return None
    modifier=BUILDING_DANGER.get(building_level,0)
    total=roll+danger+(-modifier if owner_relation=='own' else modifier)
    if total<=5:return None
    if total<=7:return 'animals' if building_level<4 else None
    return 'bandits'


def defense_budget(hex_defense,building_level):
    return max(1,hex_defense+BUILDING_POWER.get(building_level,0))


def choose_defenders(candidates,budget,rng):
    """Choose at most five units; every chosen level costs 2**(level-1)."""
    available=[unit for unit in candidates if 1<=unit['combat_level']<=5]
    result=[]
    for _ in range(5):
        affordable=[unit for unit in available if 2**(unit['combat_level']-1)<=budget]
        if not affordable:break
        selected=rng.choice(affordable)
        result.append(selected)
        budget-=2**(selected['combat_level']-1)
        if rng.random()<0.25:break
    return result
