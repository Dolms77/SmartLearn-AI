# -*- coding: utf-8 -*-
"""脱离 Streamlit 的自检脚本：验证数据适配层与 LLM 纯函数是否正常。

用法：
    python selftest.py                 # 默认检查 ../output 与赛题原始数据
    python selftest.py --output-dir X --raw-dir Y
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 - 某些终端不可重配置
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import adapter as A  # noqa: E402
import llm            # noqa: E402

DEFAULT_OUT = os.path.abspath(os.path.join(HERE, "..", "output"))
DEFAULT_RAW = os.path.abspath(os.path.join(
    HERE, "..", "赛题材料", "赛题数据", "赛题资料包", "4_赛题数据", "模拟学情数据"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=DEFAULT_OUT)
    ap.add_argument("--raw-dir", default=DEFAULT_RAW)
    a = ap.parse_args()
    fails: list[str] = []

    print("[1/5] 载入产物 ...")
    b = A.load_bundle(a.output_dir)
    n_students = len(A.list_students(b))
    print(f"      记录 {len(b['records'])} 条 | 学生 {n_students} 名 | 诊断 {len(b['diagnoses'])} 条")
    for k in ("statistics", "profiles", "mastery"):
        if not b.get(k):
            fails.append(f"缺少 {k}.json")
    if not b["records"]:
        fails.append("cleaned_data.json 缺失或为空")

    print("[2/5] 遍历全部学生视图 ...")
    bad = []
    for sid in A.list_students(b):
        try:
            v = A.student_view(b, sid)
            assert v["coverage"]["total"] == 9
            assert len(v["indicators"]) == 9
        except Exception as e:  # noqa: BLE001
            bad.append((sid, type(e).__name__, str(e)[:60]))
    print(f"      正常 {n_students - len(bad)} / {n_students}")
    fails += [f"student_view({s}) {t}: {m}" for s, t, m in bad]

    print("[3/5] 群体视图与任务1 ...")
    cv = A.class_view(b)
    rows = A.knowledge_rows(b)
    print(f"      班级 {cv['classes']} | 题目 {len(cv['by_question'])} 道 | 知识结构 {len(rows)} 行")
    if len(rows) != 9:
        fails.append(f"知识结构应为 9 行，实际 {len(rows)}")

    print("[4/5] 数据质量独立复核 ...")
    qr = A.quality_recheck(a.raw_dir)
    print("      " + (f"命中 {qr['问题数']} 条规则" if qr else "原始目录不可用，已跳过（只影响数据质量页）"))

    print("[5/5] LLM 纯函数 ...")
    ok = llm.validate_diagnosis({"error_type": "符号错误", "related_indicator": "T03I1"})
    bad_call = llm.validate_diagnosis({"error_type": "不存在的类型"})
    if not ok or bad_call is not None:
        fails.append("validate_diagnosis 校验逻辑异常")
    if n_students:
        v = A.student_view(b, A.list_students(b)[0])
        _ = llm.offline_answer("测试", llm.build_facts(v, {}, cv["class_theme"]))
    print("      校验 / 离线回答 正常")

    print("")
    if fails:
        print(f"[FAIL] 发现 {len(fails)} 个问题：")
        for f in fails:
            print("   -", f)
        return 1
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
