#!/usr/bin/env python3
"""经当次人工授权后，临时暴露现有浏览器的回环验证窗口。"""

import argparse
import os
from pathlib import Path
import secrets
import shutil
import socket
import string
import subprocess
import time

UNITS = ("hermes-douyin-manual-web.service", "hermes-douyin-manual-vnc.service")
PASSWORD_FILE = Path("/run/hermes-douyin/manual.pass")


def start_units(pid, display, authority):
    subprocess.run([
        "systemd-run", "--unit=hermes-douyin-manual-vnc", "--property=RuntimeMaxSec=15min",
        "nsenter", "--target", pid, "--mount", "--", "runuser", "-u", "douyin-runner", "--",
        "/usr/bin/x11vnc", "-norc", "-nocmds", "-localhost", "-listen", "127.0.0.1", "-no6",
        "-rfbport", "5905", "-passwdfile", "rm:" + str(PASSWORD_FILE), "-display", display,
        "-auth", authority, "-noshm", "-noxdamage", "-nosel", "-forever",
    ], check=True)
    subprocess.run([
        "systemd-run", "--unit=hermes-douyin-manual-web", "--property=RuntimeMaxSec=15min",
        "--property=User=douyin-runner", "--property=Group=hermes-douyin",
        "/usr/bin/websockify", "--web=/usr/share/novnc", "127.0.0.1:6085", "127.0.0.1:5905",
    ], check=True)
    for port in (5905, 6085):
        deadline = time.monotonic() + 5
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("临时窗口监听启动失败")
                time.sleep(0.1)


def close_window():
    subprocess.run(["systemctl", "stop", *UNITS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for unit in UNITS:
        state = subprocess.check_output(["systemctl", "show", unit, "-p", "ActiveState", "--value"], text=True).strip()
        if state not in {"inactive", "failed"}:
            raise RuntimeError("临时窗口未完全停止，请人工检查")
    subprocess.run(["systemctl", "reset-failed", *UNITS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PASSWORD_FILE.unlink(missing_ok=True)


def open_window():
    import pwd

    for command in ("x11vnc", "websockify", "nsenter"):
        if not shutil.which(command):
            raise RuntimeError("请先安装临时验证窗口的可选依赖")
    if not Path("/usr/share/novnc/vnc.html").is_file():
        raise RuntimeError("缺少 noVNC 页面")
    for unit in UNITS:
        if subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0:
            raise RuntimeError("窗口已存在；请先关闭旧窗口")
    group = subprocess.check_output(["systemctl", "show", "hermes-douyin.service", "-p", "ControlGroup", "--value"], text=True).strip()
    if not group.startswith("/system.slice/hermes-douyin.service"):
        raise RuntimeError("浏览器服务控制组不符")
    runner = pwd.getpwnam("douyin-runner")
    candidates = []
    for pid in (Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.procs").read_text().split():
        proc = Path("/proc") / pid
        try:
            arguments = (proc / "cmdline").read_bytes().split(b"\0")
            if proc.stat().st_uid == runner.pw_uid and arguments[:2] == [b"/opt/hermes-douyin/venv/bin/python", b"/opt/hermes-douyin/service.py"]:
                candidates.append(pid)
        except FileNotFoundError:
            continue
    if len(candidates) != 1:
        raise RuntimeError("无法唯一确定现有浏览器服务进程")
    pid = candidates[0]
    environment = dict(part.split(b"=", 1) for part in (Path("/proc") / pid / "environ").read_bytes().split(b"\0") if b"=" in part)
    display, authority = environment[b"DISPLAY"].decode(), environment[b"XAUTHORITY"].decode()
    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    fd = os.open(PASSWORD_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(password + "\n")
        os.fchown(f.fileno(), runner.pw_uid, runner.pw_gid)
    try:
        start_units(pid, display, authority)
    except BaseException:
        close_window()
        raise
    print("临时窗口已启动，十五分钟后自动关闭。VNC 临时密码：" + password)
    print("仅通过 SSH 转发访问：http://127.0.0.1:16085/vnc.html?resize=scale&autoconnect=1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抖音临时人工验证窗口")
    parser.add_argument("action", choices=("open", "close"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("须经授权由 root 运维执行")
    open_window() if args.action == "open" else close_window()
