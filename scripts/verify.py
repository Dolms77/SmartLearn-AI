# -*- coding: utf-8 -*-
"""产物校验：换一台机器跑完 01–09 后，用这里确认"跑对了"。

用法：
    .venv-ui\\Scripts\\python.exe scripts\\verify.py
    .venv-ui\\Scripts\\python.exe scripts\\verify.py --output-dir <output-directory>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.environ.get("SS_OUT") or os.path.abspath(os.path.join(HERE, "..", "output"))

REQUIRED = {
    "cleaned_data.json": "清洗后数据（01）",
    "data_quality_report.json": "质量报告（01）",
    "statistics.json": "五维统计（01）",
    "mastery_matrix.json": "掌握矩阵（02）",
    "student_profiles.json": "学生画像（02）",
    "error_diagnosis.json": "错因诊断（03）",
    "error_pattern_summary.json": "错因汇总（03）",
    "task3_recommendations.json": "任务3建议（08）",
    "task1_knowledge_structure.json": "任务1知识结构（09）",
}
OPTIONAL = {
    "knowledge_base.json": "RAG 知识库（04，可选）",
    "knowledge_graph.html": "知识图谱（05）",
    "dashboard.html": "学情仪表盘（06）",
    "error_diagnosis_llm.json": "LLM 诊断（llm_upgrade.py，可选）",
}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=DEFAULT_OUT)
    a = ap.parse_args()
    d = a.output_dir
    fails, warns = [], []

    print(f"产物目录：{d}\n")
    print(f"{'文件':<34}{'状态':<8}{'说明'}")
    print("-" * 78)
    for name, desc in REQUIRED.items():
        p = os.path.join(d, name)
        ok = os.path.exists(p)
        print(f"{name:<34}{'OK' if ok else 'MISSING':<8}{desc}")
        if not ok:
            fails.append(f"缺少 {name}")
    for name, desc in OPTIONAL.items():
        p = os.path.join(d, name)
        print(f"{name:<34}{'OK' if os.path.exists(p) else '—':<8}{desc}")

    # 关键数字
    try:
        cleaned = load(os.path.join(d, "cleaned_data.json"))
        stats = load(os.path.join(d, "statistics.json"))
        diag = load(os.path.join(d, "error_diagnosis.json"))
        prof = load(os.path.join(d, "student_profiles.json"))
        task3 = load(os.path.join(d, "task3_recommendations.json"))
        task1 = load(os.path.join(d, "task1_knowledge_structure.json"))
        recs = cleaned.get("records") or []
        task3_cases = task3.get("cases") or {}
        task3_all_students = task3.get("all_students") or {}
        task3_students = set(task3_cases) | set(task3_all_students)
        task1_themes = task1.get("themes") or {}
        task1_indicator_count = sum(
            len((theme.get("indicators") or {}))
            for theme in task1_themes.values()
        )
        task1_question_count = sum(
            indicator.get("question_count", 0)
            for theme in task1_themes.values()
            for indicator in (theme.get("indicators") or {}).values()
        )
        checks = [
            ("有效作答记录 = 790", len(recs) == 790, len(recs)),
            ("学生数 = 40", len(prof) == 40, len(prof)),
            ("指标数 = 9", len({r.get("indicator_id") for r in recs}) == 9,
             len({r.get("indicator_id") for r in recs})),
            ("错因诊断 = 385", len(diag) == 385, len(diag)),
            ("任务3覆盖全部学生", task3_students == set(prof)
             and len(task3_cases) + len(task3_all_students) == len(prof),
             len(task3_students)),
            ("总得分率 ≈ 57.9%", abs(stats["overall"]["score_rate"] - 0.5794) < 0.001,
             stats["overall"]["score_rate"]),
            ("任务1主题 = 3", len(task1_themes) == 3, len(task1_themes)),
            ("任务1指标 = 9", task1_indicator_count == 9, task1_indicator_count),
            ("任务1题目映射 = 54", task1_question_count == 54, task1_question_count),
        ]
        print("\n关键数字：")
        for label, ok, val in checks:
            print(f"  {'OK ' if ok else 'FAIL'} {label}（实际 {val}）")
            if not ok:
                fails.append(f"数字不符：{label} -> {val}")
    except Exception as e:  # noqa: BLE001
        fails.append(f"解析产物失败：{type(e).__name__}: {e}")

    print("")
    if fails:
        print(f"[FAIL] {len(fails)} 项：")
        for f in fails:
            print("   -", f)
        return 1
    print("[OK] 产物齐全且关键数字一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
