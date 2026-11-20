import hashlib,json,tempfile,unittest
from pathlib import Path
from core.version import version_info
class VersionTests(unittest.TestCase):
 def test_release_detects_modified_code_but_ignores_customer_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'VERSION').write_text('2026.11.20.1');(p/'main.py').write_text('original')
   (p/'.release.json').write_text(json.dumps({'revision':'abc123','files':{'main.py':hashlib.sha256(b'original').hexdigest()}}))
   self.assertFalse(version_info(p)['modified'])
   (p/'data').mkdir();(p/'data/customer.txt').write_text('customer')
   self.assertFalse(version_info(p)['modified'])
   (p/'main.py').write_text('changed');self.assertTrue(version_info(p)['modified'])
 def test_missing_release_file_is_modified(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'.release.json').write_text(json.dumps({'revision':'abc','files':{'main.py':'hash'}}))
   self.assertTrue(version_info(p)['modified'])
if __name__=='__main__':unittest.main()
