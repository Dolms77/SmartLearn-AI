# -*- coding: utf-8 -*-
"""首页（三块式）：身份条 → KPI → 核心结论卡 → Tab（掌握度 / 错因 / 建议）。

设计目标：一屏看到"最重要的那句话"，两跳看到依据；表格只做配角。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import adapter as A
import charts as C
from comparison_dashboard import render_comparison
import design
import insights as I
import labels
import llm
from scoring_review import render_scoring_review, valid_rate
import theme
import views


# ---------------------------------------------------------------------------
# 核心结论：从数据里挑"最该说的那一句"
# ---------------------------------------------------------------------------
def _student_headline(v: dict) -> tuple[str, list[tuple[str, str]], str | None]:
    """返回 (一句话结论, 两个数字, 建议查看依据的指标)。"""
    sid = v["sid"]
    if v["coverage"]["decided"] == 0:
        return (f"{sid} 目前只有 {v['evidence_total']} 条有效记录，**还没有任何指标够 3 条证据**，"
                f"先不下结论——建议按下方「补测题单」补几次观察。",
                [("已作答指标", f"{v['coverage']['answered']}/9"), ("有效记录", f"{v['evidence_total']}")],
                None)
    if v["weak"]:
        top = v["weak"][0]
        rest = len(v["weak"]) + len(v["developing"]) - 1
        tail = f"另有 {rest} 个指标需要跟进。" if rest > 0 else ""
        return (f"最需要先补的是 **{top['name']}**，掌握度 {top['mastery']:.0%}。{tail}",
                [("掌握度", f"{top['mastery']:.0%}"), ("证据", f"{top['n']} 条")],
                top["code"])
    if v["developing"]:
        top = v["developing"][0]
        return (f"没有明显薄弱项，**{top['name']}**还在发展中，掌握度 {top['mastery']:.0%}，"
                f"适合做一次变式巩固。",
                [("掌握度", f"{top['mastery']:.0%}"), ("证据", f"{top['n']} 条")],
                top["code"])
    return (f"{sid} 的 {v['coverage']['decided']} 个可判定指标都达到「已掌握」，可以进入下一主题的迁移练习。",
            [("可判定", f"{v['coverage']['decided']}/9"), ("整体掌握度",
                                                       f"{v['overall']:.0%}" if v["overall"] is not None else "—")],
            None)


def _teacher_headline(bundle: dict, cls: str) -> tuple[str, list[tuple[str, str]], str | None]:
    """教师端结论卡：全部用本班口径，指标显示中文名称而不是代号。"""
    cv = A.class_view(bundle, cls)
    row = cv["class_theme"].get(cls, {})
    sp = I.class_scoring_points(bundle, cls, limit=3)
    others = [c for c in cv["classes"] if c != cls]
    gap = ""
    if others:
        d = (row.get("overall") or 0) - (cv["class_theme"].get(others[0], {}).get("overall") or 0)
        gap = f"，比 {others[0]} 高 {d:+.1%}"
    if sp:
        top = sp[0]
        # 评分点用中文定义（来自 fix 分支的改进），指标名走统一的名称映射
        point_name = I.scoring_point_name(bundle, top["评分点"]) or top["评分点"]
        ind_name = labels.ind_name(top.get("指标", ""), "", bundle.get("output_dir"))
        return (f"最该先讲 **{point_name}**（{ind_name}），全班得分率 {top['得分率']:.0%}"
                f"（{top['正确/总数']}）。讲评按「评分点 → 题目 → 变式」推进。",
                [("班级得分率", f"{(row.get('overall') or 0):.0%}"),
                 ("薄弱评分点", f"{sum(1 for x in I.class_scoring_points(bundle, cls) if x['得分率'] < 0.3)} 个")],
                None)
    return (f"{cls}：{row.get('students', 0)} 名学生，班级得分率 {(row.get('overall') or 0):.0%}{gap}。",
            [("学生数", f"{row.get('students', 0)}"),
             ("得分率", f"{(row.get('overall') or 0):.0%}")], None)


# ---------------------------------------------------------------------------
# 依据抽屉
# ---------------------------------------------------------------------------
@st.dialog("结论依据：记录明细")
def _evidence_dialog(bundle: dict, sid: str, code: str) -> None:
    recs = A.indicator_evidence(bundle, sid, code)
    v = A.student_view(bundle, sid)
    item = next((x for x in v["indicators"] if x["code"] == code), None)
    name = item["name"] if item else code
    st.markdown(f"**{code} {name}** · 证据 {len(recs)} 条")
    if recs:
        st.dataframe(
            [{"记录编号": r.get("record_id"), "节点": r.get("node_id"),
              "题号": r.get("question_id"), "得分": f"{r.get('score')}/{r.get('full_score')}",
              "评分点": r.get("scoring_point_scores") or "—",
              "我的作答": str(r.get("student_answer") or "—")[:40]} for r in recs],
            width="stretch", hide_index=True)
        diag = [d for d in v["errors"] if d.get("indicator_id") == code]
        if diag:
            st.markdown("**错因诊断**")
            for d in diag[:5]:
                st.markdown(f"- `{d.get('record_id')}` {d.get('question_id')}："
                            f"{d.get('error_type_code')} {d.get('error_type')} — {d.get('error_description', '')}")
    else:
        design.empty_state("🗂", "这个指标还没有作答记录", "做完同指标 3 道题，就能给出结论。")
    st.caption("仅统计已评分的作答记录。")


# ---------------------------------------------------------------------------
# 学生首页
# ---------------------------------------------------------------------------
def render_student_home(bundle: dict, sid: str, key: str | None, cache_dir: str) -> None:
    v = A.student_view(bundle, sid)
    stt = (bundle.get("statistics") or {}).get("by_student", {}).get(sid, {})

    design.identity_bar(
        theme.avatar_img(40),
        f"{sid} · {v['cls']}",
        f"有效记录 {v['evidence_total']} 条 · 可判定 {v['coverage']['decided']}/9 指标 · "
        f"错因 {len(v['errors'])} 条")

    design.kpi_row([
        ("可判定掌握度", f"{v['overall']:.0%}" if v["overall"] is not None else "—", "只用证据 ≥3 条的指标"),
        ("指标覆盖", f"{v['coverage']['decided']}/9", f"已作答 {v['coverage']['answered']} 个"),
        ("有效记录", f"{v['evidence_total']}", "已去重、已评分"),
        ("待补观察", f"{len(v['insufficient'])}", "证据 <3 条，暂不下结论"),
    ], tones=["", "", "", "warn" if v["insufficient"] else "ok"])

    headline, metrics, target = _student_headline(v)
    left, right = st.columns([5, 1])
    with left:
        design.conclusion_card("核心结论", headline, metrics)
    with right:
        st.write("")
        if target and st.button("看依据 →", key=f"ev_{sid}", width="stretch"):
            _evidence_dialog(bundle, sid, target)
        if v["insufficient"]:
            st.caption(f"⚪ {len(v['insufficient'])} 个指标证据不足")

    t1, t2, t3 = st.tabs(["📊 掌握度", "🔍 错因", "🎯 建议与提问"])

    with t1:
        c1, c2 = st.columns([1, 1])
        with c1:
            C.show(C.student_radar(v))
        with c2:
            C.show(C.indicator_bars(v))
        with st.expander("证据量分布（为什么有的指标不下结论）", expanded=False):
            C.show(C.evidence_bars(v))
            st.caption("灰线为门槛 3 条；低于门槛一律「证据不足」，不参与薄弱排序。")
        st.dataframe([{"知识点": i["name"], "编号": i["code"],
                       "掌握度": None if i["mastery"] is None else round(i["mastery"], 3),
                       "证据数": i["n"],
                       "判定": {"mastered": "已掌握", "developing": "发展中", "weak": "薄弱",
                                "insufficient": "证据不足"}[i["band"]]} for i in v["indicators"]],
                     width="stretch", hide_index=True)

    with t2:
        errs = v["errors"]
        if not errs:
            design.empty_state("✅", "没有可归因的错误记录", "保持节奏，做一次综合练习即可。")
        else:
            by_type: dict[str, int] = {}
            for e in errs:
                by_type[e.get("error_type") or "未分类"] = by_type.get(e.get("error_type") or "未分类", 0) + 1
            # 交换 label/value：错因类型用大字、数量用小字（kpi_row 的 value 是大字、label 是小字）
            design.kpi_row([(f"{n} 处", k, f"{n / len(errs):.0%}") for k, n in
                            sorted(by_type.items(), key=lambda kv: -kv[1])[:4]])
            st.dataframe([{"记录": e.get("record_id"), "题号": e.get("question_id"),
                           "指标": e.get("indicator_id"), "类型": e.get("error_type"),
                           "得分": f"{e.get('score')}/{e.get('full_score')}",
                           "说明": (e.get("error_description") or "")[:40]} for e in errs[:20]],
                         width="stretch", hide_index=True)
            with st.expander("规则 vs 本地模型（如已生成）", expanded=False):
                rows = []
                for e in errs[:10]:
                    d = (bundle.get("llm_diag") or {}).get(e.get("record_id")) or {}
                    rows.append({"记录": e.get("record_id"), "规则": f"{e.get('error_type_code')} {e.get('error_type')}",
                                 "模型": f"{d.get('error_type_code')} {d.get('error_type')}" if d else "—",
                                 "一致": ("✅" if d.get("agree_with_rule") else ("🔁 改判" if d.get("agree_with_rule") is False else "—")) if d else "—"})
                st.dataframe(rows, width="stretch", hide_index=True)

    with t3:
        rec = views._task3_for(bundle, sid)
        if rec:
            views._render_task3(rec, bundle.get("output_dir"))
        else:
            order = sorted(v["weak"] + v["developing"], key=lambda x: x["mastery"])
            if order:
                st.markdown("**按证据排出的第一步**（正式建议待 `task3_recommendations.json` 覆盖）")
                for i, x in enumerate(order[:3], 1):
                    qids = [q for q, m in bundle["question_map"].items() if m.get("indicator") == x["code"]]
                    done = {r["question_id"] for r in A.indicator_evidence(bundle, sid, x["code"])}
                    todo = [q for q in qids if q not in done]
                    st.markdown(f"{i}. **{x['name']}**（掌握度 {x['mastery']:.0%}，证据 {x['n']} 条）"
                                f"→ 练 {'、'.join(todo[:3]) if todo else '该指标变式题'}")
            else:
                design.empty_state("🎉", "没有薄弱指标", "可以进入下一主题的迁移练习。")
        if v["insufficient"]:
            st.markdown("**需要先补观察的指标**")
            st.dataframe([{"知识点": x["name"], "已有证据": x["n"], "编号": x["code"]}
                          for x in v["insufficient"]], width="stretch", hide_index=True)
        st.divider()
        st.markdown("**问学伴一句**")
        q = st.text_input("例如：我哪一块最薄弱？", key=f"home_q_{sid}",
                          label_visibility="collapsed", placeholder="输入你的学情问题")
        if st.button("提问", key=f"home_ask_{sid}") and q:
            facts = llm.build_facts(v, stt, A.class_view(bundle)["class_theme"])
            with st.spinner("正在生成回答…"):
                ans = llm.answer_question(q, facts, key, cache_dir)
            st.success(ans)


# ---------------------------------------------------------------------------
# 教师首页
# ---------------------------------------------------------------------------
def render_teacher_home(bundle: dict, cls: str) -> None:
    cv = A.class_view(bundle, cls)
    row = cv["class_theme"].get(cls, {})
    cms = I.class_mastery_summary(bundle).get(cls, {})
    sp_all = I.class_scoring_points(bundle, cls)
    ind_rates = I.class_indicator_rates(bundle, cls)
    q_rates = I.class_question_rates(bundle, cls)

    design.identity_bar(
        theme.avatar_img(40), "班级概览",
        f"{cls} 班 · {row.get('students', 0)} 名学生 · "
        f"{sum(1 for r in bundle['records'] if r.get('class_id') == cls)} 条有效作答")

    design.kpi_row([
        ("班级得分率", f"{(row.get('overall') or 0):.0%}", "Σ得分/Σ满分"),
        ("学生数", f"{row.get('students', 0)}", ""),
        ("可判定格子", f"{cms.get('decided', 0)}", f"共 {cms.get('students', 0) * 9} 个"),
        ("薄弱评分点", f"{len([x for x in sp_all if x['得分率'] < 0.3])}", "得分率 <30% 的评分点"),
    ])

    headline, metrics, _ = _teacher_headline(bundle, cls)
    design.conclusion_card("核心结论", headline, metrics)

    t1, t2, t3 = st.tabs(["📈 班级对比", "🔍 薄弱点", "👥 学生"])
    with t1:
        render_comparison(cls, cv["class_theme"], ind_rates, q_rates, A.INDICATOR_NAMES)
    with t2:
        st.markdown("**本班优先复盘的评分步骤**")
        st.caption("按得分率从低到高展示最多 12 项。红色表示得分率为 30% 或以下。")
        measured, missing = _scoring_review_rows(bundle, cls)
        if measured:
            render_scoring_review(measured[:12], key=f"scoring_review_{cls}")
        else:
            st.info("本班暂无有效的评分步骤得分记录。")
        if missing:
            with st.expander(f"暂无数据的评分步骤（{len(missing)} 项）"):
                render_scoring_review(missing, key=f"scoring_review_missing_{cls}")
        class_students = {r['student_id'] for r in bundle['records'] if r.get('class_id') == cls}
        counts = {}
        for d in bundle.get('diagnoses', []):
            if d.get('student_id') in class_students:
                code = d.get('error_type_code') or d.get('error_type', '未分类')
                counts.setdefault(code, {'代码': code, '类型': d.get('error_type', code), '条数': 0})['条数'] += 1
        total_errors = sum(r['条数'] for r in counts.values())
        et = [{**r, '占比': 100 * r['条数'] / total_errors} for r in counts.values()] if total_errors else []
        if et:
            st.markdown("**本班错因构成**")
            st.caption("每条诊断计一次。悬停查看各类条数与占比。")
            _, ring, _ = st.columns([1, 3, 1])
            with ring:
                C.show(C.error_type_chart(et))
        st.markdown(f"**{cls} 班全员掌握度矩阵**")
        sort_mode = st.radio(
            "矩阵排序",
            ["学生编号", "平均掌握度"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"mastery_matrix_sort_{cls}",
        )
        matrix = I.mastery_heatmap(
            bundle, class_id=cls, clustered=sort_mode == "平均掌握度")
        st.caption(
            "气泡大小与颜色表示掌握度（红 <40% · 燕麦色 40–70% · 绿 ≥70%）；"
            "灰色空心点表示证据不足。悬停查看掌握度、正确记录数和证据数。"
        )
        C.show(C.mastery_bubble_matrix_chart(matrix))
    with t3:
        rows = []
        for sid in A.list_students(bundle):
            sv = A.student_view(bundle, sid)
            if sv["cls"] != cls:
                continue
            rows.append({"学生": sid, "班级": sv["cls"], "有效记录": sv["evidence_total"],
                         "可判定": f"{sv['coverage']['decided']}/9",
                         "可判定掌握度": "—" if sv["overall"] is None else f"{sv['overall']:.0%}",
                         "状态": "证据不足" if sv["coverage"]["decided"] == 0 else
                                 ('需关注' if sv['overall'] is not None and sv['overall'] < 0.4 else '正常')})
        st.dataframe(rows, width="stretch", hide_index=True)


def _scoring_review_rows(bundle: dict, cls: str) -> tuple[list[dict], list[dict]]:
    """旧数据可能以零分填补空记录，只有有效满分与作答数才采用得分率。"""
    stats = bundle.get("statistics") or {}
    points = (stats.get("by_class_scoring_point") or {}).get(cls) or {}
    ids = set(points) | set(stats.get("by_scoring_point") or {})
    for question in bundle["question_map"].values():
        ids.update(question.get("scoring_point_definitions") or {})

    measured, missing = [], []
    for pid in sorted(ids):
        record = points.get(pid) or {}
        rate = record.get("score_rate")
        if not ((record.get("count") or 0) > 0 and (record.get("full") or 0) > 0 and valid_rate(rate)):
            rate = None
        question = bundle["question_map"].get(pid.split("P")[0], {})
        definition = (question.get("scoring_point_definitions") or {}).get(pid) or {}
        description = definition.get("description") or I.scoring_point_name(bundle, pid)
        if description.strip(" \t。；") == "答案正确":
            indicator = question.get("indicator", "")
            prompt = question.get("question_text") or A.INDICATOR_NAMES.get(indicator, "")
            description = " · ".join(filter(None, [question.get("type"), prompt])) or description
        item = {
            "id": pid,
            "description": description,
            "rate": rate,
        }
        (missing if rate is None else measured).append(item)
    measured.sort(key=lambda item: (item["rate"], -points[item["id"]]["count"]))
    return measured, missing
