# -*- coding: utf-8 -*-
r"""智慧学伴 · 智能体入口

流程：唤醒智能体 → 选身份（学生/教师）→ 选对象（个人/班级）→ 对话优先的主界面
运行：
    cd ui
    ..\.venv-ui\Scripts\python.exe -m streamlit run app.py
"""
from __future__ import annotations

import os
import sys

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import adapter as A     # noqa: E402
import llm               # noqa: E402
import shell             # noqa: E402
import theme             # noqa: E402

DEFAULT_OUTPUT = os.path.abspath(os.path.join(HERE, "..", "output"))
DEFAULT_RAW = os.path.abspath(os.path.join(
    HERE, "..", "赛题材料", "赛题数据", "赛题资料包", "4_赛题数据", "模拟学情数据"))

st.set_page_config(page_title="智慧学伴 · 学情诊断智能体", page_icon="🤖", layout="wide")
theme.inject()
st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1180px;}
  div[data-testid="stMetricValue"] {font-size: 1.35rem;}
  section[data-testid="stSidebar"] {min-width: 268px;}
  div[data-testid="stChatMessage"] {border-radius: 14px;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="智能体正在读取学情数据…")
def cached_bundle(output_dir: str) -> dict:
    return A.load_bundle(output_dir)


if not os.path.isdir(DEFAULT_OUTPUT):
    st.error(f"产物目录不存在：{DEFAULT_OUTPUT}\n请先运行 01–03 脚本。")
    st.stop()

bundle = cached_bundle(DEFAULT_OUTPUT)
if not bundle.get("records"):
    st.error("cleaned_data.json 缺失或为空，请先运行 01_data_loader.py。")
    st.stop()

key = llm.resolve_key(st.session_state.get("api_key_input") or None)
st.session_state["_key"] = key
st.session_state["_cache"] = os.path.join(DEFAULT_OUTPUT, "llm_cache")
st.session_state["_raw"] = DEFAULT_RAW

# --------------------------------------------------------------------------
# 路由：未登录走唤醒流程，已登录进主界面
# --------------------------------------------------------------------------
ident = shell.current()
if ident:
    role, who = ident
    shell.render_app(bundle, role, who, key, st.session_state["_cache"])
else:
    stage = st.session_state.get("stage", "landing")
    if stage == "role":
        shell.pick_role()
    elif stage == "identity":
        shell.pick_identity(bundle)
    else:
        shell.landing()

# --------------------------------------------------------------------------
# 侧栏页脚：接入设置（放在最后，保证出现在导航下方）
# --------------------------------------------------------------------------
with st.sidebar:
    st.divider()
    with st.expander("⚙ 接入与数据", expanded=False):
        st.text_input("DeepSeek API Key（可选）", type="password", key="api_key_input",
                      help="留空则自动读环境变量 / api.txt；不填也能用，对话走离线模板")
        stt = llm.status(key)
        st.caption(("✅ 已就绪：" + stt["key"]) if stt["online"] else f"⚠️ 离线：{stt['reason']}")
        st.caption(f"产物目录：`{DEFAULT_OUTPUT}`")
        st.caption("数据仅用于本赛题演示；不写入、不上传任何学生个人信息。")
