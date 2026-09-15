#!/usr/bin/env python3
"""季度清理 Hermes 旧备份；默认只预演，生产路径不可通过参数修改。"""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import stat
import time


BACKUP_ROOT = Path("/home/hermes/backups")
GROUP = re.compile(r"session_(manual_cleanup|retention)_(\d{8}_\d{6})")
ALLOWED = {
    "manual_cleanup": {"state.db.backup", "sessions.json"},
    "retention": {"deleted-over-retention.txt"},
}


def cleanup(root, *, delete=False, now=None):
    root = Path(root)
    if root.is_symlink() or root.resolve() != root.absolute():
        raise ValueError("拒绝符号链接或非规范备份根目录")
    cutoff = (time.time() if now is None else now) - 90 * 86400
    report = {"mode": "delete" if delete else "dry-run", "protected": [],
              "candidates": [], "deleted": [], "skipped": []}
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with_fd = os.open(root, flags)
    try:
        groups = []
        for name in sorted(os.listdir(with_fd)):
            match = GROUP.fullmatch(name)
            if not match:
                report["skipped"].append(name)
                continue
            try:
                stamp = datetime.datetime.strptime(match[2], "%Y%m%d_%H%M%S").timestamp()
            except ValueError:
                report["skipped"].append(name)
                continue
            info = os.stat(name, dir_fd=with_fd, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                report["skipped"].append(name)
                continue
            if match[1] == "manual_cleanup":
                fd = os.open(name, flags, dir_fd=with_fd)
                try:
                    try:
                        database = os.stat("state.db.backup", dir_fd=fd,
                                           follow_symlinks=False)
                    except FileNotFoundError:
                        report["skipped"].append(name)
                        continue
                    if not stat.S_ISREG(database.st_mode) or database.st_size == 0:
                        report["skipped"].append(name)
                        continue
                finally:
                    os.close(fd)
            groups.append((name, match[1], stamp))

        manual = [g for g in groups if g[1] == "manual_cleanup"]
        newest = max(manual, key=lambda g: g[2])[0] if manual else None
        for name, kind, stamp in groups:
            if name == newest:
                report["protected"].append(name)
                continue
            fd = os.open(name, flags, dir_fd=with_fd)
            try:
                names = os.listdir(fd)
                entries = {n: os.stat(n, dir_fd=fd, follow_symlinks=False) for n in names}
                # 白名单只允许平铺的普通文件，不递归，不跟随链接。
                if (not names or not set(names) <= ALLOWED[kind]
                        or any(not stat.S_ISREG(s.st_mode) or s.st_nlink != 1
                               for s in entries.values())):
                    report["skipped"].append(name)
                    continue
                newest_mtime = max([stamp, os.fstat(fd).st_mtime]
                                   + [s.st_mtime for s in entries.values()])
                if newest_mtime >= cutoff:
                    continue
                report["candidates"].append(name)
                if not delete:
                    continue
                # 删除前重新确认目录和全部文件未被替换或修改。
                current = os.stat(name, dir_fd=with_fd, follow_symlinks=False)
                opened = os.fstat(fd)
                if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                    raise RuntimeError("备份目录在检查期间被替换")
                if set(os.listdir(fd)) != set(entries):
                    raise RuntimeError("备份文件列表在检查期间发生变化")
                for n, previous in entries.items():
                    current = os.stat(n, dir_fd=fd, follow_symlinks=False)
                    if current != previous:
                        raise RuntimeError("备份文件在检查期间发生变化")
                for n in entries:
                    os.unlink(n, dir_fd=fd)
                os.rmdir(name, dir_fd=with_fd)
                report["deleted"].append(name)
            finally:
                os.close(fd)
    finally:
        os.close(with_fd)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="实际删除；默认仅预演")
    args = parser.parse_args()
    print(json.dumps(cleanup(BACKUP_ROOT, delete=args.delete), ensure_ascii=False))
