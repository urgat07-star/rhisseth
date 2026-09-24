"""Fixed-price ransom for generals captured by another player."""
from fastapi import APIRouter, HTTPException, Request
from db import connect
from army import home_hex

router = APIRouter()
RANSOM_GOLD = 100


@router.get('/api/cabinet/diplomacy')
def diplomacy(request: Request):
    user_id = request.state.user['user_id']
    with connect() as conn:
        wallet = conn.execute('SELECT gold FROM game_wallets WHERE user_id=%s',(user_id,)).fetchone()
        rows = conn.execute('''SELECT pg.id,pg.name,pg.level,pg.experience,pg.attack_bonus,pg.defense_bonus,
            pg.user_id,pg.captor_user_id,COALESCE(capturing.name,''),COALESCE(capturing.crest,''),
            COALESCE(owner.name,''),COALESCE(owner.crest,'')
            FROM player_generals pg
            LEFT JOIN player_baronies capturing ON capturing.user_id=pg.captor_user_id
            LEFT JOIN player_baronies owner ON owner.user_id=pg.user_id
            WHERE pg.status='captive' AND (pg.user_id=%s OR pg.captor_user_id=%s)
            ORDER BY pg.captured_at DESC,pg.id''',(user_id,user_id)).fetchall()
    return {'gold':wallet[0] if wallet else 0,'ransom_gold':RANSOM_GOLD,
            'captives':[{'id':row[0],'name':row[1],'level':row[2],'experience':row[3],
                         'attack_bonus':row[4],'defense_bonus':row[5],
                         'mine':row[6]==user_id,'captor_barony':row[8],
                         'captor_crest':row[9],'owner_barony':row[10],
                         'owner_crest':row[11]} for row in rows]}


@router.post('/api/cabinet/diplomacy/generals/{general_id}/ransom')
def pay_ransom(general_id: int, request: Request):
    user_id = request.state.user['user_id']
    with connect() as conn:
        general = conn.execute('''SELECT user_id,captor_user_id,status FROM player_generals
            WHERE id=%s FOR UPDATE''',(general_id,)).fetchone()
        if not general or general[0]!=user_id or general[2]!='captive' or general[1] is None:
            raise HTTPException(409,'Генерал не находится в плену у другого игрока')
        captor_id = general[1]
        balances = dict(conn.execute('SELECT user_id,gold FROM game_wallets WHERE user_id IN (%s,%s) ORDER BY user_id FOR UPDATE',
                                     (user_id,captor_id)).fetchall())
        if balances.get(user_id,0)<RANSOM_GOLD:
            raise HTTPException(409,'Недостаточно золота для выкупа')
        if captor_id not in balances:
            raise HTTPException(409,'У пленившего игрока нет казны')
        home=home_hex(conn,user_id)
        if not home: raise HTTPException(409,'У баронии нет территории для возвращения генерала')
        conn.execute('UPDATE game_wallets SET gold=gold-%s WHERE user_id=%s',(RANSOM_GOLD,user_id))
        conn.execute('UPDATE game_wallets SET gold=gold+%s WHERE user_id=%s',(RANSOM_GOLD,captor_id))
        conn.execute('''UPDATE player_generals SET status='active',captor_user_id=NULL,captured_at=NULL,
            q=%s,r=%s,previous_q=NULL,previous_r=NULL WHERE id=%s''',(*home,general_id))
        conn.execute("INSERT INTO game_gold_ledger(user_id,amount,reason,related_general_id) VALUES (%s,%s,'ransom_paid',%s)",
                     (user_id,-RANSOM_GOLD,general_id))
        conn.execute("INSERT INTO game_gold_ledger(user_id,amount,reason,related_general_id) VALUES (%s,%s,'ransom_received',%s)",
                     (captor_id,RANSOM_GOLD,general_id))
    return {'released':True,'general_id':general_id,'gold_spent':RANSOM_GOLD}
