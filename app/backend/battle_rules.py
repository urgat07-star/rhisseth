"""Pure, deterministic rules used by the transactional battle API."""
from collections import deque

NEIGHBORS=((1,0),(-1,0),(0,1),(0,-1),(1,-1),(-1,1))
BATTLE_WIDTH=8
BATTLE_HEIGHT=6
BUILDING_POWER={1:0,2:1,3:2,4:2,5:4,6:3,7:5,8:10}
BUILDING_DANGER={1:0,2:0,3:0,4:0,5:2,6:1,7:3,8:0}
WALL_HEALTH={4:5,5:7,6:9,7:12,8:12}


def defender_catalog_pattern(owner_type, terrain):
    """Province raids and captures use regular units for every owner type.

    Barbarian templates are reserved for a future explicit invasion event and
    must not be selected as an ordinary provincial garrison.
    """
    return 'units/unit-%'


def distance(a,b):
    """Hex distance for the odd-row offset coordinates used by the battle UI."""
    aq=a[0]-(a[1]-(a[1]&1))//2
    bq=b[0]-(b[1]-(b[1]&1))//2
    dq=aq-bq;dr=a[1]-b[1]
    return max(abs(dq),abs(dr),abs(dq+dr))


def battle_neighbors(cell):
    """Return the six visual neighbours of a cell on the odd-row offset grid."""
    x,y=cell
    diagonals=((1,1),(0,1),(1,-1),(0,-1)) if y&1 else ((0,1),(-1,1),(0,-1),(-1,-1))
    return ((x+1,y),(x-1,y),*((x+dx,y+dy) for dx,dy in diagonals))


def reachable(start,goal,speed,occupied):
    if goal in occupied or not 0<=goal[0]<BATTLE_WIDTH or not 0<=goal[1]<BATTLE_HEIGHT:
        return False
    queue=deque([(start,0)]);seen={start}
    while queue:
        cell,steps=queue.popleft()
        if cell==goal:return True
        if steps>=speed:continue
        for point in battle_neighbors(cell):
            if 0<=point[0]<BATTLE_WIDTH and 0<=point[1]<BATTLE_HEIGHT and point not in seen and point not in occupied:
                seen.add(point);queue.append((point,steps+1))
    return False

def shortest_path_steps(start,goal,speed,occupied):
    if goal in occupied:return None
    queue=deque([(start,0)]);seen={start}
    while queue:
        cell,steps=queue.popleft()
        if cell==goal:return steps
        if steps>=speed:continue
        for point in battle_neighbors(cell):
            if 0<=point[0]<BATTLE_WIDTH and 0<=point[1]<BATTLE_HEIGHT and point not in seen and point not in occupied:
                seen.add(point);queue.append((point,steps+1))
    return None


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
