"""Linux 部署器的目录句柄与符号链接隔离回归。"""

import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "posix", "部署器仅面向 Linux")
class TestPrivateDeploymentPaths(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ["DOUYIN_TEST_REPO"]) if "DOUYIN_TEST_REPO" in os.environ else Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location("douyin_installer_test", root / "ops/douyin-login/install.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module.HOME = Path(self.temp.name) / "home"
        self.module.HOME.mkdir()
        self.account_patch = patch.object(self.module.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()))
        self.account_patch.start()
        self.addCleanup(self.account_patch.stop)

    def test_directory_symlink_cannot_redirect_root_write(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.module.HOME / "plugins").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.module.write_user_file("plugins/douyin-login/plugin.yaml", "内容")
        self.assertEqual(list(outside.iterdir()), [])

    def test_leaf_symlink_is_not_read_and_atomic_write_replaces_link(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("保持原样", encoding="utf-8")
        (self.module.HOME / "config.yaml").symlink_to(outside)
        with self.assertRaises(OSError):
            self.module.read_user_file("config.yaml")
        self.module.write_user_file("config.yaml", "新配置", 0o600)
        self.assertEqual(outside.read_text(encoding="utf-8"), "保持原样")
        self.assertEqual(self.module.read_user_file("config.yaml")[0], "新配置")
        self.assertFalse((self.module.HOME / "config.yaml").is_symlink())
        self.assertFalse(list(self.module.HOME.glob(".douyin-*.tmp")))

    def test_parent_traversal_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.module.write_user_file("../outside/config.yaml", "拒绝")


if __name__ == "__main__":
    unittest.main()
