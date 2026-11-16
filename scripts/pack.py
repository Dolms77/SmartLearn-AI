# -*- coding: utf-8 -*-
"""把工作区打包成可分发的 zip：自动剔除密钥、虚拟环境、缓存。

用法：
    .venv-ui\\Scripts\\python.exe scripts\\pack.py
    .venv-ui\\Scripts\\python.exe scripts\\pack.py --out D:\\tmp\\deliver.zip
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOP = "智慧学伴_队伍交付"

INCLUDE_FILES = [
    "00_开始使用.html", "README.md", "requirements.txt", "requirements-rag.txt",
    ".gitignore", "赛题规则.pdf", "创新点.xlsx",
    "1_一键安装.bat", "2_一键运行全部.bat", "3_启动界面.bat",
]
INCLUDE_DIRS = ["docs", "scripts", "已完成脚本", "ui", "output", "赛题材料",
                "方案设计", "评审意见", "分析脚本"]

EXCLUDE_PARTS = [
    "__pycache__", ".pyc", ".venv", ".tmp", ".streamlit-home", "llm_cache",
    "chroma_db", "api.txt", ".git" + os.sep, ".DS_Store", ".pytest_cache",
]
SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{20,}")
TEXT_EXT = {".py", ".md", ".txt", ".json", ".html", ".ps1", ".bat", ".csv", ".yml", ".yaml"}


def keep(rel: str) -> bool:
    low = rel.lower()
    return not any(p.lower() in low for p in EXCLUDE_PARTS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "智慧学伴_队伍交付_20261116.zip"))
    a = ap.parse_args()

    files: list[tuple[str, str]] = []   # (abs, rel)
    for f in INCLUDE_FILES:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            files.append((p, f))
        else:
            print(f"[warn] 缺少 {f}，已跳过")
    for d in INCLUDE_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            print(f"[warn] 缺少目录 {d}，已跳过")
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if keep(x)]
            for name in filenames:
                p = os.path.join(dirpath, name)
                rel = os.path.relpath(p, ROOT)
                if keep(rel):
                    files.append((p, rel))

    # 密钥扫描
    leaks = []
    for p, rel in files:
        if os.path.splitext(p)[1].lower() in TEXT_EXT:
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    if SECRET_RE.search(fh.read()):
                        leaks.append(rel)
            except OSError:
                pass
    if leaks:
        print("[FAIL] 以下文件疑似含 API Key，已中止：")
        for x in leaks:
            print("   -", x)
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    if os.path.exists(a.out):
        os.remove(a.out)

    total_raw = 0
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p, rel in sorted(files, key=lambda x: x[1]):
            total_raw += os.path.getsize(p)
            z.write(p, os.path.join(TOP, rel).replace("\\", "/"))

    size = os.path.getsize(a.out)
    print(f"已打包 {len(files)} 个文件")
    print(f"原始 {total_raw / 1024 / 1024:.1f} MB → 压缩后 {size / 1024 / 1024:.1f} MB")
    print(f"输出: {a.out}")
    print("已排除: api.txt / .venv-ui / .tmp / __pycache__ / llm_cache / chroma_db")
    return 0


if __name__ == "__main__":
    sys.exit(main())
