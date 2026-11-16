# -*- coding: utf-8 -*-
"""智慧学伴 · 学情诊断与个性化学习 —— Streamlit 入口

运行：
    cd ui
    streamlit run app.py
或（Windows 指定解释器）：
    ..\\.venv-ui\\Scripts\\python.exe -m streamlit run app.py
"""
from __future__ import annotations

import os
import sys

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import adapter as A          # noqa: E402
import llm                    # noqa: E402
import views                  # noqa: E402

DEFAULT_OUTPUT = os.path.abspath(os.path.join(HERE, "..", "output"))
DEFAULT_RAW = os.path.abspath(os.path.join(
    HERE, "..", "赛题材料", "赛题数据", "赛题资料包", "4_赛题数据", "模拟学情数据"))

st.set_page_config(page_title="智慧学伴 · 学情诊断", page_icon="🎓", layout="wide")

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px;}
  div[data-testid="stMetricValue"] {font-size: 1.45rem;}
  div[data-testid="stMetricLabel"] {font-size: .82rem; opacity: .75;}
  section[data-testid="stSidebar"] {min-width: 300px;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="正在载入数据…")
def cached_bundle(output_dir: str) -> dict:
    return A.load_bundle(output_dir)


# --------------------------------------------------------------------------
# 侧栏
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🎓 智慧学伴")
    st.caption("学情诊断与个性化学习智能体")

    page = st.radio("功能", ["学生诊断", "班级概览", "任务1 知识结构", "数据质量", "成果文件"], index=0)

    st.divider()
    output_dir = st.text_input("产物目录", DEFAULT_OUTPUT, help="01–03 脚本的输出目录")
    raw_dir = st.text_input("原始数据目录", DEFAULT_RAW, help="用于数据质量独立复核")
    api_key_input = st.text_input("DeepSeek API Key（可选）", type="password",
                                  help="留空则自动读取环境变量 / api.txt；不填也能用界面")

    key = llm.resolve_key(api_key_input or None)
    stt = llm.status(key)
    if stt["online"]:
        st.success(f"DeepSeek：已就绪（{stt['key']}）", icon="✅")
    else:
        st.warning(f"DeepSeek：离线（{stt['reason']}）", icon="⚠️")
    st.caption("离线时所有结论仍可用：统计来自规则引擎，问答走模板。")

    st.divider()
    st.caption("数据仅用于本赛题演示；不写入、不上传任何学生个人信息。")

# --------------------------------------------------------------------------
# 载入
# --------------------------------------------------------------------------
if not os.path.isdir(output_dir):
    st.error(f"产物目录不存在：{output_dir}\n请先运行 01–03 脚本，或在侧栏修改路径。")
    st.stop()

bundle = cached_bundle(output_dir)
if not bundle.get("records"):
    st.error("cleaned_data.json 缺失或为空，请先运行 01_data_loader.py。")
    st.stop()

cache_dir = os.path.join(output_dir, "llm_cache")

# --------------------------------------------------------------------------
# 路由
# --------------------------------------------------------------------------
TITLES = {"学生诊断": "学情诊断", "班级概览": "班级与群体分析",
          "任务1 知识结构": "学习内容与要求梳理", "数据质量": "数据质量与清洗复核",
          "成果文件": "成果文件与外部产物"}
st.title(TITLES[page])

if page == "学生诊断":
    students = A.list_students(bundle)
    if not students:
        st.error("没有可用学生。")
        st.stop()
    default_idx = students.index("D01") if "D01" in students else 0
    sid = st.selectbox("选择学生", students, index=default_idx,
                       format_func=lambda s: f"{s} · {A.student_class(bundle, s)}")
    views.render_diagnosis(bundle, sid, key, cache_dir)

elif page == "班级概览":
    views.render_class(bundle, None)

elif page == "任务1 知识结构":
    views.render_knowledge(bundle)

elif page == "数据质量":
    views.render_quality(bundle, raw_dir)

else:
    views.render_artifacts(bundle)

st.divider()
st.caption(
    f"数据：{len(bundle['records'])} 条有效作答 / {len(A.list_students(bundle))} 名学生 / "
    f"生成时间 {(bundle.get('meta') or {}).get('generated_at', '—')}　|　"
    "口径：仅当指标证据 ≥3 条时才输出掌握度结论；其余标记「证据不足」。")
