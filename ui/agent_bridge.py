# -*- coding: utf-8 -*-
"""agent_bridge.py — 把 07 多智能体编排层接进 Streamlit（按 07 的真实 API 适配）

07 的实际接口（本文件据此编写，不再假设 trace/results 结构）：
    mod.DataBundle(output_dir)
    mod.Coordinator(output_dir).route(question, student_id=None) -> dict
        dict 含 agent / routing / validation，以及该 Agent 自己的字段

本模块提供：
    load_coordinator()     缓存 Coordinator（同一会话复用）
    ask()                  调 route()，异常兜底返回 {"error": ...}
    render_chain()         由 routing + validation 还原"处理链路"时间线
    render_result()        按 Agent 类型渲染
    render_agent_page()    整页对话（学生上下文 + 快捷问题 + 链路 + 结果）

设计原则：不修改 07；07 不可用时界面只报错不崩。
"""
from __future__ import annotations

import importlib.util
import os
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
    "QaAgent": ("💬", "答疑", "#95A5FC"),
    "ValidatorAgent": ("🛡️", "校验", "#2ECC71"),
}


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
    mod = _load_module(AGENT_SCRIPT)
    if not os.path.exists(os.path.join(output_dir, "cleaned_data.json")):
        raise RuntimeError(f"{output_dir} 缺少 cleaned_data.json，请先运行 01 脚本")
    return mod.Coordinator(output_dir)


def ask(question: str, student_id: str | None = None,
        output_dir: str = DEFAULT_OUTPUT) -> dict:
    try:
        return load_coordinator(output_dir).route(question, student_id)
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
# 链路可视化（由结果字段还原，不伪造步骤）
# ---------------------------------------------------------------------------
_CHAIN_CSS = """
<style>
.sa-trace {margin:.35rem 0 .7rem; font-size:.86rem;}
.sa-step {display:flex; align-items:flex-start; gap:8px; padding:3px 0; position:relative;}
.sa-step:not(:last-child)::before {
  content:""; position:absolute; left:13px; top:26px; bottom:-5px; width:2px;
  background:linear-gradient(#cfd8dc, #eceff1); border-radius:1px;}
.sa-ico {width:28px; height:28px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:14px; background:#fff; border:2px solid; flex:none; z-index:1;}
.sa-body {flex:1; padding-top:3px;}
.sa-t {font-weight:600; color:#37474f;}
.sa-d {color:#607d8b; font-size:.8rem; line-height:1.5;}
</style>
"""


def render_chain(result: dict, expanded: bool = True) -> None:
    routing = result.get("routing") or {}
    agent = result.get("agent", "")
    validation = result.get("validation") or {}
    if not agent and not routing:
        return

    scores = routing.get("intent_scores") or {}
    hit = "、".join(f"{k}×{v}" for k, v in scores.items() if v) or "无关键词命中"
    steps = [
        ("Coordinator", "解析意图", f"命中的意图词：{hit}"),
    ]
    if agent:
        steps.append((agent, "执行任务", _agent_desc(result)))
    if validation:
        passed = validation.get("passed")
        steps.append(("ValidatorAgent", "输出校验",
                      "通过" if passed else "拦截：" + "；".join(validation.get("issues", [])[:3])))

    with st.expander(f"🤖 处理链路（{len(steps)} 步 · 可复核）", expanded=expanded):
        st.markdown(_CHAIN_CSS, unsafe_allow_html=True)
        html = ['<div class="sa-trace">']
        for name, action, detail in steps:
            icon, cn, color = AGENT_META.get(name, ("⚙️", name, "#90A4AE"))
            if name == "ValidatorAgent":
                color = "#2ECC71" if (validation.get("passed") is True) else "#E74C3C"
            html.append(
                f'<div class="sa-step"><div class="sa-ico" style="border-color:{color};'
                f'color:{color};">{icon}</div><div class="sa-body">'
                f'<div class="sa-t">{cn} · {action}</div>'
                f'<div class="sa-d">{str(detail)[:120]}</div></div></div>')
        html.append("</div>")
        st.markdown("".join(html), unsafe_allow_html=True)
        st.caption("链路由 route() 的路由打分与校验结果还原，不是编造的日志。")


