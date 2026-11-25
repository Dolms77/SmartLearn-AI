# -*- coding: utf-8 -*-
"""首页、身份选择和按角色显示的导航。"""
from __future__ import annotations

from html import escape

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
    "对话": ("chat_agent.png", "多智能体对话"),
    "我的学情": ("lightbulb.png", "我的学情"),
    "学习建议": ("target.png", "学习建议"),
    "知识与成果": ("compass.png", "知识与成果"),
    "班级概览": ("chart_line.png", "班级概览"),
    "讲评建议": ("target.png", "讲评建议"),
}

# 控件 key 用 ASCII slug：Streamlit 的 st-key-* 类名对非 ASCII 不保证，CSS 会匹配不到
NAV_KEYS = {
    "对话": "chat", "我的学情": "diagnosis", "学习建议": "advice",
    "知识与成果": "knowledge", "班级概览": "class", "讲评建议": "lecture",
}


STUDENT_PAGES = ["对话", "我的学情", "学习建议", "知识与成果"]
TEACHER_PAGES = ["对话", "班级概览", "讲评建议", "知识与成果"]


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------
def _ss(key, default=None):
    return st.session_state.setdefault(key, default)


def reset() -> None:
    for k in ("stage", "role", "ident", "page", "nav_page", "teacher_class"):
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
        if st.button(f"{theme.icon_md('data_stack.png', '上传学情数据')} 上传学情数据", width="stretch", key="open_upload"):
            st.session_state["show_upload"] = True
            st.rerun()


def pick_role() -> None:
    theme.hero(sub="请选择身份")
    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        theme.role_card("student.png", "我是学生",
                        "查看个人学情、错因和练习建议。")
        if st.button("以学生身份进入", type="primary", width="stretch", key="as_student"):
            st.session_state.update({"role": "student", "stage": "identity"})
            st.rerun()
    with c2:
        theme.role_card("teacher.png", "我是教师",
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
        class_view = A.class_view(bundle)
        if class_view["classes"]:
            cls = st.selectbox("选择班级", class_view["classes"])
            row = class_view["class_theme"][cls]
            c1, c2, c3 = st.columns(3)
            c1.metric("学生数", row.get("students", 0))
            c2.metric("班级得分率", f"{row['overall']:.0%}" if row["overall"] is not None else "—")
            c3.metric("可判定覆盖", f"{I.class_mastery_summary(bundle).get(cls, {}).get('decided_rate', 0):.0%}")
            st.caption("覆盖率是已有至少 3 条有效作答的学生与指标组合所占比例。")
            if st.button(f"进入 {cls} 的班级视图", type="primary", width="stretch", key="enter_teacher"):
                st.session_state.update({"role": "teacher", "ident": cls, "stage": "app", "page": "对话"})
                st.rerun()
        else:
            st.info("当前数据中没有班级。")

    st.write("")
    if st.button("← 返回身份选择", key="back_identity"):
        st.session_state["stage"] = "role"
        st.rerun()


# --------------------------------------------------------------------------
# 登录后的页面
# --------------------------------------------------------------------------

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


def _select_page(page: str) -> None:
    st.session_state["nav_page"] = page


def _nav(pages: list[str], role: str) -> str:
    """Use one native button per page and a stable route key."""
    active = st.session_state["nav_page"]
    for page in pages:
        icon, label = NAV_LABELS[page]
        if page == "知识与成果":
            icon = "trophy.png" if role == "student" else "book.png"
        st.button(
            f"{theme.icon_md(icon, label)} {label}", key=f"nav_{NAV_KEYS[page]}",
            type="primary" if page == active else "secondary", width="stretch",
            on_click=_select_page, args=(page,),
        )
    return active


def _teacher_class_selector(bundle: dict, ident: str) -> str | None:
    classes = A.list_classes(bundle)
    if not classes:
        theme.brand(sub="教师视角")
        return None

    if st.session_state.get("teacher_class") not in classes:
        st.session_state["teacher_class"] = ident if ident in classes else classes[0]
    brand, picker = st.columns([1.25, 1], gap=None, vertical_alignment="center")
    with brand:
        theme.brand(sub="教师视角", compact=True)
    cls = picker.selectbox("选择班级", classes, key="teacher_class", label_visibility="collapsed")
    st.session_state["ident"] = cls
    return cls


def render_app(bundle: dict, role: str, ident: str, key: str | None, cache_dir: str) -> None:
    pages = STUDENT_PAGES if role == "student" else TEACHER_PAGES
    if st.session_state.get("nav_page") not in pages:
        st.session_state["nav_page"] = pages[0]

    with st.sidebar:
        if role == "teacher":
            ident = _teacher_class_selector(bundle, ident)
        else:
            theme.brand(sub=f"学生视角 · {ident}")
        page = _nav(pages, role)
        st.session_state["page"] = page
        st.divider()
        st.caption("学情数据")
        st.success(f"已加载 {len(bundle['records'])} 条记录", icon="✅")
        if st.button(f"{theme.icon_md('switch_role.png', '切换身份')} 切换身份", width="stretch", key="switch_role"):
            reset()
            st.rerun()

    if ident is None:
        st.info("当前数据中没有班级。")
        return

    # 顶部状态条
    if page not in {"我的学情", "班级概览"}:
        sub = (f"{ident} · {A.student_class(bundle, ident)}" if role == "student" else f"{ident} 班级视角")
        st.markdown(
            f"""<div class="sa-brand" style="border-bottom:1px solid #eaeff7;padding-bottom:10px;margin-bottom:14px">
                  {theme.avatar_svg(38)}
                  <div><div class="sa-brand-t">{page}</div>
                       <div class="sa-brand-s">{escape(sub)}</div></div>
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
    elif page == "讲评建议":
        home.render_teacher_advice(bundle, ident)
