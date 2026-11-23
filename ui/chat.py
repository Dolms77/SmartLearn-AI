# -*- coding: utf-8 -*-
"""智能对话窗口：像通用 AI 助手一样的气泡对话，答案受"事实白名单"约束。"""
from __future__ import annotations

import time

import streamlit as st

import adapter as A
import insights as I
import labels
import llm
import theme

STUDENT_GREET = (
    "你好，我是你的学伴。我已经读完你**全部 {n} 条**作答记录，"
    "能定位到具体题号和评分点。\n\n"
    "我只在证据足够时下结论——所以你可能会听到我说「这个还看不出」，"
    "那不是敷衍，是数据真的不够。"
)

TEACHER_GREET = (
    "你好，我是 {cls} 的班级助手。我已汇总 **{n} 名学生 / {m} 条**作答记录，"
    "可以按主题、指标、评分点三个粒度给你讲评建议。\n\n"
    "注意：30% 左右的「学生×指标」格子证据不足 3 条，我会明确标出来，不猜。"
)

STUDENT_CHIPS = ["我哪一块最薄弱？", "哪些结论其实证据不足？", "我错得最多的是什么类型？",
                 "给我一个这周能做完的计划"]
TEACHER_CHIPS = ["这个班最该讲哪几道题？", "哪个评分点全班都错？", "两个班差在哪？",
                 "哪些学生需要单独关注？"]


def _key(role: str, ident: str) -> str:
    return f"chat_{role}_{ident}"


def history(role: str, ident: str) -> list[dict]:
    return st.session_state.setdefault(_key(role, ident), [])


def _teacher_facts(bundle: dict, cls: str) -> dict:
    """教师端事实白名单：全部按“本班”口径，含评分点、学生名单与证据覆盖。"""
    cv = A.class_view(bundle, cls)
    row = cv["class_theme"].get(cls, {})
    qrates = I.class_question_rates(bundle, cls)
    irates = I.class_indicator_rates(bundle, cls)
    cov = I.class_mastery_summary(bundle).get(cls, {})

    weak_q = sorted(qrates.items(), key=lambda kv: kv[1]["rate"])[:5]
    weak_i = sorted(((c, v) for c, v in irates.items() if v["rate"] is not None),
                    key=lambda kv: kv[1]["rate"])[:5]
    return {
        "class": cls,
        "students": row.get("students"),
        "overall": row.get("overall"),
        "theme_rates": {t: row.get(t) for t in ("T01", "T02", "T03")},
        "weakest_indicators": [{"indicator": c, "rate": v["rate"], "n": v["n"]} for c, v in weak_i],
        "weakest_questions": [{"question": k, "rate": v["rate"], "n": v["n"],
                               "text": v.get("text", "")} for k, v in weak_q],
        "scoring_points": I.class_scoring_points(bundle, cls, limit=8),
        "students_at_risk": I.students_at_risk(bundle, cls),
        "coverage": {"decided": cov.get("decided"), "students": cov.get("students"),
                     "rate": cov.get("decided_rate")},
        "class_compare": {c: cv["class_theme"].get(c, {}) for c in cv["classes"]},
        "note": "全部为班级口径；证据不足（n<3）的指标不得下结论。",
    }


def _answer(question: str, role: str, ident: str, bundle: dict, key: str | None, cache_dir: str,
            history: list[dict] | None = None) -> str:
    if role == "student":
        stt = (bundle.get("statistics") or {}).get("by_student", {}).get(ident, {})
        v = A.student_view(bundle, ident)
        facts = llm.build_facts(v, stt, A.class_view(bundle)["class_theme"])
    else:
        facts = _teacher_facts(bundle, ident)

    if key:
        try:
            return llm.answer_question(question, facts, key, cache_dir,
                                       role=role, history=history)
        except Exception as e:  # noqa: BLE001 - 网络/额度问题一律降级
            return (llm.offline_answer(question, facts, history)
                    + f"\n\n（本地模型调用失败：{type(e).__name__}，已回退离线回答）")
    return llm.offline_answer(question, facts, history)


def render(bundle: dict, role: str, ident: str, key: str | None, cache_dir: str) -> None:
    hist = history(role, ident)
    n = len(bundle["records"])

    if not hist:
        if role == "student":
            v = A.student_view(bundle, ident)
            hist.append({"role": "assistant", "content": STUDENT_GREET.format(n=v["evidence_total"])})
            hist.append({"role": "assistant", "content":
                         f"先说结论：你 9 个指标里 **{v['coverage']['decided']} 个**有足够证据，"
                         f"{len(v['insufficient'])} 个还不够。想知道哪一个最拖后腿，点下面的问题就行。"})
        else:
            row = A.class_view(bundle, ident)["class_theme"].get(ident, {})
            hist.append({"role": "assistant",
                         "content": TEACHER_GREET.format(cls=ident, n=row.get("students", 0), m=n)})

    for m in hist:
        with st.chat_message(m["role"], avatar="🧑‍🎓" if m["role"] == "user" else theme.character_path()):
            st.markdown(labels.humanize(m["content"], bundle.get("output_dir"))
                        if m["role"] != "user" else m["content"])

    chips = STUDENT_CHIPS if role == "student" else TEACHER_CHIPS
    st.caption("试试这样问：")
    cols = st.columns(len(chips))
    picked = None
    for i, (c, txt) in enumerate(zip(cols, chips)):
        if c.button(txt, key=f"chip_{role}_{ident}_{i}", width="stretch"):
            picked = txt

    typed = st.chat_input("问我任何关于" + ("你" if role == "student" else "这个班") + "学习情况的问题…")
    question = picked or typed
    if not question:
        return

    hist.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(question)

    placeholder = st.empty()
    with placeholder.container():
        with st.chat_message("assistant", avatar=theme.character_path()):
            st.markdown(theme.typing(), unsafe_allow_html=True)
    answer = labels.humanize(
        _answer(question, role, ident, bundle, key, cache_dir, history=hist[:-1][-4:]),
        bundle.get("output_dir"))
    time.sleep(0.35)
    placeholder.empty()
    hist.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant", avatar=theme.character_path()):
        st.markdown(answer)
    st.caption("回答依据：结构化统计 + 证据白名单；" +
               "数字与结论来自结构化统计，口吻由本地模型改写；模型不可用时自动回退模板。")
