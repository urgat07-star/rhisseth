"""Package reviewed SQL migrations for restored-copy validation."""
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parents[2]
target=root/'.local/batell-v03-migrations.tar.gz'
files=sorted((root/'data/migrations').glob('*.sql'))
if [path.name[:3] for path in files]!=[f'{number:03d}' for number in range(1,34)]:
    raise SystemExit('Expected contiguous migrations 001 through 033')
target.parent.mkdir(parents=True,exist_ok=True)
with tarfile.open(target,'w:gz') as archive:
    for path in files:
        archive.add(path,arcname='data/migrations/'+path.name)
    backend=sorted((root/'app/backend').glob('*.py'))
    for path in backend:
        archive.add(path,arcname='app/backend/'+path.name)
print(f'Validation archive: {target}; migrations={len(files)}; backend files={len(backend)}; bytes={target.stat().st_size}')
