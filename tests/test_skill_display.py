import tempfile,unittest
from pathlib import Path
from core.skills import describe_skills
class SkillDisplayTests(unittest.TestCase):
 def test_metadata_and_legacy_fallback(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   for name,metadata in [('named','metadata:\n  display_name: 中文技能\n  display_description: 中文用途\n'),('legacy','')]:
    p=root/name;p.mkdir();(p/'SKILL.md').write_text(f'---\nname: {name}\ndescription: original\n{metadata}---\nInstructions unchanged\n')
   rows={r['name']:r for r in describe_skills(root,{})}
   self.assertEqual(rows['named']['display_name'],'中文技能');self.assertEqual(rows['named']['display_description'],'中文用途')
   self.assertEqual(rows['legacy']['display_name'],'legacy');self.assertEqual(rows['legacy']['display_description'],'original')
if __name__=='__main__':unittest.main()
