# Release review 2026-09-18 (0.0.2): Local-only checks: no SSH, Docker daemon or infrastructure access.
# Details: docs/releases/0.0.2-changes-2026-09-18.md.
"""Local-only checks: no SSH, Docker daemon or infrastructure access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('entrypoint',Path(__file__).resolve().parents[1]/'deploy/recovery/entrypoint.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)

class ConfigTests(unittest.TestCase):
    def config(self):
        return {'target':{'ip':'8.8.8.8','username':'root','password':'synthetic-test-secret'},'backup':{'ip':'1.1.1.1'},'instance':{'domain':'example.org','tls_mode':'test'}}

    def test_private_target_rejected_before_credentials_written(self):
        config=self.config()
        config['target']['ip']='10.210.52.56'
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                entry.prepare(config,Path(folder))
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_password_only_in_ephemeral_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            settings=entry.prepare(self.config(),directory)
            self.assertNotIn('synthetic-test-secret',settings.read_text())
            data=json.loads(settings.read_text())
            self.assertFalse(data['enforce_runner'])
            self.assertEqual(data['instance']['test_ip'],'8.8.8.8')
            self.assertEqual(json.loads((directory/'target.json').read_text())['password'],'synthetic-test-secret')

if __name__=='__main__':
    unittest.main()
