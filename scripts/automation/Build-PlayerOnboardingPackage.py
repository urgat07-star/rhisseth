# Release review 2026-09-18 (0.0.2): Build the exact reviewed package; excludes user data, reports and secrets.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Build the exact reviewed package; excludes user data, reports and secrets."""
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
names = (
    'app/backend/main.py', 'app/backend/site_auth.py', 'app/backend/game_start.py',
    'app/backend/hex_rules.py', 'app/frontend/index.html', 'app/frontend/app.js',
    'app/frontend/styles.css', 'app/frontend/create-barony.html',
    'app/frontend/cabinet.html', 'app/frontend/crests/gerb_1.png',
    'app/frontend/crests/gerb_2.png', 'app/frontend/crests/gerb_3.png',
    'app/frontend/crests/gerb_4.png', 'app/frontend/crests/gerb_5.png',
    'data/migrations/006_player_onboarding.sql',
    'data/migrations/007_player_cabinet.sql', 'app/backend/player_cabinet.py',
    'app/frontend/cabinet.js', 'data/migrations/008_player_barony_rename.sql',
)
if any(not (root / name).is_file() for name in names):
    raise SystemExit('Required reviewed file missing')
output = root / 'temp/player-onboarding.tar'
with tarfile.open(output, 'w') as archive:
    for name in names:
        archive.add(root / name, arcname=name, recursive=False)
print('Created reviewed package:', output)
