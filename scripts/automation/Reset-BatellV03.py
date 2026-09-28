"""Run the authorized full tester reset after v0.3 migrations."""
import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'app/backend'))
from admin_game import _inspect, reset_baronies
from db import connect

EXPECTED={
    (1,20):[(13,6),(13,7),(14,6)],
    (3,5):[(16,7),(16,8),(17,7)],
    (4,21):[(11,11),(12,10),(13,10)],
    (5,24):[(6,17),(6,18),(7,17)],
    (6,6):[(6,14),(7,13),(7,14)],
}


def main():
    if os.environ.get('DB_HOST')!='127.0.0.1':
        raise RuntimeError('Expected local VDS PostgreSQL endpoint')
    with connect() as conn:
        zones={}
        for barony_id,user_id,q,r in conn.execute('''SELECT b.id,b.user_id,s.q,s.r
            FROM player_baronies b JOIN barony_start_hexes s ON s.barony_id=b.id
            ORDER BY b.id,s.position''').fetchall():
            zones.setdefault((barony_id,user_id),[]).append((q,r))
        if zones!=EXPECTED:raise RuntimeError('Start zones differ from reviewed barony baseline')
        preview=_inspect(conn)
        if not preview['ready'] or preview['baronies']!=5 or preview['recorded_start_hexes']!=15:
            raise RuntimeError('Full reset preview is not ready')
        admin=conn.execute('''SELECT u.user_id FROM users u JOIN roles r USING(role_id)
            WHERE r.role_alias='admin' ORDER BY u.user_id LIMIT 1''').fetchone()
        if not admin:raise RuntimeError('No administrator account for reset audit')
    class Request:
        state=SimpleNamespace(user={'role_alias':'admin','user_id':admin[0]})
        async def json(self):
            return {'confirmation':'СБРОСИТЬ ТЕСТ','expected_turn':preview['turn']}
    result=asyncio.run(reset_baronies(Request()))
    with connect() as conn:
        owned=conn.execute("SELECT count(*) FROM hexes WHERE data->>'Тип владельца'='Игрок'").fetchone()[0]
        wallets=conn.execute('''SELECT count(*) FROM player_baronies b JOIN game_wallets w
            ON w.user_id=b.user_id WHERE w.gold=300''').fetchone()[0]
        generals=conn.execute('SELECT count(*) FROM player_generals').fetchone()[0]
        turn=conn.execute('SELECT turn_number FROM game_clock WHERE id=true').fetchone()[0]
        if (owned,wallets,generals,turn)!=(15,5,0,0):
            raise RuntimeError('Reset verification failed')
    print(f'Full test reset verified: baronies={result["baronies"]}; start_hexes={owned}; wallets_300={wallets}; generals={generals}; turn={turn}')


if __name__=='__main__':main()
