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
    "statistics.json": "多维统计（01）",
    "mastery_matrix.json": "掌握矩阵（02）",
    "student_profiles.json": "学生画像（02）",
    "error_diagnosis.json": "错因诊断（03）",
    "error_pattern_summary.json": "错因汇总（03）",
    "task3_recommendations.json": "任务3建议（08）",
    "task1_knowledge_structure.json": "任务1知识结构（09）",
    "dashboard.html": "学情仪表盘（06）",
}
OPTIONAL = {
    "knowledge_base.json": "RAG 知识库（04，可选）",
    "knowledge_graph.html": "知识图谱（05）",
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
        quality = load(os.path.join(d, "data_quality_report.json"))
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
        task1_question_references = sum(
            len(indicator.get("question_references") or [])
            for theme in task1_themes.values()
            for indicator in (theme.get("indicators") or {}).values()
        )
        question_map = cleaned.get("question_indicator_map") or {}
        all_question_references = [
            reference
            for theme in task1_themes.values()
            for indicator in (theme.get("indicators") or {}).values()
            for reference in (indicator.get("question_references") or [])
        ]
        question_references_match = all(
            reference.get("question_id") in question_map
            and reference.get("source_file")
            == question_map[reference["question_id"]].get("source_file")
            and reference.get("source_row")
            == question_map[reference["question_id"]].get("source_row")
            for reference in all_question_references
        )
        task1_indicator_count = sum(
            len((theme.get("indicators") or {}))
            for theme in task1_themes.values()
        )
        task1_question_count = sum(
            indicator.get("question_count", 0)
            for theme in task1_themes.values()
            for indicator in (theme.get("indicators") or {}).values()
        )
        audit = quality.get("source_quality_audit") or {}
        checks_by_rule = {
            check.get("rule_id"): check
            for check in audit.get("checks") or []
        }
        expected_audit_hits = {
            "R1": 2, "R2": 3, "R3": 14, "R4": 6,
            "R5": 5, "R6": 1, "R7": 1, "R8": 1,
        }
        process_coverage = quality.get("process_coverage") or {}
        process_statuses_match = all(
            record.get("student_process_status")
            == ("recorded" if record.get("student_process", "").strip() else "not_recorded")
            and record.get("student_process_status_label")
            == ("已记录" if record.get("student_process", "").strip() else "未记录")
            for record in recs
        )
        record_by_id = {record.get("record_id"): record for record in recs}
        expected_class_questions = {}
        expected_class_points = {}
        for record in recs:
            class_id = record.get("class_id")
            question_id = record.get("question_id")
            question_cell = expected_class_questions.setdefault(class_id, {}).setdefault(
                question_id, {"count": 0, "score": 0, "full": 0}
            )
            question_cell["count"] += 1
            question_cell["score"] += record.get("score") or 0
            question_cell["full"] += record.get("full_score") or 0
            for point in record.get("scoring_point_details") or []:
                point_cell = expected_class_points.setdefault(class_id, {}).setdefault(
                    point.get("scoring_point_id"), {"count": 0, "score": 0, "full": 0}
                )
                point_cell["count"] += 1
                point_cell["score"] += point.get("score") or 0
                point_cell["full"] += point.get("full_score") or 0

        def aggregates_match(expected, actual):
            if set(expected) != set(actual):
                return False
            for group_id, items in expected.items():
                actual_items = actual.get(group_id) or {}
                if set(items) != set(actual_items):
                    return False
                for item_id, values in items.items():
                    actual_values = actual_items[item_id]
                    if any(actual_values.get(key) != value for key, value in values.items()):
                        return False
                    rate = values["score"] / values["full"] if values["full"] else 0
                    if actual_values.get("score_rate") != round(rate, 4):
                        return False
            return True

        expected_flags = {
            "DR0133": {"R2"},
            "DR0361": {"R1", "R2"},
            "DR0535": {"R1", "R2"},
        }
        source_scores = {"DR0133": 3, "DR0361": 10, "DR0535": 4}
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
            ("任务1题目来源引用 = 54", task1_question_references == 54,
             task1_question_references),
            ("任务1题目来源行可关联", question_references_match,
             len(all_question_references)),
            ("质量复核规则 = 8", set(checks_by_rule) == set(expected_audit_hits),
             len(checks_by_rule)),
            ("质量复核命中数符合源数据", {
                rule: entry.get("hit_count")
                for rule, entry in checks_by_rule.items()
            } == expected_audit_hits, {
                rule: entry.get("hit_count")
                for rule, entry in checks_by_rule.items()
            }),
            ("解题过程覆盖 = 260/790", (
                process_coverage.get("recorded_count") == 260
                and process_coverage.get("scored_record_count") == 790
                and process_coverage.get("not_recorded_count") == 530
            ), process_coverage),
            ("逐条过程状态与文本一致", process_statuses_match, len(recs)),
            ("班级×题目统计覆盖2班",
             len(stats.get("by_class_question") or {}) == 2,
             len(stats.get("by_class_question") or {})),
            ("班级×评分点统计覆盖2班",
             len(stats.get("by_class_scoring_point") or {}) == 2,
             len(stats.get("by_class_scoring_point") or {})),
            ("班级×题目统计与记录汇总一致", aggregates_match(
                expected_class_questions, stats.get("by_class_question") or {}
            ), len(expected_class_questions)),
            ("班级×评分点统计与记录汇总一致", aggregates_match(
                expected_class_points, stats.get("by_class_scoring_point") or {}
            ), len(expected_class_points)),
            ("成绩冲突记录均已标记", all(
                record_id in record_by_id
                and set(record_by_id[record_id].get("quality_flags") or []) == flags
                for record_id, flags in expected_flags.items()
            ), {
                record_id: record_by_id.get(record_id, {}).get("quality_flags")
                for record_id in expected_flags
            }),
            ("成绩冲突保留源分", all(
                record_id in record_by_id
                and record_by_id[record_id].get("score") == score
                for record_id, score in source_scores.items()
            ), {
                record_id: record_by_id.get(record_id, {}).get("score")
                for record_id in source_scores
            }),
            ("评分点定义和满分可结构化读取", all(
                point.get("description") and point.get("full_score") is not None
                for point in (record_by_id.get("DR0133") or {}).get(
                    "scoring_point_details", []
                )
            ), (record_by_id.get("DR0133") or {}).get("scoring_point_details")),
            ("跨节点变化包含中文展示标签", all(
                bool(entry.get("change_type_label"))
                for entry in stats.get("cross_node_changes") or []
            ), len(stats.get("cross_node_changes") or [])),
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
