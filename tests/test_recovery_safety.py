"""Isolated safety checks: no SSH, infrastructure, real data, or credentials."""
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts/automation'
sys.path.insert(0,str(SCRIPTS))
from rhisseth_deploy import inspect_archive,validate_schema

class RecoverySafety(unittest.TestCase):
    def test_release_cannot_omit_or_modify_applied_migrations(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            migrations = repo/'data/migrations'
            migrations.mkdir(parents=True)
            first = migrations/'001_initial.sql'
            first.write_text('CREATE TABLE example(id integer);')
            expected = hashlib.sha256(first.read_bytes()).hexdigest()
            manifest = {'schema_migrations':[first.name],'migrations_sha256':{first.name:expected}}
            self.assertEqual(validate_schema(repo,manifest),[])
            (migrations/'002_new.sql').write_text('ALTER TABLE example ADD COLUMN value text;')
            self.assertEqual(validate_schema(repo,manifest),['002_new.sql'])
            first.write_text('CREATE TABLE example(id text);')
            with self.assertRaisesRegex(RuntimeError,'modified'):
                validate_schema(repo,manifest)
            first.unlink()
            with self.assertRaisesRegex(RuntimeError,'prefix'):
                validate_schema(repo,manifest)

    def test_untrusted_archive_paths_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'unsafe.tar.gz'
            for name,kind in (('../outside',tarfile.REGTYPE),('project/escape',tarfile.SYMTYPE)):
                with tarfile.open(path,'w:gz') as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    if kind==tarfile.SYMTYPE:
                        member.linkname='/etc/shadow'
                    archive.addfile(member,io.BytesIO(b''))
                expected = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(RuntimeError):
                    inspect_archive(path,expected)
                with self.assertRaisesRegex(RuntimeError,'SHA256 mismatch'):
                    inspect_archive(path,'0'*64)
            self.assertFalse((Path(directory).parent/'outside').exists())

    @unittest.skipIf(os.name == 'nt', 'Storage service requires Linux flock')
    def test_failed_transfer_preserves_backups_and_success_applies_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = dt.datetime.now(dt.timezone.utc)
            old = 'rhisseth-20260901T060000Z-11111111.tar.gz'
            recent = 'rhisseth-20260915T060000Z-22222222.tar.gz'
            fresh = 'rhisseth-20260916T060000Z-33333333.tar.gz'
            for name,age in ((old,8),(recent,1)):
                (root/name).write_bytes(b'previous')
                (root/(name+'.json')).write_text(json.dumps({'name':name,'size':8,'sha256':hashlib.sha256(b'previous').hexdigest(),'completed_utc':(now-dt.timedelta(days=age)).isoformat()}))
            harness = 'import sys,os; from pathlib import Path; import rhisseth_storage as s; s.ROOT=Path(sys.argv[1]); os.environ["SSH_ORIGINAL_COMMAND"]=sys.argv[2]; raise SystemExit(s.main())'
            def invoke(command,data=b''):
                return subprocess.run([sys.executable,'-c',harness,str(root),command],input=data,capture_output=True,cwd=SCRIPTS)
            payload = b'new archive fixture'
            expected = hashlib.sha256(payload).hexdigest()
            bad = invoke(f'put {fresh} {len(payload)} {expected}',b'corrupt')
            self.assertNotEqual(bad.returncode,0)
            self.assertTrue((root/old).exists())
            self.assertTrue((root/recent).exists())
            self.assertFalse((root/fresh).exists())
            good = invoke(f'put {fresh} {len(payload)} {expected}',payload)
            self.assertEqual(good.returncode,0,good.stderr.decode())
            self.assertFalse((root/old).exists())
            self.assertTrue((root/recent).exists())
            self.assertEqual(invoke('get '+fresh).stdout,payload)
            self.assertEqual(len(json.loads(invoke('list').stdout)),2)
            self.assertNotEqual(invoke('get ../../etc/shadow').returncode,0)
            self.assertNotEqual(invoke(f'put {fresh} {len(payload)} {expected}',payload).returncode,0)

if __name__=='__main__':
    unittest.main()
