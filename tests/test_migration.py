import tempfile
import unittest
from pathlib import Path

from core.migration import create_backup, restore_backup


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "czon_agent"
        (self.root / "data").mkdir(parents=True)
        (self.root / "skills" / "stateful" / "runtime").mkdir(parents=True)
        (self.root / "workspace" / "users" / "u1").mkdir(parents=True)
        (self.root / "uploads").mkdir()
        (self.root / "data" / "czon_agent.db").write_bytes(b"database")
        (self.root / "data" / "czon_agent.key").write_bytes(b"key")
        (self.root / "skills" / "stateful" / "SKILL.md").write_text("skill", encoding="utf-8")
        (self.root / "skills" / "stateful" / "runtime" / "submitted.json").write_text(
            "submitted", encoding="utf-8"
        )
        (self.root / "workspace" / "users" / "u1" / "result.txt").write_text("result", encoding="utf-8")
        (self.root / ".env").write_text("CLIENT_SECRET=secret\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_encrypted_backup_restores_skill_state_and_credentials(self):
        backup = Path(self.temp_dir.name) / "migration.czon-backup"
        create_backup(self.root, backup, "123.com")
        self.assertNotIn(b"CLIENT_SECRET=secret", backup.read_bytes())

        (self.root / "data" / "czon_agent.db").write_bytes(b"changed")
        (self.root / "skills" / "stateful" / "runtime" / "submitted.json").unlink()
        restore_backup(self.root, backup, "123.com")

        self.assertEqual((self.root / "data" / "czon_agent.db").read_bytes(), b"database")
        self.assertEqual(
            (self.root / "skills" / "stateful" / "runtime" / "submitted.json").read_text(encoding="utf-8"),
            "submitted",
        )
        self.assertEqual((self.root / ".env").read_text(encoding="utf-8"), "CLIENT_SECRET=secret\n")

    def test_wrong_password_does_not_change_existing_data(self):
        backup = Path(self.temp_dir.name) / "migration.czon-backup"
        create_backup(self.root, backup, "123.com")
        database = self.root / "data" / "czon_agent.db"
        database.write_bytes(b"current")

        with self.assertRaisesRegex(RuntimeError, "密码错误"):
            restore_backup(self.root, backup, "wrong-password")

        self.assertEqual(database.read_bytes(), b"current")


if __name__ == "__main__":
    unittest.main()
