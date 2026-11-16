# -*- coding: utf-8 -*-
"""页面：学生诊断 / 班级概览 / 任务1 知识结构 / 数据质量 / 成果文件。"""
from __future__ import annotations

import json
import os

import pandas as pd
import streamlit as st

import adapter as A
import charts as C
import insights as I
import llm

BAND_TEXT = {"mastered": "已掌握", "developing": "发展中", "weak": "薄弱", "insufficient": "证据不足"}
BAND_ICON = {"mastered": "🟢", "developing": "🟠", "weak": "🔴", "insufficient": "⚪"}


# --------------------------------------------------------------------------
# 公用小组件
# --------------------------------------------------------------------------
def _badge(band: str, n: int) -> str:
    return f"{BAND_ICON[band]} {BAND_TEXT[band]}（n={n}）"


def _metric_row(items: list[tuple[str, str, str | None]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value, help_text) in zip(cols, items):
        col.metric(label, value, help=help_text)


def _record_table(records: list[dict]) -> pd.DataFrame:
    rows = []
    for r in records:
        rows.append({
            "记录编号": r.get("record_id"),
            "节点": r.get("node_id"),
            "题号": r.get("question_id"),
            "得分": f"{r.get('score')}/{r.get('full_score')}",
            "作答": (str(r.get("student_answer") or "")[:40]),
            "评分点": r.get("scoring_point_scores") or "—",
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 页面 1：学生诊断
# --------------------------------------------------------------------------
def render_diagnosis(bundle: dict, sid: str, key: str | None, cache_dir: str) -> None:
    v = A.student_view(bundle, sid)
    stats = (bundle.get("statistics") or {}).get("by_student", {}).get(sid, {})

    st.subheader(f"{sid} · {v['cls']} · 学情诊断")
    _metric_row([
        ("可判定掌握度", f"{v['overall']:.0%}" if v["overall"] is not None else "—",
         "只用证据 ≥3 条的指标计算；全无证据时为 —"),
        ("有效记录", f"{v['evidence_total']}", "去重后的已评分作答事件"),
        ("指标覆盖", f"{v['coverage']['decided']}/{v['coverage']['total']}",
         f"已作答 {v['coverage']['answered']} 个，达到证据门槛 {v['coverage']['decided']} 个"),
        ("错因记录", f"{len(v['errors'])}", "规则引擎判定的错误记录数"),
    ])

    if v["coverage"]["decided"] == 0:
        st.warning(
            f"{sid} 只有 {v['evidence_total']} 条有效记录，**没有任何指标达到 3 条证据门槛**，"
            f"按赛题口径不下掌握度结论。下方仅展示原始证据，供补充观察设计使用。")
    elif v["coverage"]["decided"] < 5:
        st.info(
            f"仅 {v['coverage']['decided']}/9 个指标证据充分；其余 "
            f"{len(v['insufficient'])} 个指标标记为「证据不足」，不参与薄弱判定。")

    left, right = st.columns([1, 1])
    with left:
        st.plotly_chart(C.student_radar(v), width="stretch")
    with right:
        st.plotly_chart(C.indicator_bars(v), width="stretch")

    with st.expander("证据量分布（为什么有的指标不下结论）", expanded=False):
        st.plotly_chart(C.evidence_bars(v), width="stretch")
        st.caption("灰线为证据门槛 3 条；低于门槛的指标一律输出「证据不足」，避免把缺记录当作未掌握。")

    # ---- 三主题得分率（来自 statistics.by_student.theme_rates）----
    rates = I.student_theme_rates(bundle, sid)
    nodes = I.node_info(bundle)
    c1, c2 = st.columns([1, 1])
    with c1:
        if rates:
            st.markdown("##### 三主题得分率（按题目原始计分，不含证据门槛）")
            st.plotly_chart(C.theme_rates_chart(rates), width="stretch")
        else:
            st.info("statistics.json 中没有该生的 theme_rates。")
    with c2:
        if nodes:
            st.markdown("##### 测验节点口径")
            st.dataframe(pd.DataFrame([{
                "节点": n["节点"], "日期": n["日期"], "已教主题": n["已教及测量主题"],
                "可用题数": n["可用题目数"],
            } for n in nodes]), width="stretch", hide_index=True)
            st.caption("N01 未教方程组与不等式：该节点出现相关题目属数据异常，已在校验中标记。")

    # ---- 指标表 ----
    st.markdown("##### 指标级结论")
    df = pd.DataFrame([{
        "指标": i["code"],
        "观察指标": i["name"],
        "掌握度": None if i["mastery"] is None else round(i["mastery"], 3),
        "证据数": i["n"],
        "判定": _badge(i["band"], i["n"]),
    } for i in v["indicators"]])
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={"掌握度": st.column_config.NumberColumn(format="%.2f")})

    # ---- 薄弱指标 + 证据链 ----
    st.markdown("##### 薄弱指标与证据链")
    if not v["weak"] and not v["developing"]:
        st.success("没有达到「薄弱」判定门槛的指标（或证据不足，见上表）。")
    for item in (v["weak"] + v["developing"]):
        code = item["code"]
        errs = v["errors_by_indicator"].get(code, [])
        with st.expander(f"{BAND_ICON[item['band']]} {code} {item['name']} · "
                         f"掌握度 {item['mastery']:.0%} · 证据 {item['n']} 条 · 错因 {len(errs)} 条"):
            recs = A.indicator_evidence(bundle, sid, code)
            st.dataframe(_record_table(recs), width="stretch", hide_index=True)
            hist = (v.get("bkt_history") or {}).get(code) or []
            if len(hist) > 1:
                st.markdown("**知识追踪轨迹（BKT 掌握概率随作答次序变化）**")
                st.plotly_chart(C.timeline_chart(hist, code), width="stretch")
            for e in errs[:5]:
                st.markdown(
                    f"- `{e.get('record_id')}` **{e.get('question_id')}** "
                    f"〔{e.get('error_type_code')} {e.get('error_type')}〕"
                    f" 得分 {e.get('score')}/{e.get('full_score')} — {e.get('error_description', '')}")
            if item["n"] < A.MIN_EVIDENCE:
                st.caption("⚠ 该指标证据未达门槛，以上仅作线索，不作结论。")

    # ---- AI 深度诊断（双源对比）----
    st.markdown("##### 错因诊断：规则引擎 vs DeepSeek")
    err_ids = [e.get("record_id") for e in v["errors"]]
    if not err_ids:
        st.caption("该生没有错误记录，无需诊断。")
    else:
        rid = st.selectbox(
            "选择一条错误记录", err_ids,
            format_func=lambda r: next(
                f"{r} · {e.get('question_id')} · {e.get('error_type_code')} {e.get('error_type')}"
                for e in v["errors"] if e.get("record_id") == r))
        detail = A.record_detail(bundle, rid) or {}
        rule = detail.get("diagnosis_rule") or {}
        cached_llm = (bundle.get("llm_diag") or {}).get(rid) or st.session_state.get(f"llm_{rid}")

        left, right = st.columns(2)
        with left:
            st.markdown("**规则引擎（可复算）**")
            st.markdown(f"- 类型：`{rule.get('error_type_code')}` {rule.get('error_type')}")
            st.markdown(f"- 说明：{rule.get('error_description', '—')}")
            st.caption(f"置信度 {rule.get('confidence', '—')}｜来源 {rule.get('diagnosis_source', '—')}")
        with right:
            st.markdown("**DeepSeek（可解释）**")
            if cached_llm:
                st.markdown(f"- 类型：`{cached_llm.get('error_type_code')}` {cached_llm.get('error_type')}")
                st.markdown(f"- 出错位置：{cached_llm.get('error_location') or '—'}")
                st.markdown(f"- 思维误区：{cached_llm.get('root_cause') or '—'}")
                st.markdown(f"- 补救提示：{cached_llm.get('remediation_hint') or '—'}")
                st.caption(f"关联指标 {cached_llm.get('related_indicator') or '—'}｜来源 llm/{cached_llm.get('model', '')}")
            else:
                st.caption("尚未生成。点击下方按钮调用（无 Key 时不可用）。")
        if st.button("🤖 调用 DeepSeek 生成深度诊断", disabled=not key, key=f"ai_{rid}"):
            with st.spinner("请求中…"):
                got = llm.diagnose_record(detail, key, cache_dir)
            if not got or got.get("error"):
                st.error(f"调用失败：{(got or {}).get('error', '返回为空')}")
            else:
                st.session_state[f"llm_{rid}"] = got
                st.rerun()

    # ---- 建议区 ----
    st.markdown("##### 个性化学习建议")
    rec = _task3_for(bundle, sid)
    if rec:
        _render_task3(rec)
    else:
        st.info("B 的 `task3_recommendations.json` 尚未提供。以下只列出**排序依据**，不是建议结论。")
        order = sorted(v["weak"] + v["developing"], key=lambda x: x["mastery"])
        if order:
            rows = []
            for i, x in enumerate(order, 1):
                qids = [q for q, meta in bundle["question_map"].items()
                        if meta.get("indicator") == x["code"]]
                rows.append({
                    "优先级": i, "指标": x["code"], "观察指标": x["name"],
                    "掌握度": f"{x['mastery']:.0%}", "证据数": x["n"],
                    "同指标可用练习": "、".join(qids[:4]),
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        if v["insufficient"]:
            st.caption("待补充观察：" + "、".join(x["code"] for x in v["insufficient"]))

    # ---- 问答 ----
    st.markdown("##### 问答（可接入 DeepSeek）")
    facts = llm.build_facts(v, stats, A.class_view(bundle)["class_theme"])
    presets = [
        "这个学生最需要先补什么？为什么？",
        "哪些指标其实没有足够证据？",
        "他/她的错误主要集中在哪一类？",
        "下一步怎么验证是否真的掌握了？",
    ]
    col1, col2 = st.columns([3, 1])
    q = col1.selectbox("选择问题（或在下框自定义）", presets, label_visibility="collapsed")
    custom = st.text_input("自定义问题（留空则用上面的选择）", "")
    question = (custom or "").strip() or q
    if col2.button("提问", width="stretch", key=f"qa_btn_{sid}"):
        if key:
            with st.spinner("正在请求 DeepSeek…"):
                try:
                    st.session_state[f"qa_{sid}"] = llm.answer_question(question, facts, key, cache_dir)
                except Exception as e:  # noqa: BLE001
                    st.session_state[f"qa_{sid}"] = f"调用失败，已回退离线回答：\n\n" + \
                        llm.offline_answer(question, facts) + f"\n\n（错误：{type(e).__name__}）"
        else:
            st.session_state[f"qa_{sid}"] = llm.offline_answer(question, facts)
        st.session_state[f"qa_q_{sid}"] = question
    if st.session_state.get(f"qa_{sid}"):
        st.markdown(f"> **问**：{st.session_state.get(f'qa_q_{sid}', '')}")
        st.success(st.session_state[f"qa_{sid}"])
        st.caption(f"数据来源：结构化统计 + {'DeepSeek 改写' if key else '离线模板'}；"
                   f"事实白名单已限定，不包含任何编造数字。")

    # ---- 导出 ----
    export = {k: v[k] for k in ("sid", "cls", "overall", "evidence_total", "coverage")}
    export.update({"indicators": v["indicators"],
                   "weak": [x["code"] for x in v["weak"]],
                   "insufficient": [x["code"] for x in v["insufficient"]],
                   "errors": v["errors"]})
    st.download_button("⬇ 导出该生诊断 JSON（复核用）",
                       data=json.dumps(export, ensure_ascii=False, indent=2, default=str),
                       file_name=f"diagnosis_{sid}.json", mime="application/json")


def _task3_for(bundle: dict, sid: str) -> dict | None:
    data = bundle.get("task3_json") or {}
    students = data.get("students") if isinstance(data, dict) else None
    if isinstance(students, list):
        for s in students:
            if s.get("student_id") == sid:
                return s
    if isinstance(data, dict) and sid in data:
        return data[sid]
    return None


def _render_task3(rec: dict) -> None:
    if rec.get("diagnosis_summary"):
        st.markdown(f"**诊断摘要**：{rec['diagnosis_summary']}")
    for r in rec.get("recommendations", []):
        with st.expander(f"优先级 {r.get('priority', '-')}｜{r.get('indicator', '')}｜"
                         f"{r.get('reason', '')[:40]}", expanded=r.get("priority") == 1):
            st.markdown(f"**理由**：{r.get('reason', '')}")
            if r.get("recommended_questions"):
                st.markdown("**推荐题目**：" + " → ".join(r["recommended_questions"]))
            for i, h in enumerate(r.get("step_hints", []), 1):
                st.markdown(f"{i}. {h}")
            if r.get("follow_up_condition"):
                st.info(f"调整条件：{r['follow_up_condition']}")


# --------------------------------------------------------------------------
# 页面 2：班级概览
# --------------------------------------------------------------------------
def render_class(bundle: dict, cls: str | None) -> None:
    cv = A.class_view(bundle, cls)
    st.subheader("班级与群体分析")
    if not cv["classes"]:
        st.error("未找到 statistics.json / by_student，无法渲染班级视图。")
        return

    selected = st.selectbox("选择班级", cv["classes"],
                            index=cv["classes"].index(cv["selected"]) if cv["selected"] in cv["classes"] else 0)
    row = cv["class_theme"].get(selected, {})
    others = [c for c in cv["classes"] if c != selected]
    diff = None
    if others:
        diff = (row.get("overall") or 0) - (cv["class_theme"].get(others[0], {}).get("overall") or 0)

    _metric_row([
        ("班级得分率", f"{(row.get('overall') or 0):.1%}", "Σ得分/Σ满分"),
        ("学生数", f"{row.get('students', 0)}", ""),
        (f"与 {others[0]} 差" if others else "对照", f"{diff:+.1%}" if diff is not None else "—",
         "正数表示本班更高"),
        ("全班有效记录", f"{(bundle.get('statistics') or {}).get('overall', {}).get('total_records', 0)}", ""),
    ])

    left, right = st.columns(2)
    with left:
        st.plotly_chart(C.class_theme_chart(cv["class_theme"]), width="stretch")
    with right:
        st.plotly_chart(C.indicator_rank_chart(cv["by_indicator"]), width="stretch")

    st.markdown("##### 最薄弱的题目（至少 5 人作答）")
    st.plotly_chart(C.question_rate_chart(cv["by_question"]), width="stretch")

    st.markdown("##### 跨节点变化（N01 → N02）")
    changes = cv["cross_node"]
    if changes:
        df = pd.DataFrame([{
            "学生": x["student_id"], "题目": x["question_id"],
            "N01": f"{x['N01']['score']}/{x['N01']['full']}",
            "N02": f"{x['N02']['score']}/{x['N02']['full']}",
            "变化": {"improved": "进步", "declined": "退步", "still_wrong": "仍未掌握",
                     "still_right": "保持正确"}.get(x.get("change_type"), x.get("change_type")),
        } for x in changes])
        st.dataframe(df, width="stretch", hide_index=True, height=280)
        st.caption("只统计两个节点都出现的同一道题，共 "
                   f"{len(changes)} 组；用于说明「进步/退步/顽固错误」。")
    else:
        st.info("statistics.json 中没有 cross_node_changes。")


    # ---- 评分点级薄弱清单（任务2 最有说服力的证据）----
    st.markdown("##### 薄弱评分点 Top 12")
    sp = I.scoring_points(bundle, limit=12)
    if sp:
        left, right = st.columns([3, 2])
        with left:
            st.plotly_chart(C.scoring_point_chart(sp), width="stretch")
        with right:
            st.dataframe(pd.DataFrame([{
                "评分点": r["评分点"], "指标": r["指标"], "得分率": f"{r['得分率']:.0%}",
                "正确/总数": r["正确/总数"], "标记": r["标记"],
            } for r in sp]), width="stretch", hide_index=True)
        with st.expander("这 12 个评分点的官方定义（可直接写进报告）", expanded=False):
            for r in sp:
                st.markdown(f"- `{r['评分点']}` **{r['指标']}** · 得分率 {r['得分率']:.0%}"
                            f"（{r['正确/总数']}）— {I.scoring_point_definition(bundle, r['评分点'])}")
        st.caption("评分点级证据比题目级更细：例如「Q043P2 除以负数反向」0% 会直接指向"
                   "「不等式性质 3」这一知识点，而不是笼统说「不等式薄弱」。")
    else:
        st.info("statistics.json 中没有 by_scoring_point。")

    # ---- 错因分布 + 班级掌握覆盖 ----
    left, right = st.columns([3, 2])
    with left:
        st.markdown("##### 六类错因分布（全部 385 条错误记录）")
        et = I.error_types(bundle)
        if et:
            st.plotly_chart(C.error_type_chart(et), width="stretch")
    with right:
        st.markdown("##### 班级掌握度覆盖")
        cms = I.class_mastery_summary(bundle)
        st.dataframe(pd.DataFrame([{
            "班级": k, "学生": v["students"],
            "可判定指标": v["decided"], "覆盖学生数": v["decided_rate"],
            "可判定均掌握度": None if v["avg_mastery"] is None else f"{v['avg_mastery']:.0%}",
        } for k, v in cms.items()]), width="stretch", hide_index=True)
        st.caption("40×9=360 个『学生-指标』格子里，只有 130 个达到 3 条证据门槛（36%）。"
                   "这就是为什么个体页大量显示「证据不足」。")

    # ---- 全班热力图 ----
    st.markdown("##### 全班 40 × 9 掌握度热力图（空白=证据不足）")
    hm = I.mastery_heatmap(bundle)
    st.plotly_chart(C.mastery_heatmap_chart(hm), width="stretch")
    st.caption("留白格子不填先验值：宁可空着，也不把「没有记录」画成「掌握/未掌握」。")

    # ---- 关键发现 ----
    findings = I.critical_findings(bundle)
    if findings:
        with st.expander(f"03 自动生成的关键发现（{len(findings)} 条）", expanded=False):
            for f in findings:
                st.markdown(f"- `{f.get('severity', '')}` {f.get('description', '')}")
            st.markdown("**高频错题（按答错人数）**")
            fq = I.frequent_questions(bundle, top=10)
            if fq:
                st.dataframe(pd.DataFrame([{
                    "题号": r["题号"], "指标": r["指标"],
                    "答错人数": r["错误人数"], "错误率": f"{r['错误率']}%",
                } for r in fq]), width="stretch", hide_index=True)


# --------------------------------------------------------------------------
# 页面 3：任务 1 知识结构
# --------------------------------------------------------------------------
def render_knowledge(bundle: dict) -> None:
    st.subheader("任务 1 · 学习内容与要求梳理")
    rows = A.knowledge_rows(bundle)
    if not rows:
        st.error("cleaned_data.json 缺少 knowledge_structure，无法渲染。")
        return

    st.caption("每个观察指标一行：课标条目 → 教材页 → 对应题号 → 题量/满分/证据密度。"
               "证据密度 = 该指标下的已评分作答条数，用于判断结论是否可靠。")

    for t in A.THEMES:
        trows = [r for r in rows if r["theme"] == t]
        if not trows:
            continue
        with st.expander(f"{t} {trows[0]['theme_name']} · 课标 {trows[0]['course_standard']} · "
                         f"教材 {trows[0]['textbook_pages']}", expanded=True):
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

    st.download_button("⬇ 导出任务1 结构（UI 组装版，供 B 校对）",
                       data=json.dumps({"themes": bundle.get("knowledge")}, ensure_ascii=False, indent=2),
                       file_name="task1_knowledge_structure_ui.json", mime="application/json")
    st.caption("正式成果包请以 B 的 `task1_knowledge_structure.json` 为准；此文件仅用于交叉校对。")


# --------------------------------------------------------------------------
# 页面 4：数据质量
# --------------------------------------------------------------------------
def render_quality(bundle: dict, raw_dir: str) -> None:
    st.subheader("数据质量与清洗复核")
    rep = bundle.get("quality") or {}
    a_issues = rep.get("issues") or []
    st.markdown(
        f"A 的 `data_quality_report.json`：总记录 {rep.get('total_records', '—')}，"
        f"报告问题 **{len(a_issues)}** 条。")

    st.markdown("##### UI 侧独立复核（直接读原始 CSV，重算 8 条规则）")
    qr = A.quality_recheck(raw_dir)
    if qr is None:
        st.warning(f"未找到原始数据目录（`{raw_dir}`）或缺少 pandas，跳过独立复核。")
        return

    st.markdown(f"原始记录 **{qr['总记录']}** 条，命中问题规则 **{qr['问题数']}** 条。")
    df = pd.DataFrame(qr["明细"])
    st.dataframe(df, width="stretch", hide_index=True)
    st.caption("这 8 条规则对应任务 2「数据缺失、异常、重复记录的处理方式」，"
               "每条都能给出记录编号，评审核对时可逐条复现。")
    st.download_button("⬇ 导出质量复核 CSV",
                       data=df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="quality_recheck.csv", mime="text/csv")

    with st.expander("这些异常对结论的影响（写进文档即可）", expanded=False):
        st.markdown(
            "1. **得分越界**（2 条）会直接抬高 D16 的指标掌握度，须先截断；\n"
            "2. **评分点之和≠总分**（3 条）说明总分可能是人工录入，须以评分点为准重算；\n"
            "3. **修订版本**（14 行/7 组）若不去重，同一事件会被计两次；\n"
            "4. **待评分**（6 条）不是答错，不能计入掌握度；\n"
            "5. **未作答**（5 条）同理；\n"
            "6. **节点越界**（1 条，Q038 出现在未教不等式的 N01）会污染「前测」对照；\n"
            "7. **主题错标**（1 条）会让按主题聚合的数字偏移；\n"
            "8. **答案一致却 0 分**（1 条）属评分冲突，不能作为能力证据。")


# --------------------------------------------------------------------------
# 页面 5：成果文件（把 01–06 的其余产物接出来）
# --------------------------------------------------------------------------
def render_artifacts(bundle: dict) -> None:
    st.subheader("成果文件与外部产物")
    st.caption("这里集中提供 01–06 生成、但未内联进页面的文件；缺失的会在最右列标出原因。")

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
                    "task1_knowledge_structure.json": "归属 B，界面已用 cleaned_data 现组装替代",
                    "task3_recommendations.json": "归属 B，界面在建议区显示「待 B 交付」占位",
                }.get(r["file"], "尚未运行对应脚本")
                st.markdown(f"- `{r['file']}`：{hint}")

    # 05 的图谱可以直接内嵌预览（离线时若依赖 CDN 可能显示空白）
    kg = os.path.join(bundle["output_dir"], "knowledge_graph.html")
    if os.path.exists(kg):
        st.markdown("##### 知识图谱预览")
        if st.toggle("在页面内渲染（依赖 HTML 内的 CDN，离线可能空白）", key="kg_preview"):
            try:
                import streamlit.components.v1 as components

                with open(kg, encoding="utf-8") as f:
                    components.html(f.read(), height=620, scrolling=True)
            except OSError:
                st.warning("读取 knowledge_graph.html 失败。")
    else:
        st.info("`knowledge_graph.html` 尚未生成：先 `pip install pyvis`，再运行 "
                "`python 已完成脚本\\05_knowledge_graph.py`。")
