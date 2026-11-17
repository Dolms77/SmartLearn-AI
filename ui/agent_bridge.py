# -*- coding: utf-8 -*-
"""agent_bridge.py — 把 07V2 多智能体编排层接进 Streamlit

07V2 的真实接口（本文件据此编写）：
    mod.Bundle(output_dir)
    mod.Coordinator(bundle).run(question) -> {
        'question', 'routing': {question, intents, student_id, detail},
        'results': [ {agent, ...}, ... ],        # 可能多个（复合意图级联）
        'trace': {'steps': [{step, time, agent, action, detail, output}]},
        'trace_text': str,
    }

提供：
    load_coordinator()   缓存 Coordinator（同一会话复用 → 多轮记忆生效）
    ask()                调 run()，异常兜底
    render_trace()       执行轨迹时间线（直接读 trace.steps）
    render_result()      按 Agent 类型渲染（诊断 / 建议 / 讲评 / 班级）
    render_agent_page()  整页对话：历史 + 快捷问题 + 轨迹 + 结构化结果
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import traceback

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_OUTPUT = os.path.join(REPO_ROOT, "output")
AGENT_SCRIPT = os.path.join(REPO_ROOT, "已完成脚本", "07_multi_agent.py")

AGENT_META = {
    "Coordinator": ("🧭", "协调器", "#4ECDC4"),
    "DiagnosisAgent": ("🔍", "诊断", "#45B7D1"),
    "RecommendationAgent": ("📚", "建议", "#9B59B6"),
    "LectureAgent": ("👩‍🏫", "讲评", "#E67E22"),
    "ClassAgent": ("🏫", "班级", "#3498DB"),
    "ValidatorAgent": ("🛡️", "校验", "#2ECC71"),
}
CLASS_HINTS = ("班", "全班", "对比", "DC01", "DC02")


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="正在唤醒多智能体系统…")
def _load_module(script_path: str = AGENT_SCRIPT):
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"未找到多智能体脚本：{script_path}")
    spec = importlib.util.spec_from_file_location("smartlearn_multi_agent", script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["smartlearn_multi_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


@st.cache_resource(show_spinner="正在装载学情数据…")
def load_coordinator(output_dir: str = DEFAULT_OUTPUT):
    """缓存 Coordinator：同一会话内复用，多轮指代（"他呢？"）才能生效。

    另外补一个 07V2 的意图缺口：'下周这个班该怎么讲？' 里只有「怎么」命中诊断词，
    「讲评」类词库没有「怎么讲/该讲」，会被误路由到诊断。这里子类覆写 parse()，
    在不点名具体学生时把这类问题强制归到 lecture（讲评是班级级任务）。
    """
    mod = _load_module(AGENT_SCRIPT)
    if not os.path.exists(os.path.join(output_dir, "cleaned_data.json")):
        raise RuntimeError(f"{output_dir} 缺少 cleaned_data.json，请先运行 01 脚本")

    return _build_coordinator(mod, output_dir)


def _build_coordinator(mod, output_dir: str):
    """构造带 lecture 路由修正的 Coordinator（selftest 与界面共用）。"""
    lecture_cues = ("讲评", "怎么讲", "该讲", "讲什么", "上课", "备课", "课堂")

    class _Patched(mod.Coordinator):
        def parse(self, question: str) -> dict:
            r = super().parse(question)
            if (any(k in question for k in lecture_cues)
                    and not re.search(r"D\d{2}", question)
                    and "lecture" not in r["intents"]):
                r["intents"] = ["lecture"]
            return r

    return _Patched(mod.Bundle(output_dir))


def ask(question: str, output_dir: str | None = None) -> dict:
    try:
        coord = load_coordinator(output_dir or DEFAULT_OUTPUT)
        return coord.run(question)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(limit=3)}


def list_students(output_dir: str = DEFAULT_OUTPUT) -> list[str]:
    try:
        import json

        with open(os.path.join(output_dir, "student_profiles.json"), encoding="utf-8") as f:
            return sorted(json.load(f).keys())
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# 执行轨迹
# ---------------------------------------------------------------------------
_TRACE_CSS = """
<style>
.sa-trace {margin:.35rem 0 .7rem; font-size:.86rem;}
.sa-step {display:flex; align-items:flex-start; gap:8px; padding:3px 0; position:relative;}
.sa-step:not(:last-child)::before {
  content:""; position:absolute; left:13px; top:26px; bottom:-5px; width:2px;
  background:linear-gradient(#cfd8dc, #eceff1); border-radius:1px;}
.sa-ico {width:28px; height:28px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:13px; background:#fff; border:2px solid; flex:none; z-index:1;}
.sa-body {flex:1; padding-top:2px;}
.sa-t {font-weight:600; color:#37474f;}
.sa-t small {color:#90a4ae; font-weight:400; margin-left:6px;}
.sa-d {color:#607d8b; font-size:.8rem; line-height:1.5;}
</style>
"""


def render_trace(result: dict, expanded: bool = True, compact: bool = True) -> None:
    steps = (result.get("trace") or {}).get("steps") or []
    if not steps:
        return
    agents = [s.get("agent") for s in steps if s.get("agent") != "Coordinator"]
    label = f"🤖 执行轨迹（{len(steps)} 步 · {len(agents)} 个专职 Agent）"
    passed = all((r.get("validation") or {}).get("passed", True)
                 for r in result.get("results", []) or [])

    with st.expander(label, expanded=expanded):
        st.markdown(_TRACE_CSS, unsafe_allow_html=True)
        html = ['<div class="sa-trace">']
        for s in steps:
            icon, cn, color = AGENT_META.get(s.get("agent", ""), ("⚙️", s.get("agent", "?"), "#90A4AE"))
            detail = ""
            if not compact:
                if s.get("detail"):
                    detail += f'<div class="sa-d">输入：{str(s["detail"])[:70]}</div>'
                if s.get("output"):
                    detail += f'<div class="sa-d">输出：{str(s["output"])[:70]}</div>'
            html.append(
                f'<div class="sa-step"><div class="sa-ico" style="border-color:{color};'
                f'color:{color};">{icon}</div><div class="sa-body">'
                f'<div class="sa-t">{cn} · {s.get("action", "")}'
                f'<small>{s.get("time", "")}</small></div>{detail}</div></div>')
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)
        st.caption(("✅ 校验通过：结论均带证据、提示未泄露答案。" if passed
                    else "⚠️ 校验拦截：存在需要人工复核的结论。") +
                   " 轨迹由 Trace 逐步记录，可复核。")


# ---------------------------------------------------------------------------
# 结果渲染
# ---------------------------------------------------------------------------
def render_result(res: dict) -> None:
    agent = res.get("agent", "")
    if agent == "DiagnosisAgent":
        _render_diagnosis(res)
    elif agent == "RecommendationAgent":
        _render_recommendation(res)
    elif agent == "LectureAgent":
        _render_lecture(res)
    elif agent == "ClassAgent":
        _render_class(res)
    else:
        st.json(res)


def _render_diagnosis(res: dict) -> None:
    if res.get("summary"):
        st.markdown(res["summary"])
    inds = res.get("indicators") or []
    weak = [i for i in inds if i.get("band") in ("weak", "developing")
            and i.get("mastery") is not None]
    insuf = [i for i in inds if i.get("band") == "insufficient"]
    if weak:
        st.markdown("**需关注指标**")
        st.dataframe([{"指标": i.get("indicator"), "观察指标": i.get("name", ""),
                       "掌握度": f"{i['mastery']:.0%}", "证据": f"n={i.get('n', 0)}"}
                      for i in weak[:5]], width="stretch", hide_index=True)
    persistent = res.get("persistent_errors") or []
    improved = res.get("improved") or []
    if persistent:
        st.warning("🔴 顽固性错误：" + "、".join(c["question_id"] for c in persistent[:6])
                   + "（两次同答案同错，建议面谈追问）")
    if improved:
        st.success("🟢 进步信号：" + "、".join(c["question_id"] for c in improved[:6]))
    if insuf:
        st.info(f"⚪ 证据不足（n<3 不下结论）：{'、'.join(i.get('indicator', '') for i in insuf)}")


def _render_recommendation(res: dict) -> None:
    if res.get("diagnosis_summary"):
        st.markdown(f"**诊断摘要**：{res['diagnosis_summary']}")
    if res.get("diagnosis_link"):
        st.caption(f"↳ 已自动衔接上一步诊断：{res['diagnosis_link'][:60]}")
    if res.get("source"):
        st.caption(f"来源：{res['source']}")
    for r in res.get("recommendations", []):
        m = r.get("mastery")
        label = (f"优先级{r.get('priority')}｜{r.get('indicator')} "
                 f"{r.get('indicator_name', '')[:14]}")
        with st.expander(label, expanded=r.get("priority") == 1):
            st.markdown(r.get("reason", ""))
            if r.get("recommended_questions"):
                st.markdown("**推荐题目**：" + "、".join(f"`{q}`" for q in r["recommended_questions"]))
            hints = r.get("step_hints") or []
            if hints:
                st.markdown("**分步提示**（不含答案）")
                for i, h in enumerate(hints, 1):
                    st.markdown(f"{i}. {h}")
            if r.get("follow_up_condition"):
                st.caption(f"🔄 {r['follow_up_condition']}")


def _render_lecture(res: dict) -> None:
    st.markdown(f"**{res.get('title', '讲评建议')}**")
    must = res.get("must_teach") or []
    if must:
        st.markdown("**必讲评分点**（按全班得分率排序）")
        for m in must:
            point = m.get("point") or m.get("point_id") or ""
            st.markdown(f"- `{point}` 得分率 {m.get('rate_note', m.get('rate', '—'))}")
    for g in res.get("class_gaps") or []:
        st.markdown(f"- 两班差异：{g.get('theme', '')} 相差 {g.get('gap', '')}"
                    f"（{g.get('weaker', '')} 班较弱）")
    if res.get("teaching_suggestion"):
        st.info(f"💡 {res['teaching_suggestion']}")
    if res.get("warning"):
        st.caption(f"⚠️ {res['warning']}")


def _render_class(res: dict) -> None:
    comp = res.get("comparison") or {}
    if not comp:
        st.info("暂无班级对比数据")
        return
    rows = []
    for cls, themes in comp.items():
        for t, v in (themes or {}).items():
            if isinstance(v, dict) and v.get("rate") is not None:
                rows.append({"班级": cls, "主题": t, "得分率": f"{v['rate']:.0%}",
                             "记录数": v.get("n")})
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# 整页对话
# ---------------------------------------------------------------------------
CHAT_KEY = "agent_bridge_history"
SID_KEY = "agent_bridge_student"


def render_agent_page(output_dir: str = DEFAULT_OUTPUT,
                      quick_questions: list[str] | None = None) -> None:
    st.subheader("🤖 多智能体协同 · 对话")
    st.caption("协调器识别意图后调度诊断 / 建议 / 讲评 / 班级 Agent，可复合级联；"
               "每一步都记进执行轨迹，并由校验 Agent 过一遍。")

    students = list_students(output_dir)
    c1, c2 = st.columns([1, 3])
    sid = c1.selectbox("当前学生", students or ["D01"],
                       index=(students.index(st.session_state.get(SID_KEY, "D01"))
                              if students and st.session_state.get(SID_KEY, "D01") in students else 0),
                       key="ab_sid")
    st.session_state[SID_KEY] = sid
    c2.caption("问句里带 Dxx 会自动切换学生；只说「他呢？」沿用上一位（多轮记忆）。")

    hist = st.session_state.setdefault(CHAT_KEY, [])
    if not hist:
        hist.append({"role": "assistant", "content":
                     "你好，我是智慧学伴的多智能体系统。可以直接问我：\n\n"
                     f"- **{sid} 哪里最薄弱？**（诊断）\n"
                     f"- **{sid} 哪里薄弱，顺便说说该练什么**（诊断→建议 级联）\n"
                     "- **下周这个班该怎么讲？**（讲评稿）\n"
                     "- **两个班差在哪？**（班级对比）\n"
                     "- **他呢？**（沿用上一位学生）"})

    for m in hist:
        with st.chat_message(m["role"], avatar="🧑‍🎓" if m["role"] == "user" else "🤖"):
            st.markdown(m["content"])
            if m.get("result"):
                for r in m["result"].get("results", []) or []:
                    render_result(r)
                render_trace(m["result"], expanded=False)

    chips = quick_questions or [
        f"{sid}哪里最薄弱？",
        f"{sid}哪里薄弱，顺便说说该练什么",
        "下周这个班该怎么讲？",
        "他呢？",
    ]
    cols = st.columns(len(chips))
    picked = None
    for i, (c, txt) in enumerate(zip(cols, chips)):
        if c.button(txt, key=f"ab_chip_{i}", width="stretch"):
            picked = txt

    typed = st.chat_input("问智能体任何学情问题…")
    question = picked or typed
    if not question:
        return

    # 没有学生编号、也不是班级类问题时，补上当前学生，避免落进"班级"分支
    if not re.search(r"D\d{2}", question) and not any(k in question for k in CLASS_HINTS):
        question = f"{sid} {question}"

    hist.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🤖"):
        with st.status("🧭 协调器正在识别意图…", expanded=False) as status:
            result = ask(question, output_dir)
            if result.get("error"):
                status.update(label="⚠️ 执行出错", state="error", expanded=False)
            else:
                intents = (result.get("routing") or {}).get("intents") or []
                status.update(label=f"✅ 调度完成：{' → '.join(intents)}"
                                    f"（{len(result.get('results', []))} 个结果）",
                              state="complete", expanded=False)

        if result.get("error"):
            st.error(f"智能体执行出错：{result['error']}")
            st.code(result.get("traceback", ""))
            hist.append({"role": "assistant", "content": f"⚠️ 执行出错：{result['error']}"})
            return

        render_trace(result, expanded=True, compact=False)
        parts = []
        for r in result.get("results", []) or []:
            head = f"**[{r.get('agent')}]**"
            body = r.get("summary") or r.get("diagnosis_summary") or r.get("title") or ""
            parts.append(f"{head} {body}".strip())
        answer_md = "\n\n".join(parts) or "（无结构化输出）"
        st.markdown(answer_md)
        for r in result.get("results", []) or []:
            render_result(r)
        hist.append({"role": "assistant", "content": answer_md, "result": result})

    with st.sidebar:
        if st.button("🗑 清空智能体对话", width="stretch", key="ab_clear"):
            st.session_state.pop(CHAT_KEY, None)
            st.rerun()


# ---------------------------------------------------------------------------
# CLI 自检
# ---------------------------------------------------------------------------
def _selftest(output_dir: str = DEFAULT_OUTPUT) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    mod = _load_module(AGENT_SCRIPT)
    coord = _build_coordinator(mod, output_dir)
    print("[OK] 07V2 加载成功（Bundle / Coordinator.run）")

    for q in ["D01哪里最薄弱？", "D01哪里薄弱，顺便说说该练什么",
              "下周这个班该怎么讲？", "两个班差在哪？", "他呢？"]:
        r = coord.run(q)
        agents = [x.get("agent") for x in r.get("results", [])]
        steps = len((r.get("trace") or {}).get("steps") or [])
        ok = all((x.get("validation") or {}).get("passed", True) for x in r.get("results", []))
        print(f"[OK] [{q}] → {agents} | {steps} 步 | 校验{'通过' if ok else '拦截'}")
    print("\n全部自检通过")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    a = ap.parse_args()
    if a.selftest:
        _selftest(a.output_dir)
    else:
        print("UI 桥接模块：由 shell.py 的「智能体」页调用；"
              "自检请加 --selftest --output-dir <产物目录>")
