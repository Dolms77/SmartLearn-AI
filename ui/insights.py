# -*- coding: utf-8 -*-
"""把结构化产物里"界面还没用上"的部分接出来。

覆盖：
  * statistics.by_scoring_point  → 评分点级薄弱清单（任务2 最硬的证据）
  * statistics.by_student.theme_rates → 个体三主题得分率
  * error_pattern_summary → 错误类型分布 / 关键发现 / 高频错题
  * mastery_matrix + 每人证据量 → 全班 40×9 热力图（证据不足的格子留白）
  * cleaned_data.test_nodes → 两个测验节点的口径说明
  * 05 生成的知识图谱 HTML、04 的 knowledge_base.json → 成果附件
"""
from __future__ import annotations

import os

import adapter as A

IND = A.INDICATORS


def scoring_points(bundle: dict, limit: int | None = None,
                   flags: tuple[str, ...] = ("critical", "weak")) -> list[dict]:
    """评分点级排行：把 90 个评分点按得分率升序，标注 critical/weak/normal。"""
    stats = bundle.get("statistics") or {}
    sp = stats.get("by_scoring_point") or {}
    qmap = bundle["question_map"]
    rows = []
    for pid, v in sp.items():
        qid = pid.split("P")[0]
        q = qmap.get(qid, {})
        rows.append({
            "评分点": pid,
            "题号": qid,
            "指标": q.get("indicator", ""),
            "题型": q.get("type", ""),
            "得分率": round(float(v.get("score_rate", 0)), 4),
            "正确/总数": f"{v.get('correct', 0)}/{v.get('total', 0)}",
            "样本": int(v.get("total", 0)),
            "标记": v.get("flag", "normal"),
            "题干": (q.get("question_text") or "")[:36],
        })
    if flags:
        rows = [r for r in rows if r["标记"] in flags]
    rows.sort(key=lambda r: (r["得分率"], -r["样本"]))
    return rows[:limit] if limit else rows


def scoring_point_definition(bundle: dict, pid: str) -> str:
    """从题目表里取该评分点的中文定义（如 Q015P3 写出正确结果）。"""
    qid = pid.split("P")[0]
    q = bundle["question_map"].get(qid, {})
    for line in str(q.get("scoring_points", "")).splitlines():
        if line.strip().startswith(pid):
            return line.strip()
    return ""


def error_types(bundle: dict) -> list[dict]:
    pattern = bundle.get("pattern") or {}
    by = pattern.get("by_error_type") or {}
    rows = [{"代码": code, "类型": v.get("name", code),
             "条数": int(v.get("count", 0)), "占比": float(v.get("percentage", 0))}
            for code, v in by.items()]
    rows.sort(key=lambda r: -r["条数"])
    return rows


def critical_findings(bundle: dict) -> list[dict]:
    return (bundle.get("pattern") or {}).get("critical_findings") or []


def frequent_questions(bundle: dict, top: int = 10) -> list[dict]:
    by = (bundle.get("pattern") or {}).get("by_question") or {}
    rows = [{"题号": qid, "错误人数": v.get("error_count", 0),
             "错误率": v.get("error_rate", 0),
             "指标": (bundle["question_map"].get(qid) or {}).get("indicator", "")}
            for qid, v in by.items()]
    rows.sort(key=lambda r: -r["错误人数"])
    return rows[:top]


def student_theme_rates(bundle: dict, sid: str) -> dict:
    stats = (bundle.get("statistics") or {}).get("by_student", {}).get(sid, {})
    return stats.get("theme_rates") or {}


