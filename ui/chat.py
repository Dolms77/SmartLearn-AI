# -*- coding: utf-8 -*-
"""智能对话窗口：像通用 AI 助手一样的气泡对话，答案受"事实白名单"约束。"""
from __future__ import annotations

import time

import streamlit as st

import adapter as A
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
    cv = A.class_view(bundle, cls)
    row = cv["class_theme"].get(cls, {})
    stats = (bundle.get("statistics") or {})
    by_q = sorted(cv["by_question"].items(), key=lambda kv: kv[1]["rate"])[:5]
    ind = sorted((stats.get("by_indicator") or {}).items(), key=lambda kv: kv[1].get("score_rate", 1))[:5]
    return {
        "class": cls,
        "students": row.get("students"),
        "overall": row.get("overall"),
        "theme_rates": {t: row.get(t) for t in ("T01", "T02", "T03")},
        "weakest_indicators": [{"indicator": k, "rate": v.get("score_rate"), "n": v.get("count")}
                               for k, v in ind],
        "weakest_questions": [{"question": k, "rate": v.get("rate"), "n": v.get("n")}
                              for k, v in by_q],
        "note": "只允许引用这些统计；证据不足的指标不得下结论。",
    }


def _teacher_offline(facts: dict) -> str:
    lines = [f"【离线模式】{facts['class']}：{facts['students']} 名学生，"
             f"班级得分率 {facts['overall']:.0%}。" if facts.get("overall") is not None
             else f"【离线模式】{facts['class']} 暂无班级统计。"]
    tr = facts.get("theme_rates") or {}
    if tr:
        lines.append("三主题：" + "；".join(f"{k} {v:.0%}" for k, v in tr.items() if v is not None))
    qs = facts.get("weakest_questions") or []
    if qs:
        lines.append("最薄弱题目：" + "；".join(
            f"{q['question']}（{q['rate']:.0%}，n={q['n']}）" for q in qs[:3]))
    ind = facts.get("weakest_indicators") or []
    if ind:
        lines.append("最薄弱指标：" + "；".join(
            f"{i['indicator']}（{i['rate']:.0%}）" for i in ind[:3]))
    lines.append("接入 DeepSeek 后这些数字会被整理成讲评话术；当前回答纯来自统计。")
    return "\n\n".join(lines)


def _answer(question: str, role: str, ident: str, bundle: dict, key: str | None, cache_dir: str) -> str:
    if role == "student":
        stt = (bundle.get("statistics") or {}).get("by_student", {}).get(ident, {})
        v = A.student_view(bundle, ident)
        facts = llm.build_facts(v, stt, A.class_view(bundle)["class_theme"])
    else:
        facts = _teacher_facts(bundle, ident)

    if key:
        try:
            return llm.answer_question(question, facts, key, cache_dir)
        except Exception as e:  # noqa: BLE001 - 网络/额度问题一律降级
            base = llm.offline_answer(question, facts) if role == "student" else _teacher_offline(facts)
            return base + f"\n\n（DeepSeek 调用失败：{type(e).__name__}，已回退离线回答）"
    return llm.offline_answer(question, facts) if role == "student" else _teacher_offline(facts)


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
        with st.chat_message(m["role"], avatar="🧑‍🎓" if m["role"] == "user" else None):
            st.markdown(m["content"])

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
        with st.chat_message("assistant"):
            st.markdown(theme.typing(), unsafe_allow_html=True)
    answer = _answer(question, role, ident, bundle, key, cache_dir)
    time.sleep(0.35)
    placeholder.empty()
    hist.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)
    st.caption("回答依据：结构化统计 + 证据白名单；" +
               ("已接入 DeepSeek 改写。" if key else "当前为离线模板，接入 API 后会更自然。"))
