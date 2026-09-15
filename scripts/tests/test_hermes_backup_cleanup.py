"""在临时目录验证备份保留和删除边界，不访问生产备份。"""

import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest


spec = importlib.util.spec_from_file_location(
    "backup_cleanup", Path(__file__).resolve().parents[1] / "ops/hermes_backup_cleanup.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BackupCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = time.time()

    def group(self, name, age=100, filename="state.db.backup"):
        path = self.root / name
        path.mkdir()
        (path / filename).write_text("测试备份", encoding="utf-8")
        stamp = self.now - age * 86400
        os.utime(path / filename, (stamp, stamp))
        os.utime(path, (stamp, stamp))
        return path

    def test_preview_and_delete_keep_latest_even_when_old(self):
        old = self.group("session_manual_cleanup_20200101_000000")
        newest = self.group("session_manual_cleanup_20210101_000000")
        preview = module.cleanup(self.root, now=self.now)
        self.assertEqual(preview["candidates"], [old.name])
        self.assertTrue(old.exists())
        result = module.cleanup(self.root, delete=True, now=self.now)
        self.assertEqual(result["deleted"], [old.name])
        self.assertTrue(newest.exists())

    def test_recent_content_and_exact_boundary_are_retained(self):
        for index, age in enumerate([1, 90]):
            self.group(f"session_retention_2020010{index + 1}_000000", age,
                       "deleted-over-retention.txt")
        self.assertEqual(module.cleanup(self.root, delete=True, now=self.now)["deleted"], [])

    def test_old_manifest_is_removed_without_manual_backups(self):
        path = self.group("session_retention_20200101_000000",
                          filename="deleted-over-retention.txt")
        self.assertEqual(module.cleanup(self.root, delete=True, now=self.now)["deleted"],
                         [path.name])

    def test_unknown_content_and_unknown_directory_are_retained(self):
        for name in ["session_retention_20200101_000000", "unrelated"]:
            path = self.group(name, filename="unknown.txt")
            self.assertTrue(path.exists())
        self.assertEqual(module.cleanup(self.root, delete=True, now=self.now)["deleted"], [])

    def test_symlink_directory_and_file_are_retained(self):
        outside = self.root / "outside"
        outside.mkdir()
        target = outside / "important"
        target.write_text("不可删除", encoding="utf-8")
        (self.root / "session_retention_20200101_000000").symlink_to(
            outside, target_is_directory=True
        )
        group = self.root / "session_retention_20200102_000000"
        group.mkdir()
        (group / "deleted-over-retention.txt").symlink_to(target)
        os.utime(group, (0, 0))
        self.assertEqual(module.cleanup(self.root, delete=True, now=self.now)["deleted"], [])
        self.assertTrue(target.exists())

    def test_symlink_root_is_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            module.cleanup(alias, delete=True, now=self.now)

    def test_incomplete_newer_group_does_not_displace_latest_backup(self):
        valid = self.group("session_manual_cleanup_20200101_000000")
        self.group("session_manual_cleanup_20210101_000000", filename="sessions.json")
        result = module.cleanup(self.root, delete=True, now=self.now)
        self.assertEqual(result["protected"], [valid.name])
        self.assertEqual(result["deleted"], [])


if __name__ == "__main__":
    unittest.main()
