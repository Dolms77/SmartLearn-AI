# -*- coding: utf-8 -*-
"""数据适配层：只读 output/*.json，归一化成界面可直接渲染的视图模型。

设计原则
--------
1. 不改 A/B 的任何产物，只读；
2. 任何"结论"都必须带证据量（n），n < MIN_EVIDENCE 一律判 insufficient；
3. 缺失文件不报错，返回 None 并由界面显示 PLACEHOLDER；
4. 本模块不 import streamlit，便于脱离界面做单元自测。
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from typing import Any

INDICATORS = ["T01I1", "T01I2", "T01I3", "T02I1", "T02I2", "T02I3", "T03I1", "T03I2", "T03I3"]
THEMES = ["T01", "T02", "T03"]
THEME_NAMES = {"T01": "代数式与整式运算", "T02": "方程与方程组", "T03": "不等式与不等式组"}
INDICATOR_NAMES = {
    "T01I1": "表示数量关系并代入求值",
    "T01I2": "识别同类项、去括号并化简",
    "T01I3": "用整式解释具体问题",
    "T02I1": "运用等式性质解一元一次方程",
    "T02I2": "用消元法解二元一次方程组",
    "T02I3": "列方程或方程组解决简单实际问题并检验",
    "T03I1": "运用不等式性质求解，负数乘除时改变方向",
    "T03I2": "求两个一元一次不等式解集的交集",
    "T03I3": "根据实际限制列不等式并解释取值范围",
}
ERROR_TYPE_NAMES = {
    "C1": "概念误解", "C2": "符号错误", "C3": "计算失误",
    "C4": "步骤遗漏", "C5": "表达不规范", "C6": "级联错误", "OTHER": "其他",
}
MIN_EVIDENCE = 3


# --------------------------------------------------------------------------
# 基础读写
# --------------------------------------------------------------------------
def _read_json(path: str) -> Any | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_bundle(output_dir: str) -> dict[str, Any]:
    """一次性载入全部产物；缺失的键为 None。"""
    p = lambda name: os.path.join(output_dir, name)  # noqa: E731
    cleaned = _read_json(p("cleaned_data.json")) or {}
    diagnoses = _read_json(p("error_diagnosis.json")) or []
    llm_diag = _read_json(p("error_diagnosis_llm.json")) or {}
    bundle = {
        "output_dir": output_dir,
        "cleaned": cleaned,
        "records": cleaned.get("records") or [],
        "knowledge": cleaned.get("knowledge_structure") or {},
        "students": cleaned.get("students") or {},
        "question_map": cleaned.get("question_indicator_map") or {},
        "test_nodes": cleaned.get("test_nodes") or {},
        "meta": cleaned.get("meta") or {},
        "statistics": _read_json(p("statistics.json")),
        "profiles": _read_json(p("student_profiles.json")),
        "mastery": _read_json(p("mastery_matrix.json")),
        "diagnoses": diagnoses,
        "llm_diag": llm_diag if isinstance(llm_diag, dict) else {},
        "pattern": _read_json(p("error_pattern_summary.json")),
        "quality": _read_json(p("data_quality_report.json")),
    }
    bundle["diag_by_record"] = {d.get("record_id"): d for d in diagnoses if d.get("record_id")}
    bundle["records_by_student"] = _group(bundle["records"], "student_id")
    bundle["knowledge_base"] = _read_json(p("knowledge_base.json"))
    bundle["task1_json"] = _read_json(p("task1_knowledge_structure.json"))
    bundle["task3_json"] = _read_json(p("task3_recommendations.json"))
    return bundle


def _group(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r.get(key)].append(r)
    return dict(out)


def list_students(bundle: dict) -> list[str]:
    ids = set(bundle["students"].keys()) | set((bundle.get("profiles") or {}).keys())
    return sorted(ids)


def student_class(bundle: dict, sid: str) -> str:
    prof = (bundle.get("profiles") or {}).get(sid, {})
    if prof.get("class_id"):
        return prof["class_id"]
    return (bundle["students"].get(sid) or {}).get("模拟班级编号", "—")


# --------------------------------------------------------------------------
# 个体视图
# --------------------------------------------------------------------------
def _band(mastery: float | None, n: int) -> str:
    """证据量门槛在这里统一把关：n < MIN_EVIDENCE 一律 insufficient。"""
    if mastery is None or n < MIN_EVIDENCE:
        return "insufficient"
    if mastery >= 0.70:
        return "mastered"
    if mastery >= 0.40:
        return "developing"
    return "weak"


def student_view(bundle: dict, sid: str) -> dict:
    prof = (bundle.get("profiles") or {}).get(sid, {})
    details = prof.get("indicator_details") or {}
    records = bundle["records_by_student"].get(sid, [])
    rec_count = Counter(r.get("indicator_id") for r in records)

    indicators = []
    for code in INDICATORS:
        d = details.get(code) or {}
        n = int(d.get("answer_count") or rec_count.get(code) or 0)
        mastery = d.get("current_mastery")
        # 没有任何记录时，profile 的 current_mastery 只是先验值，不可当结论
        if n == 0:
            mastery = None
        indicators.append({
            "code": code,
            "name": d.get("indicator_name") or INDICATOR_NAMES[code],
            "theme": code[:3],
            "mastery": None if mastery is None else round(float(mastery), 4),
            "n": n,
            "accuracy": d.get("accuracy"),
            "band": _band(mastery, n),
        })

    decided = [x for x in indicators if x["band"] != "insufficient"]
    weak = sorted([x for x in decided if x["band"] == "weak"], key=lambda x: x["mastery"])
    developing = sorted([x for x in decided if x["band"] == "developing"], key=lambda x: x["mastery"])
    mastered = sorted([x for x in decided if x["band"] == "mastered"], key=lambda x: -x["mastery"])
    insufficient = [x for x in indicators if x["band"] == "insufficient"]

    overall = round(sum(x["mastery"] for x in decided) / len(decided), 4) if decided else None

    errors = [d for d in bundle["diagnoses"] if d.get("student_id") == sid]

    return {
        "sid": sid,
        "cls": student_class(bundle, sid),
        "overall": overall,
        "overall_raw": prof.get("overall_mastery"),
        "evidence_total": len(records),
        "coverage": {
            "total": len(INDICATORS),
            "answered": sum(1 for x in indicators if x["n"] > 0),
            "decided": len(decided),
        },
        "indicators": indicators,
        "weak": weak,
        "developing": developing,
        "mastered": mastered,
        "insufficient": insufficient,
        "errors": errors,
        "errors_by_indicator": _group(errors, "indicator_id"),
        "records": sorted(records, key=lambda r: r.get("submit_time", "")),
        "path_from_profile": prof.get("recommended_learning_path") or [],
        "bkt_history": {c: (details.get(c) or {}).get("mastery_history") or [] for c in INDICATORS},
    }


def indicator_evidence(bundle: dict, sid: str, code: str) -> list[dict]:
    """某生某指标下的原始作答记录（证据链下钻用）。"""
    return [r for r in bundle["records_by_student"].get(sid, [])
            if r.get("indicator_id") == code]


def record_detail(bundle: dict, record_id: str) -> dict | None:
    for r in bundle["records"]:
        if r.get("record_id") == record_id:
            out = dict(r)
            out["diagnosis_rule"] = bundle["diag_by_record"].get(record_id)
            out["diagnosis_llm"] = bundle["llm_diag"].get(record_id)
            return out
    return None


# --------------------------------------------------------------------------
# 群体视图
# --------------------------------------------------------------------------
def class_view(bundle: dict, cls: str | None = None) -> dict:
    stats = bundle.get("statistics") or {}
    by_class_theme = stats.get("by_class_theme") or {}
    by_student = stats.get("by_student") or {}
    classes = sorted({v.get("class") for v in by_student.values() if v.get("class")})

    rows = {}
    for c in classes:
        rows[c] = {}
        for t in THEMES:
            cell = by_class_theme.get(f"{c}-{t}")
            rows[c][t] = round(cell["score_rate"], 4) if cell else None
        counts = [v for v in by_student.values() if v.get("class") == c]
        total = sum(v["full"] for v in counts)
        rows[c]["overall"] = round(sum(v["score"] for v in counts) / total, 4) if total else None
        rows[c]["students"] = len(counts)

    return {
        "classes": classes,
        "class_theme": rows,
        "by_theme": stats.get("by_theme") or {},
        "by_indicator": stats.get("by_indicator") or {},
        "by_question": _question_rates(bundle),
        "by_class_question": stats.get("by_class_question") or {},
        "by_class_scoring_point": stats.get("by_class_scoring_point") or {},
        "by_student": by_student,
        "cross_node": stats.get("cross_node_changes") or [],
        "selected": cls or (classes[0] if classes else None),
    }


def _question_rates(bundle: dict) -> dict[str, dict]:
    """题目得分率：统计文件里没有 by_question，就用记录现算（口径：Σ得分/Σ满分）。"""
    agg: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    for r in bundle["records"]:
        qid = r.get("question_id")
        a = agg[qid]
        a[0] += float(r.get("score") or 0)
        a[1] += float(r.get("full_score") or 0)
        a[2] += 1
    out = {}
    for qid, (s, f, n) in agg.items():
        if not f:
            continue
        q = bundle["question_map"].get(qid, {})
        out[qid] = {
            "rate": round(s / f, 4), "n": n,
            "indicator": q.get("indicator", ""), "type": q.get("type", ""),
            "text": q.get("question_text", ""),
        }
    return out


# --------------------------------------------------------------------------
# 任务 1：知识结构（优先读 B 的 JSON，缺失时用 cleaned_data 现组装）
# --------------------------------------------------------------------------
def knowledge_rows(bundle: dict) -> list[dict]:
    """一行一个观察指标：课标 → 教材 → 题目 → 题量/满分/证据量。"""
    src = (bundle.get("task1_json") or {}).get("themes") or bundle.get("knowledge") or {}
    rows = []
    qmap = bundle["question_map"]
    for t in THEMES:
        theme = src.get(t) or {}
        for code in [c for c in INDICATORS if c.startswith(t)]:
            info = (theme.get("indicators") or {}).get(code) or {}
            qids = [qid for qid, q in qmap.items() if q.get("indicator") == code]
            full = sum(q.get("full_score", 0) for q in qmap.values()
                       if q.get("indicator") == code)
            n = sum(1 for r in bundle["records"] if r.get("indicator_id") == code)
            rows.append({
                "theme": t,
                "theme_name": theme.get("theme_name") or THEME_NAMES[t],
                "theme_goal": theme.get("theme_goal", ""),
                "course_standard": theme.get("course_standard", ""),
                "textbook_pages": theme.get("textbook_pages", ""),
                "code": code,
                "name": info.get("indicator_name") or INDICATOR_NAMES[code],
                "cs_ref": info.get("course_standard_ref", ""),
                "curriculum_source": info.get("curriculum_source") or {},
                "textbook_source": info.get("textbook_source") or {},
                "questions": sorted(qids),
                "question_references": info.get("question_references") or [],
                "question_count": len(qids),
                "full_score": full,
                "evidence": n,
                "density": "高" if n >= 150 else ("中" if n >= 60 else "低"),
            })
    return rows


# --------------------------------------------------------------------------
# 数据质量：UI 侧独立复核（补 A 的 01 未覆盖项）
# --------------------------------------------------------------------------
def quality_recheck(raw_dir: str) -> dict | None:
    """直接读原始 CSV 复核 8 类异常；raw_dir 指向「模拟学情数据」目录。"""
    if not raw_dir or not os.path.isdir(raw_dir):
        return None
    try:
        import pandas as pd
    except ImportError:
        return None
    need = ["作答记录.csv", "题目与材料.csv"]
    if not all(os.path.exists(os.path.join(raw_dir, f)) for f in need):
        return None

    rec = pd.read_csv(os.path.join(raw_dir, "作答记录.csv"))
    items = pd.read_csv(os.path.join(raw_dir, "题目与材料.csv"))
    node_file = os.path.join(raw_dir, "测验节点.csv")
    nodes = pd.read_csv(node_file) if os.path.exists(node_file) else None

    issues: list[dict] = []

    def add(kind: str, rule: str, rows: "pd.DataFrame", detail: str, fix: str) -> None:
        issues.append({
            "类型": kind, "规则": rule, "命中": int(len(rows)),
            "记录": ", ".join(map(str, rows["记录编号"].head(6).tolist())),
            "说明": detail, "处理": fix,
        })

    over = rec[(rec["得分"].notna()) & (rec["得分"] > rec["满分"])]
    add("得分越界", "R1 得分>满分", over, "录入错误，按满分截断", "截断并记 anomaly_score")

    def pts(s: str) -> int:
        return sum(int(v) for v in re.findall(r"=(\d+)", str(s)))

    sub = rec[rec["评分状态"] == "已评分"].copy()
    sub["点和"] = sub["评分点得分"].apply(lambda s: pts(s) if isinstance(s, str) and s.strip() else None)
    mism = sub[sub["点和"].notna() & (sub["点和"] != sub["得分"])]
    add("评分点矛盾", "R2 评分点之和≠总分", mism, "以评分点为准则重算", "重算总分并标记")

    dup = rec[rec.duplicated("作答事件编号", keep=False)].sort_values(["作答事件编号", "修订版本"])
    add("修订重复", "R3 同一作答事件多版本", dup, "须取最大修订版本", "保留最新版，其余归档")

    pend = rec[rec["评分状态"] == "待评分"]
    add("待评分", "R4 评分状态=待评分", pend, "不进入得分统计", "隔离，标 insufficient")

    blank = rec[rec["评分状态"] == "未作答"]
    add("未作答", "R5 评分状态=未作答", blank, "不等于答错", "单独统计，不计入掌握度")

    if nodes is not None:
        scope = {}
        for _, n in nodes.iterrows():
            scope[n["节点编号"]] = set(str(n["可用题目编号"]).split("、"))
        bad_node = rec[rec.apply(
            lambda r: r["材料编号"] not in scope.get(r["节点编号"], set()), axis=1)]
        add("节点越界", "R6 题目不在该节点可用范围", bad_node, "节点口径冲突", "改判节点或剔除")

    mm = rec.merge(items[["材料编号", "主题编号", "题型", "参考答案"]],
                   on="材料编号", how="left", suffixes=("", "_题"))
    topic_bad = mm[mm["主题编号"] != mm["主题编号_题"]]
    add("主题错标", "R7 记录主题≠题目主题", topic_bad, "以题目表为准", "按题目表修正")

    def norm(v: str) -> str:
        return re.sub(r"^(x|y|a|n)=|[\s，,。；;]", "", str(v))

    fill = mm[(mm["题型"] == "填空题") & (mm["评分状态"] == "已评分")].copy()
    if len(fill):
        fill["一致"] = [norm(a) == norm(b) for a, b in zip(fill["学生最终作答"], fill["参考答案"])]
        conflict = fill[fill["一致"] & (fill["得分"] == 0)]
        add("评分冲突", "R8 答案与参考答案一致却0分", conflict, "疑似误判", "标记待复核，不作能力证据")

    return {"总记录": int(len(rec)), "问题数": len(issues), "明细": issues}