def mastery_heatmap(
    bundle: dict, class_id: str | None = None, clustered: bool = False
) -> dict:
    """生成班级×指标掌握矩阵；证据不足格不暴露 BKT 先验值。"""
    profiles = bundle.get("profiles") or {}
    students = sorted(
        sid for sid in profiles
        if class_id is None or A.student_class(bundle, sid) == class_id
    )
    cells: dict[str, dict[str, tuple[float | None, int, int]]] = {}
    for sid in students:
        details = (profiles[sid] or {}).get("indicator_details") or {}
        cells[sid] = {}
        for code in IND:
            d = details.get(code) or {}
            n = int(d.get("answer_count") or 0)
            val = d.get("current_mastery")
            mastery = round(float(val), 4) if n >= A.MIN_EVIDENCE and val is not None else None
            correct = int(d.get("correct_count") or 0)
            cells[sid][code] = (mastery, n, correct)

    indicators = list(IND)
    if clustered:
        def mean_mastery(values: list[float | None]) -> float | None:
            decided = [value for value in values if value is not None]
            return sum(decided) / len(decided) if decided else None

        def student_order(sid: str) -> tuple[bool, float, int, str]:
            values = [cells[sid][code][0] for code in indicators]
            mean = mean_mastery(values)
            return (mean is None, -(mean or 0.0), -sum(v is not None for v in values), sid)

        def indicator_order(code: str) -> tuple[bool, float, int, str]:
            values = [cells[sid][code][0] for sid in students]
            mean = mean_mastery(values)
            return (mean is None, -(mean or 0.0), -sum(v is not None for v in values), code)

        students.sort(key=student_order)
        indicators.sort(key=indicator_order)

    mastery_rows = []
    evidence_rows = []
    correct_rows = []
    for sid in students:
        mastery_rows.append([cells[sid][code][0] for code in indicators])
        evidence_rows.append([cells[sid][code][1] for code in indicators])
        correct_rows.append([cells[sid][code][2] for code in indicators])

    return {
        "students": students,
        "indicators": indicators,
        "indicator_names": A.INDICATOR_NAMES,
        "mastery": mastery_rows,
        "evidence": evidence_rows,
        "correct": correct_rows,
        "clustered": clustered,
        "class_id": class_id,
    }


def class_mastery_summary(bundle: dict) -> dict:
    """按班级汇总"可判定"的指标数量与均值，体现记录覆盖差异。"""
    profiles = bundle.get("profiles") or {}
    out: dict[str, dict] = {}
    for sid, p in profiles.items():
        cls = (p or {}).get("class_id", "—")
        details = (p or {}).get("indicator_details") or {}
        decided = [d for d in details.values() if int(d.get("answer_count") or 0) >= A.MIN_EVIDENCE]
        cell = out.setdefault(cls, {"students": 0, "decided": 0, "evidence": 0, "sum": 0.0})
        cell["students"] += 1
        cell["decided"] += len(decided)
        cell["evidence"] += sum(int(d.get("answer_count") or 0) for d in details.values())
        cell["sum"] += sum(float(d.get("current_mastery") or 0) for d in decided)
    for cls, c in out.items():
        c["avg_mastery"] = round(c["sum"] / c["decided"], 4) if c["decided"] else None
        c["decided_rate"] = round(c["decided"] / (c["students"] * len(IND)), 3) if c["students"] else 0
    return out


def node_info(bundle: dict) -> list[dict]:
    nodes = bundle.get("test_nodes") or {}
    rows = []
    for nid, v in nodes.items():
        rows.append({
            "节点": nid,
            "日期": v.get("模拟测验日期", ""),
            "已教及测量主题": v.get("已教及测量主题", ""),
            "说明": v.get("说明", ""),
            "可用题目数": len(str(v.get("可用题目编号", "")).split("、")),
        })
    return sorted(rows, key=lambda r: r["节点"])


def artifact_files(bundle: dict) -> list[dict]:
    """生成、但界面尚未内联展示的成果文件，用于下载/外链。"""
    d = bundle.get("output_dir", "")
    items = [
        ("knowledge_graph.html", "05 交互式知识图谱", "text/html"),
        ("bkt_summary.txt", "02 掌握度矩阵摘要", "text/plain"),
        ("statistics_summary.txt", "01 统计摘要", "text/plain"),
        ("error_diagnosis_summary.txt", "03 错因摘要", "text/plain"),
        ("knowledge_base.json", "04 RAG 知识库索引（可选）", "application/json"),
        ("task1_knowledge_structure.json", "任务1 成果（B）", "application/json"),
        ("task3_recommendations.json", "任务3 建议（B）", "application/json"),
    ]
    out = []
    for name, desc, mime in items:
        p = os.path.join(d, name)
        out.append({"file": name, "desc": desc, "mime": mime,
                    "exists": os.path.exists(p), "size": os.path.getsize(p) if os.path.exists(p) else 0})
    return out
