# -*- coding: utf-8 -*-
"""页面：知识结构 / 成果下载 / 数据质量（与其他页面组合渲染）。"""
from __future__ import annotations

import json
import os
import re

import pandas as pd
import streamlit as st

import adapter as A
import charts as C
import insights as I
import labels
import llm

BAND_TEXT = {"mastered": "已掌握", "developing": "发展中", "weak": "薄弱", "insufficient": "证据不足"}
BAND_ICON = {"mastered": "🟢", "developing": "🟠", "weak": "🔴", "insufficient": "⚪"}


# --------------------------------------------------------------------------
# 公用小组件
# --------------------------------------------------------------------------


def _metric_row(items: list[tuple[str, str, str | None]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value, help_text) in zip(cols, items):
        col.metric(label, value, help=help_text)






# --------------------------------------------------------------------------
# 页面 1：学生诊断
# --------------------------------------------------------------------------
def _task3_for(bundle: dict, sid: str) -> dict | None:
    data = bundle.get("task3_json") or {}
    students = data.get("students") if isinstance(data, dict) else None
    if isinstance(students, list):
        for s in students:
            if s.get("student_id") == sid:
                return s
    if isinstance(data, dict) and sid in data:
        return data[sid]
    if isinstance(data, dict):
        for group in ("cases", "all_students"):
            group_data = data.get(group)
            if isinstance(group_data, dict) and sid in group_data:
                return group_data[sid]
    return None


_LEVEL_TEXT = {"high": "优势明显", "medium": "部分掌握", "low": "需要重点干预"}
_BAND_RE = re.compile(r"「(薄弱|发展中|已掌握|证据不足)」")
_RATE_RE = re.compile(r"掌握度\s*(\d+)%")


_BAND_CN = {"weak": "薄弱", "developing": "发展中", "mastered": "已掌握", "insufficient": "证据不足"}


def _rec_label(r: dict) -> str:
    """展开器标题：短而完整，只显示知识点名称（编号放正文里）。"""
    parts = [f"优先级 {r.get('priority', '-')}"]
    name = (r.get("indicator_name") or "").strip()
    code = (r.get("indicator") or "").strip()
    parts.append(name or code)

    reason = r.get("reason") or ""
    band = r.get("band") or ""
    if not band:                                   # 兼容旧产物
        m = _BAND_RE.search(reason)
        band = m.group(1) if m else ""
    band_cn = _BAND_CN.get(str(band).lower(), band)
    if band_cn:
        parts.append(band_cn)

    mastery = r.get("mastery")
    if mastery is None:                            # 兼容旧产物
        m2 = _RATE_RE.search(reason)
        mastery_txt = f"掌握度 {m2.group(1)}%" if m2 else ""
    else:
        mastery_txt = f"掌握度 {float(mastery):.0%}"
    if mastery_txt:
        parts.append(mastery_txt)

    n = r.get("evidence_n")
    if n is None:
        n = len(r.get("evidence_ids") or [])
    if n:
        parts.append(f"证据 {n} 条")
    return " · ".join(p for p in parts if p)


def _render_task3(rec: dict, output_dir: str | None = None) -> None:
    if rec.get("diagnosis_summary"):
        st.markdown(f"**诊断摘要**：{labels.humanize(rec['diagnosis_summary'], output_dir)}")
    if rec.get("level"):
        st.caption(f"学情分层：{_LEVEL_TEXT.get(str(rec['level']).lower(), rec['level'])}")
    for r in rec.get("recommendations", []):
        with st.expander(_rec_label(r), expanded=r.get("priority") == 1):
            st.markdown(f"**理由**：{labels.humanize(r.get('reason', ''), output_dir)}")
            if r.get("recommended_questions"):
                details = {
                    item.get("question_id"): item.get("why_this")
                    for item in r.get("question_details", [])
                }
                questions = []
                for qid in r["recommended_questions"]:
                    reason = details.get(qid)
                    questions.append(f"{qid}（{reason}）" if reason else qid)
                st.markdown("**推荐题目**：" + " → ".join(questions))
            for i, h in enumerate(r.get("step_hints", []), 1):
                st.markdown(f"{i}. {h}")
            if r.get("follow_up_condition"):
                st.info(f"调整条件：{r['follow_up_condition']}")
            if r.get("human_review"):
                st.caption(r["human_review"])


# --------------------------------------------------------------------------
# 页面 2：班级概览
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# 页面 3：任务 1 知识结构
# --------------------------------------------------------------------------
def render_knowledge(bundle: dict, rows: list[dict]) -> None:
    st.subheader("任务 1 · 学习内容与要求梳理")
    if not rows:
        st.error("cleaned_data.json 缺少 knowledge_structure，无法渲染。")
        return

    st.caption("每个观察指标一行：课标条目 → 教材页 → 对应题号 → 题量/满分/证据密度。"
               "证据密度 = 该指标下的已评分作答条数，用于判断结论是否可靠。")

    for t in A.THEMES:
        trows = [r for r in rows if r["theme"] == t]
        if not trows:
            continue
        with st.expander(f"{trows[0]['theme_name']} · 课标 {trows[0]['course_standard']} · "
                         f"教材 {trows[0]['textbook_pages']}", expanded=True):
            st.caption(f"主题编号：{t}")
            st.markdown(f"**主题目标**：{trows[0]['theme_goal']}")
            df = pd.DataFrame([{
                "指标": r["code"], "观察指标": r["name"],
                "课标页": r["cs_ref"], "题目数": r["question_count"],
                "满分": r["full_score"], "证据数": r["evidence"], "密度": r["density"],
                "对应题目": "、".join(r["questions"]),
            } for r in trows])
            st.dataframe(df, width="stretch", hide_index=True)

    st.markdown("##### 双向导航：任选一个指标")
    codes = [r["code"] for r in rows]
    code = st.selectbox("指标", codes, format_func=lambda c: f"{c} {next(r['name'] for r in rows if r['code'] == c)}")
    r = next(x for x in rows if x["code"] == code)
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**课标**\n\n{r['course_standard']} · 正文/文件页 {r['cs_ref']}")
    c2.markdown(f"**教材**\n\n{r['textbook_pages']}")
    c3.markdown(f"**题量**\n\n{r['question_count']} 题 / {r['full_score']} 分 / 证据 {r['evidence']} 条")

    qdf = pd.DataFrame([{
        "题号": q, "题型": (bundle["question_map"].get(q) or {}).get("type", ""),
        "题干": ((bundle["question_map"].get(q) or {}).get("question_text") or "")[:60],
        "满分": (bundle["question_map"].get(q) or {}).get("full_score", ""),
    } for q in r["questions"]])
    st.dataframe(qdf, width="stretch", hide_index=True)

    curriculum = r.get("curriculum_source") or {}
    textbook = r.get("textbook_source") or {}
    question_sources = r.get("question_references") or []
    with st.expander("来源追溯（课标、教材与题目原始行号）", expanded=False):
        source_rows = [
            {
                "来源类型": "课标",
                "文件": curriculum.get("file", "—"),
                "行号": str(curriculum.get("row", "—")),
                "引用": curriculum.get("standard_id", ""),
                "页码": curriculum.get("page_reference", ""),
            },
            {
                "来源类型": "教材",
                "文件": textbook.get("file", "—"),
                "行号": "、".join(map(str, textbook.get("source_rows") or [])) or "—",
                "引用": "",
                "页码": textbook.get("page_reference", ""),
            },
        ]
        if question_sources:
            source_rows.extend({
                "来源类型": f"题目 {source.get('question_id', '')}",
                "文件": source.get("source_file", "—"),
                "行号": str(source.get("source_row", "—")),
                "引用": source.get("material_source", ""),
                "页码": "",
            } for source in question_sources)
        st.dataframe(pd.DataFrame(source_rows), width="stretch", hide_index=True)
        st.caption("行号对应原始 CSV（含表头）；只提供来源定位，不代表产物含有课标原文或教材摘录。")

    task1_export = bundle.get("task1_json")
    if task1_export:
        export_name = "task1_knowledge_structure.json"
        export_label = "⬇ 导出当前任务1结构"
        export_data = task1_export
    else:
        export_name = "task1_knowledge_structure_ui.json"
        export_label = "⬇ 导出 UI 组装的任务1结构"
        export_data = {"themes": bundle.get("knowledge")}
    st.download_button(
        export_label,
        data=json.dumps(export_data, ensure_ascii=False, indent=2),
        file_name=export_name, mime="application/json")
    if not task1_export:
        st.caption("当前显示的是由清洗数据自动汇总的知识结构；正式成果文件生成后将优先使用。")


# --------------------------------------------------------------------------
# 页面 4：数据质量
# --------------------------------------------------------------------------
def render_quality(bundle: dict) -> None:
    st.subheader("数据质量与清洗复核")
    rep = bundle.get("quality") or {}
    audit = rep.get("source_quality_audit") or {}
    checks = audit.get("checks") or []
    if not checks:
        st.warning("质量报告中没有 source_quality_audit 检查结果。请重新运行 01 数据加载脚本。")
        legacy_issues = rep.get("issues") or []
        if legacy_issues:
            st.dataframe(pd.DataFrame(legacy_issues), width="stretch", hide_index=True)
        return

    hit_rules = sum(1 for check in checks if check.get("hit_count", 0))
    _metric_row([
        ("原始记录数", str(audit.get("total_records", "—")), ""),
        ("复核规则数", str(audit.get("rule_count", len(checks))), ""),
        ("命中规则数", str(hit_rules), "命中数按记录-规则计数，同一记录可能命中多条规则"),
    ])
    st.caption("成绩与评分点保留源数据；命中下列规则表示需要复核，不代表已自动更正。")

    df = pd.DataFrame([{
        "规则": check.get("name", "数据质量检查"),
        "命中记录数": check.get("hit_count", 0),
        "涉及记录": "、".join(check.get("record_ids") or []) or "无",
        "处理口径": check.get("disposition", ""),
    } for check in checks])
    st.dataframe(df, width="stretch", hide_index=True)

    for key, title in (("pending_records", "待评分记录"), ("unanswered_records", "未作答记录")):
        rows = rep.get(key) or []
        if rows:
            with st.expander(f"{title}（{len(rows)} 条，不纳入已评分证据）", expanded=False):
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# --------------------------------------------------------------------------
# 页面 5：知识图谱、知识结构与成果下载
# --------------------------------------------------------------------------
def render_knowledge_and_artifacts(bundle: dict) -> None:
    rows = A.knowledge_rows(bundle)
    st.subheader("知识图谱")
    if rows and (bundle.get("knowledge") or (bundle.get("task1_json") or {}).get("themes")):
        themes = {row["theme"]: row["theme_name"] for row in rows}
        selected = st.selectbox("学习主题", list(themes), format_func=themes.__getitem__)
        st.caption("拖动画布平移，滚轮或右上角 + / − 缩放。将鼠标移到节点上查看详情。")
        fig = C.knowledge_graph([row for row in rows if row["theme"] == selected])
        C.show(fig, config={"scrollZoom": True, "displayModeBar": True, "displaylogo": False})
    else:
        st.info("知识结构数据生成后，可在这里浏览图谱。")

    knowledge, artifacts, quality = st.tabs(["知识结构", "成果下载", "数据质量"])
    with knowledge:
        render_knowledge(bundle, rows)
    with artifacts:
        render_artifacts(bundle)
    with quality:
        render_quality(bundle)


def render_artifacts(bundle: dict) -> None:
    st.subheader("成果文件与外部产物")
    st.caption("05 知识图谱与 06 学情仪表盘都由一键流程生成；图表字段说明见前端数据契约。")

    rows = I.artifact_files(bundle)
    df = pd.DataFrame([{
        "文件": r["file"], "说明": r["desc"],
        "状态": "存在" if r["exists"] else "未生成",
        "大小": f"{r['size'] / 1024:.0f} KB" if r["exists"] else "—",
    } for r in rows])
    st.dataframe(df, width="stretch", hide_index=True)

    st.markdown("##### 下载")
    cols = st.columns(3)
    for i, r in enumerate([x for x in rows if x["exists"]]):
        col = cols[i % 3]
        with col:
            try:
                with open(os.path.join(bundle["output_dir"], r["file"]), "rb") as f:
                    data = f.read()
                st.download_button(f"⬇ {r['desc']}", data=data, file_name=r["file"],
                                   mime=r["mime"], key=f"dl_{r['file']}")
            except OSError:
                st.caption(f"{r['file']} 读取失败")

    missing = [r for r in rows if not r["exists"]]
    if missing:
        with st.expander(f"未生成的 {len(missing)} 个文件及原因", expanded=False):
            for r in missing:
                hint = {
                    "knowledge_graph.html": "运行 05 需要 `pip install pyvis`",
                    "knowledge_base.json": "04 需要 `pip install -r requirements-rag.txt` 且下载 embedding 模型",
                    "task1_knowledge_structure.json": "运行 09 生成任务1结构化成果",
                    "task3_recommendations.json": "尚未生成；建议区会先展示按证据排序的第一步",
                }.get(r["file"], "尚未运行对应脚本")
                st.markdown(f"- `{r['file']}`：{hint}")