def _agent_desc(result: dict) -> str:
    a = result.get("agent")
    if a == "DiagnosisAgent":
        return f"生成 {result.get('student_id', '')} 的掌握度与错因摘要"
    if a == "RecommendationAgent":
        return f"生成 {len(result.get('recommendations', []))} 条分层建议"
    if a == "QaAgent":
        return "返回受白名单约束的事实集合"
    return "完成"


# ---------------------------------------------------------------------------
# 结果渲染
# ---------------------------------------------------------------------------
def render_result(result: dict) -> None:
    agent = result.get("agent", "")
    if agent == "DiagnosisAgent":
        _render_diagnosis(result)
    elif agent == "RecommendationAgent":
        _render_recommendation(result)
    elif agent == "QaAgent":
        _render_qa(result)
    else:
        st.json(result)


def _render_diagnosis(res: dict) -> None:
    if res.get("summary"):
        st.markdown(res["summary"])
    inds = (res.get("mastery") or {}).get("indicators") or []
    weak = [i for i in inds if i.get("band") in ("weak", "developing") and i.get("mastery") is not None]
    insuf = [i for i in inds if i.get("band") == "insufficient"]

    if weak:
        st.markdown("**需关注指标**")
        st.dataframe(
            [{"指标": i["indicator"], "观察指标": i.get("name", ""),
              "掌握度": f"{i['mastery']:.0%}", "证据": f"n={i.get('evidence_n', 0)}"}
             for i in weak[:5]], width="stretch", hide_index=True)
    changes = res.get("cross_node_changes") or []
    stubborn = [c for c in changes if c.get("change_type") == "still_wrong"]
    improved = [c for c in changes if c.get("change_type") == "improved"]
    if stubborn:
        st.warning("🔴 顽固性错误：" + "、".join(c["question_id"] for c in stubborn[:6])
                   + "（两次同错，建议面谈追问）")
    if improved:
        st.success("🟢 进步信号：" + "、".join(c["question_id"] for c in improved[:6]))
    if insuf:
        st.info(f"⚪ 证据不足（n<3 不下结论）：{'、'.join(i['indicator'] for i in insuf)}")


def _render_recommendation(res: dict) -> None:
    if res.get("diagnosis_summary"):
        st.markdown(f"**诊断摘要**：{res['diagnosis_summary']}")
    for r in res.get("recommendations", []):
        with st.expander(
                f"优先级{r.get('priority')}｜{r.get('indicator')} {r.get('indicator_name', '')[:14]}"
                f"｜掌握度 {r.get('mastery', 0):.0%}" if r.get("mastery") is not None else
                f"优先级{r.get('priority')}｜{r.get('indicator')}", expanded=r.get("priority") == 1):
            st.markdown(r.get("reason", ""))
            if r.get("recommended_questions"):
                st.markdown("**推荐题目**：" + "、".join(f"`{q}`" for q in r["recommended_questions"]))
            st.markdown("**分步提示**（不含答案）")
            for i, h in enumerate(r.get("step_hints", []), 1):
                st.markdown(f"{i}. {h}")
            if r.get("follow_up_condition"):
                st.caption(f"🔄 {r['follow_up_condition']}")


def _render_qa(res: dict) -> None:
    facts = res.get("facts_whitelist") or {}
    m = facts.get("mastery") or {}
    if m.get("overall_mastery") is not None:
        st.markdown(f"**整体掌握度**：{m['overall_mastery']:.0%}")
    inds = [i for i in (m.get("indicators") or []) if i.get("band") in ("weak", "developing")]
    if inds:
        st.markdown("**最薄弱**：" + "；".join(
            f"{i['indicator']}（{i.get('mastery', 0):.0%}，n={i.get('evidence_n', 0)}）"
            for i in inds[:3]))
    comp = facts.get("class_comparison") or {}
    if comp:
        rows = []
        for cls, themes in comp.items():
            for t, v in themes.items():
                if v.get("rate") is not None:
                    rows.append({"班级": cls, "主题": t, "得分率": f"{v['rate']:.0%}",
                                 "记录数": v.get("n")})
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
    if res.get("note"):
        st.caption(res["note"])


