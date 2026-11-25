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
import dataset as DS     # noqa: E402
import design            # noqa: E402
import llm               # noqa: E402
import shell             # noqa: E402
import theme             # noqa: E402

DEFAULT_OUTPUT = os.path.abspath(os.path.join(HERE, "..", "output"))
BUNDLE_FILES = (
    "cleaned_data.json",
    "error_diagnosis.json",
    "error_diagnosis_llm.json",
    "statistics.json",
    "student_profiles.json",
    "mastery_matrix.json",
    "error_pattern_summary.json",
    "data_quality_report.json",
    "knowledge_base.json",
    "task1_knowledge_structure.json",
    "task3_recommendations.json",
)

st.set_page_config(page_title="智慧学伴 · 学情诊断智能体", page_icon=(theme.icon_path() or "🤖"), layout="wide")
theme.inject()
design.inject_tokens()
st.markdown("""
<style>
  .block-container {
    padding-top: 1.6rem; padding-bottom: 4rem;
    max-width: 1180px; width: 100% !important;
    margin-left: auto !important; margin-right: auto !important;
  }
  div[data-testid="stMetricValue"] {font-size: 1.35rem;}
  section[data-testid="stSidebar"] {min-width: 268px;}
  section[data-testid="stSidebar"][data-collapsed="true"] {
    display: none !important;
    width: 0 !important;
    min-width: 0 !important;
    max-width: 0 !important;
    flex-basis: 0 !important;
    overflow: hidden !important;
    border: 0 !important;
  }
  div[data-testid="stChatMessage"] {border-radius: 14px;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="正在读取学情数据…")
def cached_bundle(output_dir: str, file_signature: tuple) -> dict:
    del file_signature
    return A.load_bundle(output_dir)


# --------------------------------------------------------------------------
# 第一步：选数据集（欢迎页右侧「上传学情数据」按钮展开），完成后写 session_state["output_dir"]
# --------------------------------------------------------------------------
OUTPUT_DIR = st.session_state.get("output_dir") or DEFAULT_OUTPUT


def output_signature(output_dir: str) -> tuple:
    signature = []
    for name in BUNDLE_FILES:
        path = os.path.join(output_dir, name)
        try:
            file_stat = os.stat(path)
        except FileNotFoundError:
            signature.append((name, None, None))
        else:
            signature.append((name, file_stat.st_mtime_ns, file_stat.st_size))
    return tuple(signature)


if not os.path.isdir(OUTPUT_DIR):
    st.error(f"产物目录不存在：{OUTPUT_DIR}\n请先运行 01–03 脚本。")
    st.stop()

bundle = cached_bundle(OUTPUT_DIR, output_signature(OUTPUT_DIR))
if not bundle.get("records"):
    st.error("cleaned_data.json 缺失或为空，请先运行 01_data_loader.py。")
    st.stop()

# --------------------------------------------------------------------------
# 模型后端：由侧栏底部的 radio 写入 session_state，这里提前读取，本 run 立即生效
# （不在顶部渲染任何侧栏控件，避免条件控件移位触发前端 removeChild 报错）
# --------------------------------------------------------------------------
_default_api = llm.PROVIDER == "api"
# 首屏默认索引（环境决定），之后由 session_state 接管，避免动态 index 造成控件状态混乱
_default_idx = 1 if _default_api else 0
provider_choice = st.session_state.get(
    "provider_choice", "云端 API" if _default_api else "本地模型")
use_api = provider_choice == "云端 API"

# 让底层通道与用户选择一致（覆盖模块级 PROVIDER，影响 llm.status() / llm._chat() 的分流）
llm.PROVIDER = "api" if use_api else "ollama"


@st.cache_data(ttl=20, show_spinner=False)
def _llm_status_cached(provider: str):
    del provider  # 仅作缓存键：切换后端时立即失效重查
    return llm.status()


stt = _llm_status_cached(llm.PROVIDER)

if use_api:
    api_key_val = str(st.session_state.get("api_key_input", "") or "")
    key = llm.resolve_key(api_key_val or None)
    # 只做格式校验（sk- 前缀 + 长度），杜绝“随便输数字也算成功”；真实校验走侧栏「验证 Key」按钮
    online = llm.key_format_ok(key)
    llm_flag = key if online else None
else:
    key = None
    online = bool(stt["online"])
    # 本地模式传真值哨兵即可（_chat 在 PROVIDER=="ollama" 时忽略 key）
    llm_flag = "local" if online else None

st.session_state["_key"] = llm_flag
st.session_state["_cache"] = os.path.join(OUTPUT_DIR, "llm_cache")

# --------------------------------------------------------------------------
# 路由：未登录走唤醒流程，已登录进主界面
# --------------------------------------------------------------------------
ident = shell.current()
if ident:
    role, who = ident
    shell.render_app(bundle, role, who, llm_flag, st.session_state["_cache"])
else:
    stage = st.session_state.get("stage", "landing")
    if stage == "role":
        shell.pick_role()
    elif stage == "identity":
        shell.pick_identity(bundle)
    else:
        shell.landing()
        if st.session_state.get("show_upload"):
            DS.render_upload_panel()

# --------------------------------------------------------------------------
# 侧栏页脚：模型与数据（放在最后，保证出现在导航下方）
# --------------------------------------------------------------------------
with st.sidebar:
    st.divider()
    # 模型后端开关（写 session_state["provider_choice"]；顶部据此决定通道）
    # 用 selectbox 而非 radio：避免生成第二个 radiogroup，与 _nav 的 div[role="radiogroup"] CSS 冲突
    st.selectbox(
        "模型后端", ["本地模型", "云端 API"],
        index=_default_idx, key="provider_choice",
        help="会话内即时切换；选「云端 API」后填入 Key")
    if use_api:
        st.text_input(
            "DeepSeek API Key", type="password", key="api_key_input",
            help="输入后即时生效（先做格式校验）；点「验证 Key」做真实校验")
        if not online:
            if key:
                st.warning("Key 格式不正确（应以 sk- 开头），云端不可用。", icon="⚠️")
            else:
                st.warning("尚未配置 API Key，云端不可用，已回退离线回答。", icon="⚠️")
        if st.button("🔑 验证 Key", width="stretch", key="verify_key_btn"):
            with st.spinner("正在校验 DeepSeek Key…"):
                ok, msg = llm.verify_key(key or "")
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")

    # 状态显示
    if use_api:
        st.caption(("🟢 云端模型已就绪：" if online else "🟠 云端模型未就绪：") + stt["label"])
    else:
        st.caption(("🟢 本地模型已就绪：" if online else "🟠 模型未就绪：") + stt["label"])
    with st.expander("⚙ 模型与数据", expanded=False):
        if use_api:
            if online:
                st.success(f"{stt['label']} 已就绪", icon="✅")
            else:
                st.warning("未配置有效 API Key，云端不可用", icon="⚠️")
        elif online:
            st.success(f"{stt['label']} 已就绪", icon="✅")
            st.caption("推理全程在本机完成，不联网、不上传。")
            if stt.get("models"):
                st.caption("本机模型：" + "、".join(stt["models"]))
        else:
            st.warning(stt["reason"] or "模型不可用", icon="⚠️")
            st.code("ollama pull deepseek-r1:8b", language="powershell")
            st.caption("拉取后无需重启界面，点右上角 Rerun 即可。")
    if st.button("🔄 上传 / 切换学情数据", width="stretch", key="switch_dataset"):
        st.session_state.pop("ident", None)
        st.session_state["stage"] = "landing"
        st.session_state["show_upload"] = True
        st.rerun()
    st.caption(f"产物目录：`{OUTPUT_DIR}`")
    st.caption("数据仅用于本赛题演示；不写入、不上传任何学生个人信息。")
