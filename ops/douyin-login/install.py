#!/usr/bin/env python3
"""81 服务器的显式部署入口；源码必须已提交并推送。"""

import argparse
from contextlib import contextmanager
import grp
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
HOME = Path("/home/hermes/.hermes")
DEST = Path("/opt/hermes-douyin")
STATE = Path("/var/lib/hermes-douyin")


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def atomic_write(path, data, mode=0o600, uid=0, gid=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(data.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
            os.fchmod(f.fileno(), mode)
            os.fchown(f.fileno(), uid, gid)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


@contextmanager
def user_directory(parts, create=False):
    if any(part in {"", ".", ".."} or "/" in part for part in parts):
        raise RuntimeError("用户目录路径无效")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    account = pwd.getpwnam("hermes")
    fd = os.open(HOME, flags)
    try:
        for part in parts:
            created = False
            try:
                child = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, mode=0o755, dir_fd=fd)
                child = os.open(part, flags, dir_fd=fd)
                created = True
            os.close(fd)
            fd = child
            if created:
                os.fchown(fd, account.pw_uid, account.pw_gid)
        yield fd
    finally:
        os.close(fd)


def read_user_file(relative):
    parts = Path(relative).parts
    with user_directory(parts[:-1]) as directory:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(fd, "r", encoding="utf-8") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError("用户配置不是普通文件")
            return f.read(), stat.S_IMODE(info.st_mode)


def write_user_file(relative, data, mode=0o644):
    parts = Path(relative).parts
    account = pwd.getpwnam("hermes")
    with user_directory(parts[:-1], create=True) as directory:
        temporary = ".douyin-" + uuid.uuid4().hex + ".tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
                os.fchown(f.fileno(), account.pw_uid, account.pw_gid)
                os.fchmod(f.fileno(), mode)
            os.replace(temporary, parts[-1], src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass


def owner_from_current_mapping():
    mapping = json.loads(read_user_file("sessions/sessions.json")[0])
    owners = set()
    for value in mapping.values():
        origin = value.get("origin", {})
        if value.get("platform") == "qqbot" and value.get("chat_type") == "dm":
            chat, user = origin.get("chat_id"), origin.get("user_id")
            if chat and user and chat == user:
                owners.add(user)
    if len(owners) != 1:
        raise RuntimeError("无法从当前会话唯一确定 QQ 私聊账号，拒绝扩大权限")
    owner = owners.pop()
    if not re.fullmatch(r"[-A-Za-z0-9_]+", owner):
        raise RuntimeError("QQ 账号标识格式无效")
    return owner


def activate_plugin():
    import copy
    import yaml

    owner = owner_from_current_mapping()
    contents, mode = read_user_file("config.yaml")
    original = yaml.safe_load(contents)
    updated = copy.deepcopy(original)
    enabled = updated.setdefault("plugins", {}).setdefault("enabled", [])
    toolsets = updated.setdefault("platform_toolsets", {}).setdefault("qqbot", [])
    if not isinstance(enabled, list) or not isinstance(toolsets, list):
        raise RuntimeError("现有插件或 QQ 工具组配置格式不兼容")
    if "douyin-login" not in enabled:
        enabled.append("douyin-login")
    if "douyin" not in toolsets:
        toolsets.append("douyin")
    read_user_file("skills/hermes-md-locator/SKILL.md")
    for name in ("__init__.py", "plugin.yaml"):
        write_user_file("plugins/douyin-login/" + name, (ROOT / "ops/douyin-plugin" / name).read_text())
    write_user_file("skills/hermes-md-locator/SKILL.md", (ROOT / "skills_builtin/hermes-md-locator/SKILL.md").read_text())
    if updated != original:
        write_user_file("config.yaml", yaml.safe_dump(updated, allow_unicode=True, sort_keys=False), mode)
    atomic_write(
        Path("/etc/systemd/system/hermes-gateway.service.d/douyin.conf"),
        '[Service]\nEnvironment="DOUYIN_OWNER_QQ_USER_ID=' + owner + '"\n',
    )
    run("systemctl", "daemon-reload")
    print("抖音插件及指定私聊权限已配置；尚未重启 Hermes 网关。")


def prepare(expected):
    version = re.match(r"systemd (\d+)", subprocess.check_output(["systemctl", "--version"], text=True))
    if version is None or int(version.group(1)) < 254:
        raise RuntimeError("独立登录服务要求 systemd 254 或更新版本")
    run("apt-get", "install", "--no-install-recommends", "-y", "python3-venv", "chromium", "chromium-sandbox", "xvfb", "xauth", "fonts-noto-cjk")
    try:
        grp.getgrnam("hermes-douyin")
    except KeyError:
        run("groupadd", "--system", "hermes-douyin")
    try:
        pwd.getpwnam("douyin-runner")
    except KeyError:
        run("useradd", "--system", "--gid", "hermes-douyin", "--home-dir", str(STATE), "--shell", "/usr/sbin/nologin", "douyin-runner")
    runner = pwd.getpwnam("douyin-runner")
    group = grp.getgrnam("hermes-douyin")
    hermes = pwd.getpwnam("hermes")
    run("usermod", "-aG", "hermes-douyin", "hermes")
    DEST.mkdir(mode=0o755, exist_ok=True)
    STATE.mkdir(mode=0o700, exist_ok=True)
    os.chown(STATE, runner.pw_uid, group.gr_gid)
    os.chmod(STATE, 0o700)
    for name in ("service.py", "requirements.txt"):
        shutil.copyfile(ROOT / "ops/douyin-login" / name, DEST / name)
        os.chmod(DEST / name, 0o644)
    if not (DEST / "venv/bin/python").exists():
        run("python3", "-m", "venv", str(DEST / "venv"))
    run(str(DEST / "venv/bin/python"), "-m", "pip", "install", "-r", str(DEST / "requirements.txt"))
    atomic_write(
        Path("/etc/hermes-douyin.env"),
        f"DOUYIN_ALLOWED_UID={hermes.pw_uid}\nDOUYIN_EXPECTED_ACCOUNT={expected}\n",
    )
    atomic_write(Path("/etc/systemd/system/hermes-douyin.service"), (ROOT / "ops/douyin-login/hermes-douyin.service").read_text(), 0o644)
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "hermes-douyin.service")
    print("独立抖音服务已安装并启动；没有重启 Hermes、没有上传或发布视频。")


def main():
    parser = argparse.ArgumentParser(description="部署独立抖音登录服务")
    parser.add_argument("--expected-account")
    parser.add_argument("--activate-plugin", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("必须由 root 执行")
    if args.activate_plugin:
        activate_plugin()
    elif args.expected_account and re.fullmatch(r"[-A-Za-z0-9_]{1,100}", args.expected_account):
        prepare(args.expected_account)
    else:
        parser.error("必须提供准确的 --expected-account，或使用 --activate-plugin")


if __name__ == "__main__":
    main()