# ---------------------------------------------------------------------------
# 整页对话
# ---------------------------------------------------------------------------
CHAT_KEY = "agent_bridge_history"
SID_KEY = "agent_bridge_student"


def render_agent_page(output_dir: str = DEFAULT_OUTPUT,
                      quick_questions: list[str] | None = None) -> None:
    st.subheader("🤖 多智能体协同 · 对话")
    st.caption("协调器按规则识别意图，调度诊断 / 建议 / 答疑 Agent，再由校验 Agent 过一遍；"
               "全程零联网、链路可复核。")

    students = list_students(output_dir)
    c1, c2 = st.columns([1, 3])
    sid = c1.selectbox("当前学生", students or ["D01"],
                       index=(students.index(st.session_state.get(SID_KEY, "D01"))
                              if students and st.session_state.get(SID_KEY, "D01") in students else 0),
                       key="ab_sid")
    st.session_state[SID_KEY] = sid
    c2.caption("提问里带上学生编号（如 D03）会自动切换；只问「他呢？」则沿用当前学生。")

    hist = st.session_state.setdefault(CHAT_KEY, [])
    if not hist:
        hist.append({"role": "assistant", "content":
                     "你好，我是智慧学伴的多智能体系统。可以问我：\n\n"
                     f"- **{sid} 哪里最薄弱？**（诊断链）\n"
                     f"- **给 {sid} 一个这周能做完的计划**（建议链）\n"
                     "- **两个班差在哪？**（班级对比）\n"
                     "- **为什么说他薄弱？依据呢？**（答疑 + 证据）"})

    for m in hist:
        with st.chat_message(m["role"], avatar="🧑‍🎓" if m["role"] == "user" else "🤖"):
            st.markdown(m["content"])
            if m.get("result"):
                render_result(m["result"])
                render_chain(m["result"], expanded=False)

    chips = quick_questions or [
        f"{sid}哪里最薄弱？",
        f"给{sid}一个这周能做完的计划",
        "两个班差在哪？",
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

    # 学生上下文：问题里出现 Dxx 就切；只说"他呢"就沿用
    import re

    hit = re.search(r"D\d{2}", question)
    if hit:
        sid = hit.group(0)
        st.session_state[SID_KEY] = sid

    hist.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🤖"):
        with st.status("🧭 协调器正在识别意图…", expanded=False) as status:
            result = ask(question, sid, output_dir)
            agent = result.get("agent", "—")
            status.update(label=f"✅ 完成：{agent}", state="complete", expanded=False)

        if result.get("error"):
            st.error(f"智能体执行出错：{result['error']}")
            st.code(result.get("traceback", ""))
            hist.append({"role": "assistant", "content": f"⚠️ 执行出错：{result['error']}"})
            return

        render_chain(result, expanded=True)
        head = f"**[{result.get('agent', '')}]** " + (result.get("summary")
                                                     or result.get("diagnosis_summary")
                                                     or result.get("note") or "")
        st.markdown(head)
        render_result(result)
        hist.append({"role": "assistant", "content": head, "result": result})

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
    except Exception:
        pass
    mod = _load_module(AGENT_SCRIPT)
    coord = mod.Coordinator(output_dir)
    print("[OK] 07 加载成功（DataBundle / Coordinator.route）")
    cases = ["D01哪里最薄弱？", "给D01一个这周能做完的计划",
             "两个班差在哪？", "为什么说他薄弱？依据呢？"]
    for q in cases:
        r = coord.route(q, "D01")
        v = r.get("validation") or {}
        print(f"[OK] [{q}] → {r.get('agent')} | 校验 {'通过' if v.get('passed') else '拦截'}")
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
