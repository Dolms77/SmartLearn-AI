# -*- coding: utf-8 -*-
"""首页、身份选择和按角色显示的导航。"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from urllib.parse import quote

import adapter as A
import chat
import home
import insights as I
import theme
import views

NAV_LABELS = {
    "对话": ("💬", "与智能体对话"),
    "智能体": ("🤖", "多智能体"),
    "我的学情": ("📊", "我的学情"),
    "学习建议": ("🎯", "学习建议"),
    "知识与成果": ("🗺", "知识与成果"),
    "班级概览": ("📈", "班级概览"),
    "学生名单": ("👥", "学生名单"),
    "数据质量": ("🧹", "数据质量"),
}

# 控件 key 用 ASCII slug：Streamlit 的 st-key-* 类名对非 ASCII 不保证，CSS 会匹配不到
NAV_KEYS = {
    "对话": "chat", "智能体": "agent", "我的学情": "diagnosis",
    "学习建议": "advice", "知识与成果": "knowledge", "班级概览": "class",
    "学生名单": "students", "数据质量": "quality",
}


STUDENT_PAGES = ["对话", "智能体", "我的学情", "学习建议", "知识与成果"]
TEACHER_PAGES = ["对话", "智能体", "班级概览", "学生名单", "数据质量", "知识与成果"]


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------
def _ss(key, default=None):
    return st.session_state.setdefault(key, default)


def reset() -> None:
    for k in ("stage", "role", "ident", "page", "nav_page"):
        st.session_state.pop(k, None)
    st.session_state["stage"] = "role"


def current() -> tuple[str, str] | None:
    role = st.session_state.get("role")
    ident = st.session_state.get("ident")
    if st.session_state.get("stage") == "app" and role and ident:
        return role, ident
    return None


# --------------------------------------------------------------------------
# 首页与身份选择
# --------------------------------------------------------------------------
def landing() -> None:
    theme.hero()
    st.write("")
    c1, c2, c3 = st.columns([0.9, 1.1, 1])
    with c2:
        if st.button("选择身份", type="primary", width="stretch", key="wake"):
            st.session_state["stage"] = "role"
            st.rerun()
    with c3:
        if st.button("上传学情数据", width="stretch", key="open_upload"):
            st.session_state["show_upload"] = True
            st.rerun()


def pick_role() -> None:
    theme.hero(sub="请选择身份")
    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        theme.role_card("🧑‍🎓", "我是学生",
                        "查看个人学情、错因和练习建议。")
        if st.button("以学生身份进入", type="primary", width="stretch", key="as_student"):
            st.session_state.update({"role": "student", "stage": "identity"})
            st.rerun()
    with c2:
        theme.role_card("🧑‍🏫", "我是教师",
                        "查看班级得分、共性难点和学生作答。")
        if st.button("以教师身份进入", type="primary", width="stretch", key="as_teacher"):
            st.session_state.update({"role": "teacher", "stage": "identity"})
            st.rerun()

    st.write("")
    if st.button("← 返回", key="back_role"):
        st.session_state["stage"] = "landing"
        st.rerun()


def pick_identity(bundle: dict) -> None:
    role = st.session_state.get("role")
    students = A.list_students(bundle)
    if role == "student":
        theme.hero(sub="选择学生")
        st.write("")
        sid = st.selectbox(
            "学生编号", students, index=students.index("D01") if "D01" in students else 0,
            format_func=lambda s: f"{s} · {A.student_class(bundle, s)} · "
                                  f"{len(bundle['records_by_student'].get(s, []))} 条记录")
        v = A.student_view(bundle, sid)
        c1, c2, c3 = st.columns(3)
        c1.metric("有效作答", v["evidence_total"])
        c2.metric("可判定指标", f"{v['coverage']['decided']}/9")
        c3.metric("整体掌握度", f"{v['overall']:.0%}" if v["overall"] is not None else "—")
        st.caption("每项指标至少有 3 条有效作答才计算掌握度。")
        if st.button(f"进入 {sid} 的学情", type="primary", width="stretch", key="enter_student"):
            st.session_state.update({"role": "student", "ident": sid, "stage": "app", "page": "对话"})
            st.rerun()
    else:
        theme.hero(sub="选择班级")
        st.write("")
        classes = A.class_view(bundle)["classes"] or ["DC01"]
        cls = st.selectbox("选择班级", classes)
        row = A.class_view(bundle)["class_theme"].get(cls, {})
        c1, c2, c3 = st.columns(3)
        c1.metric("学生数", row.get("students", 0))
        c2.metric("班级得分率", f"{(row.get('overall') or 0):.0%}")
        c3.metric("可判定覆盖", f"{I.class_mastery_summary(bundle).get(cls, {}).get('decided_rate', 0):.0%}")
        st.caption("覆盖率是已有至少 3 条有效作答的学生与指标组合所占比例。")
        if st.button(f"进入 {cls} 的班级视图", type="primary", width="stretch", key="enter_teacher"):
            st.session_state.update({"role": "teacher", "ident": cls, "stage": "app", "page": "对话"})
            st.rerun()

    st.write("")
    if st.button("← 返回身份选择", key="back_identity"):
        st.session_state["stage"] = "role"
        st.rerun()


# --------------------------------------------------------------------------
# 登录后的页面
# --------------------------------------------------------------------------
def render_students_list(bundle: dict) -> None:
    st.subheader("学生名单与覆盖情况")
    rows = []
    for sid in A.list_students(bundle):
        v = A.student_view(bundle, sid)
        rows.append({
            "学生": sid, "班级": v["cls"], "有效记录": v["evidence_total"],
            "可判定指标": f"{v['coverage']['decided']}/9",
            "可判定掌握度": "—" if v["overall"] is None else f"{v['overall']:.0%}",
            "错因条数": len(v["errors"]),
            "状态": "证据不足" if v["coverage"]["decided"] == 0 else
                    ('需关注' if v['overall'] is not None and v['overall'] < 0.4 else '正常'),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)
    st.caption("选择学生可查看作答记录和学情。")
    sid = st.selectbox("查看学生学情", [r["学生"] for r in rows], key="teacher_drill")
    with st.expander(f"打开 {sid} 的完整学情", expanded=False):
        views.render_diagnosis(bundle, sid, st.session_state.get("_key"), st.session_state.get("_cache"))


def render_advice(bundle: dict, sid: str) -> None:
    v = A.student_view(bundle, sid)
    st.subheader(f"{sid} 的学习建议")
    rec = views._task3_for(bundle, sid)
    if rec:
        views._render_task3(rec, bundle.get("output_dir"))
        return

    st.info("正式学习建议尚未生成。先按证据给你可执行的第一步。")
    order = sorted(v["weak"] + v["developing"], key=lambda x: x["mastery"])
    if order:
        for i, x in enumerate(order, 1):
            qids = [q for q, m in bundle["question_map"].items() if m.get("indicator") == x["code"]]
            todo = [q for q in qids
                    if q not in {r["question_id"] for r in A.indicator_evidence(bundle, sid, x["code"])}]
            with st.container(border=True):
                st.markdown(f"**第 {i} 步 · {x['code']} {x['name']}**（掌握度 {x['mastery']:.0%}，证据 {x['n']} 条）")
                st.markdown(f"- 先看学习卡：`{x['theme']}` 对应方法要点")
                st.markdown(f"- 练没做过的：{'、'.join(todo[:3]) if todo else '该指标题已全部做过，建议做变式'}")
                st.markdown(f"- 过关标准：同指标再答对 2 题，且其中 1 道是解答题")
    else:
        st.success("没有达到薄弱门槛的指标。")

    if v["insufficient"]:
        st.markdown("##### 需要先补观察的指标（证据不足，暂不下结论）")
        rows = []
        for x in v["insufficient"]:
            qids = [q for q, m in bundle["question_map"].items() if m.get("indicator") == x["code"]]
            done = {r["question_id"] for r in A.indicator_evidence(bundle, sid, x["code"])}
            rows.append({"指标": x["code"], "观察指标": x["name"], "已有证据": x["n"],
                         "建议补测": "、".join([q for q in qids if q not in done][:3])})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _nav_text(p: str) -> str:
    """导航标签（纯文字，图标由 CSS 生成，保证同一列对齐）。"""
    return NAV_LABELS.get(p, ("", p))[1]


def _nav(pages: list[str]) -> str:
    """侧栏导航：用 Streamlit 原生 st.radio（点击最可靠）。

    对齐靠两件事：① 标签文本里不含 emoji（图标改由 CSS ::before 按序号生成，固定宽度）；
    ② 固定 key、不传 index（否则控件 ID 每轮变化，会出现"要点两次"）。
    """
    if st.session_state.get("nav_page") not in pages:
        st.session_state["nav_page"] = pages[0]

    icon_rules = "".join(
        f'[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type({i + 1})::before'
        f'{{content:"{NAV_LABELS.get(p, ("", p))[0]}";}}'
        for i, p in enumerate(pages))
    st.markdown(
        "<style>"
        # 隐藏原生圆点
        '[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child{display:none!important;}'
        '[data-testid="stSidebar"] div[role="radiogroup"]{gap:2px!important;}'
        '[data-testid="stSidebar"] div[role="radiogroup"] > label{'
        'display:flex!important;align-items:center;gap:10px;'
        'padding:9px 10px!important;border-radius:10px!important;'
        'transition:background .15s ease;}'
        '[data-testid="stSidebar"] div[role="radiogroup"] > label:hover{background:rgba(47,111,237,.07)!important;}'
        '[data-testid="stSidebar"] div[role="radiogroup"] > label > div:last-child{font-size:14px;color:#31415c;}'
        # 图标：固定 22px 宽，文字因此严格左对齐
        '[data-testid="stSidebar"] div[role="radiogroup"] > label::before{'
        'flex:0 0 22px;width:22px;text-align:center;font-size:15px;line-height:1;}'
        f"{icon_rules}"
        # 选中行
        '[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked){'
        'background:linear-gradient(135deg,#eaf1ff,#f4f0ff)!important;}'
        '[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) > div:last-child{'
        'color:#2F6FED!important;font-weight:600;}'
        "</style>", unsafe_allow_html=True)

    st.radio("导航", pages, key="nav_page", format_func=_nav_text,
             label_visibility="collapsed")
    return st.session_state["nav_page"]


def render_app(bundle: dict, role: str, ident: str, key: str | None, cache_dir: str) -> None:
    pages = STUDENT_PAGES if role == "student" else TEACHER_PAGES
    if st.session_state.get("nav_page") not in pages:
        st.session_state["nav_page"] = pages[0]

    with st.sidebar:
        theme.brand(sub=f"{'学生视角' if role == 'student' else '教师视角'} · {ident}")
        page = _nav(pages)
        st.session_state["page"] = page
        st.divider()
        st.caption("学情数据")
        st.success(f"已加载 {len(bundle['records'])} 条记录", icon="✅")
        if st.button("🔄 切换身份", width="stretch", key="switch_role"):
            reset()
            st.rerun()

    # 顶部状态条
    if page not in {"我的学情", "班级概览"}:
        sub = (f"{ident} · {A.student_class(bundle, ident)}" if role == "student" else f"{ident} 班级视角")
        st.markdown(
            f"""<div class="sa-brand" style="border-bottom:1px solid #eaeff7;padding-bottom:10px;margin-bottom:14px">
                  {theme.avatar_svg(38)}
                  <div><div class="sa-brand-t">{page}</div>
                       <div class="sa-brand-s">{sub}</div></div>
                </div>""",
            unsafe_allow_html=True)
    
    if page == "对话":
        chat.render(bundle, role, ident, key, cache_dir)
    elif page == "我的学情":
        home.render_student_home(bundle, ident, key, cache_dir)
    elif page == "学习建议":
        render_advice(bundle, ident)
    elif page == "知识与成果":
        views.render_knowledge_and_artifacts(bundle)
    elif page == "班级概览":
        home.render_teacher_home(bundle, ident)
    elif page == "学生名单":
        render_students_list(bundle)
    elif page == "数据质量":
        views.render_quality(bundle)
    elif page == "智能体":
        import agent_bridge as AB

        AB.render_agent_page(bundle.get("output_dir"))
