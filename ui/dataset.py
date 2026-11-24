# -*- coding: utf-8 -*-
"""初始界面：选择数据集（已有结果 / 上传新数据 / 示例数据）并启动分析。

设计要点：
  * 分析在**独立子进程**里跑（scripts/pipeline.py），刷新页面不会中断；
  * 每一步都可以勾选，缺依赖的步骤置灰并给出安装提示；
  * run.json 记录每步状态，界面每秒轮询一次；
  * 完成后把 output_dir 写进 session，主界面直接读这个目录。
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime

import streamlit as st

import design
import theme

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
PIPELINE = os.path.join(ROOT, "scripts", "pipeline.py")
SAMPLE_OUTPUT = os.path.join(ROOT, "output")

# 固定模板：文件名 → (必需列, 可选列)
TEMPLATE = {
    "课程要求.csv": (
        ["主题编号", "主题", "主题目标", "指标编号", "观察指标"],
        ["课标整理编号", "课标文件页／正文页", "教材正文页"],
    ),
    "题目与材料.csv": (
        ["材料编号", "主题编号", "题型", "题干或内容", "满分", "指标编号"],
        ["材料类型", "选项", "参考答案", "参考解析", "评分点", "来源或资料文件"],
    ),
    "模拟学生.csv": (
        ["学生编号", "模拟班级编号"],
        ["年级"],
    ),
    "测验节点.csv": (
        ["节点编号", "模拟测验日期", "可用题目编号"],
        ["已教及测量主题", "说明"],
    ),
    "作答记录.csv": (
        ["记录编号", "学生编号", "材料编号", "主题编号", "节点编号",
         "评分状态", "得分", "满分", "学生最终作答"],
        ["作答事件编号", "修订版本", "模拟提交时间", "解答过程", "评分点得分"],
    ),
}


# ---------------------------------------------------------------------------
# 目录与状态
# ---------------------------------------------------------------------------
def runs_root() -> str:
    """运行目录：优先 SA_RUNS_DIR，其次项目 runs/，再退到用户目录/临时目录。"""
    import tempfile
    candidates = [
        os.environ.get("SA_RUNS_DIR"),
        os.path.join(ROOT, "runs"),
        os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                     "SmartLearn", "runs"),
        os.path.join(tempfile.gettempdir(), "smartlearn_runs"),
    ]
    for cand in candidates:
        if not cand:
            continue
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, "._probe")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return cand
        except OSError:
            continue
    raise RuntimeError("找不到可写的数据目录，请设置环境变量 SA_RUNS_DIR")


def load_pipeline():
    """把 scripts/pipeline.py 当模块导入（只读它的登记表和环境检查）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sa_pipeline", PIPELINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def latest_runs(limit: int = 5) -> list[dict]:
    root = runs_root()
    rows = []
    for name in os.listdir(root):
        run_json = os.path.join(root, name, "run.json")
        if not os.path.isfile(run_json):
            continue
        try:
            with open(run_json, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({"run_id": name, "dir": os.path.join(root, name),
                     "out_dir": os.path.join(root, name, "output"), **data})
    rows.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return rows[:limit]


def new_run_dir() -> tuple[str, str]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(runs_root(), run_id)
    for sub in ("input", "output", "logs"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    return run_id, base


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def _read_header(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    return [c.strip() for c in line.rstrip("\n").split(",")]


def validate_input(folder: str) -> tuple[bool, list[str], list[str]]:
    """返回 (通过, 错误, 警告)。"""
    errors: list[str] = []
    warns: list[str] = []
    for name, (need, optional) in TEMPLATE.items():
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            errors.append(f"缺少文件：{name}")
            continue
        header = _read_header(path)
        missing = [c for c in need if c not in header]
        if missing:
            errors.append(f"{name} 缺少必需列：{'、'.join(missing)}")
        missing_opt = [c for c in optional if c not in header]
        if missing_opt:
            warns.append(f"{name} 缺少可选列：{'、'.join(missing_opt)}（不影响运行）")

    rec = os.path.join(folder, "作答记录.csv")
    if os.path.isfile(rec):
        try:
            with open(rec, "r", encoding="utf-8-sig", errors="replace") as f:
                n = max(0, sum(1 for _ in f) - 1)
            if n == 0:
                errors.append("作答记录.csv 只有表头，没有数据行")
            elif n < 10:
                warns.append(f"作答记录.csv 只有 {n} 行，样本过少，诊断结论会大量显示“证据不足”")
        except OSError:
            errors.append("作答记录.csv 读取失败")
    return (not errors), errors, warns


def template_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, (need, optional) in TEMPLATE.items():
            header = ",".join(need + optional)
            z.writestr(name, "\ufeff" + header + "\n")
        z.writestr("说明.txt",
                   "把 5 个 CSV 按此表头填好，打包成 zip 上传；\n"
                   "列顺序不限，列名需一致（utf-8 编码）。\n"
                   "示例：赛题材料/赛题数据/.../模拟学情数据/\n")
    return buf.getvalue()


def unpack_upload(files, target: str) -> list[str]:
    """把上传的文件写进 target；zip 会解包（只取 5 个模板文件，防目录穿越）。"""
    saved = []
    for f in files or []:
        name = os.path.basename(f.name)
        data = f.getvalue()
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    base = os.path.basename(info.filename)
                    if base in TEMPLATE:
                        with z.open(info) as src, open(os.path.join(target, base), "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        saved.append(base)
        elif name in TEMPLATE:
            with open(os.path.join(target, name), "wb") as dst:
                dst.write(data)
            saved.append(name)
    return saved


# ---------------------------------------------------------------------------
# 启动 / 进度
# ---------------------------------------------------------------------------
def start_run(input_dir: str, steps: list[str]) -> dict:
    run_id, base = new_run_dir()
    status = os.path.join(base, "run.json")
    cmd = [sys.executable, PIPELINE,
           "--data", input_dir, "--out", os.path.join(base, "output"),
           "--run", status, "--logs", os.path.join(base, "logs"),
           "--steps", ",".join(steps),
           "--cancel", os.path.join(base, "cancel")]
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    return {"run_id": run_id, "dir": base, "status_file": status,
            "out_dir": os.path.join(base, "output")}


def read_status(status_file: str) -> dict:
    try:
        with open(status_file, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# 界面
# ---------------------------------------------------------------------------
def _enter(output_dir: str) -> None:
    st.session_state["output_dir"] = output_dir
    st.session_state["stage"] = "landing"
    st.session_state["show_upload"] = False
    st.session_state.pop("ds_run", None)
    st.rerun()


def render_upload_panel() -> None:
    """欢迎页右侧「提交学情数据」展开的面板（同页内联，不用弹窗）。"""
    st.divider()
    head1, head2 = st.columns([4, 1])
    head1.markdown("### 📤 提交学情数据")
    if head2.button("收起", key="ds_close", width="stretch"):
        st.session_state["show_upload"] = False
        st.rerun()
    st.caption("固定模板（5 个 CSV）：校验通过后勾选要跑的脚本；分析在后台进行，完成后自动切到新结果。")

    if st.session_state.get("ds_run"):
        render_progress()
        st.divider()

    runs = latest_runs()
    if runs:
        with st.expander("最近的分析记录", expanded=False):
            for r in runs:
                ok = r.get("status") == "done"
                cols = st.columns([4, 1])
                cols[0].caption(f"{r.get('started_at', '')} · {r.get('run_id', '')} · "
                                f"{'完成' if ok else r.get('status', '')}")
                if ok and os.path.isfile(os.path.join(r["out_dir"], "cleaned_data.json")):
                    if cols[1].button("使用", key=f"ds_use_{r['run_id']}", width="stretch"):
                        _enter(r["out_dir"])

    _render_upload(None)


def _render_upload(_container) -> None:
    # 两列等高：标题和控件都放在同一列里，左右按钮基线一致
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        st.markdown("**1. 下载模板**")
        st.download_button("下载 CSV 模板（zip）", template_zip(), file_name="学情数据模板.zip",
                           mime="application/zip", width="stretch", key="ds_tpl")
        st.caption("5 个 CSV 的表头模板，按列名填写即可。")
    with c2:
        st.markdown("**2. 上传数据**")
        up = st.file_uploader(
            "上传 5 个 CSV，或一个包含它们的 zip",
            type=["csv", "zip"], accept_multiple_files=True, key="ds_upload",
            label_visibility="collapsed")
        st.caption("支持 5 个 CSV 或一个 zip；校验通过后才能启动。")

    saved_dir = st.session_state.get("ds_saved_dir")
    if up:
        sig = tuple((f.name, getattr(f, "size", 0)) for f in up)
        if st.session_state.get("ds_upload_sig") != sig:
            run_id, base = new_run_dir()
            input_dir = os.path.join(base, "input")
            saved = unpack_upload(up, input_dir)
            st.session_state["ds_pending"] = {"run_id": run_id, "base": base,
                                              "input": input_dir, "saved": saved}
            st.session_state["ds_saved_dir"] = input_dir
            st.session_state["ds_upload_sig"] = sig
            st.caption(f"已保存 {len(saved)} 个文件：" + "、".join(saved) if saved else "未识别到模板中的 5 个 CSV")
        saved_dir = st.session_state.get("ds_saved_dir")

    if not saved_dir:
        st.info("支持逐列名匹配的固定模板；上传后会先校验再允许启动。", icon="ℹ️")
        return

    ok, errors, warns = validate_input(saved_dir)
    if errors:
        for e in errors:
            st.error(e, icon="❌")
    for w in warns:
        st.warning(w, icon="⚠️")
    if ok:
        st.success("文件与列名校验通过。", icon="✅")

    st.divider()
    _render_steps_and_start(saved_dir, ok)


def _render_steps_and_start(input_dir: str, validated: bool) -> None:
    pipe = load_pipeline()
    status = pipe.deps_status()
    st.markdown("**3. 选择要运行的脚本**")
    st.caption("缺少依赖的步骤不可勾选；必需步骤取消后，界面会缺少对应板块。")

    selected: list[str] = []
    all_ok = True
    for s in pipe.STEPS:
        info = status[s["id"]]
        default = s["id"] in ("01", "02", "03", "06", "08", "09")
        label = f"{s['id']} · {s['name']}"
        if not info["ok"]:
            st.checkbox(label, value=False, disabled=True, key=f"ds_step_{s['id']}",
                        help=info["reason"] + "（安装依赖后可开启）")
            st.caption(f"　　{info['reason']}")
            all_ok = False
            continue
        checked = st.checkbox(label, value=default, key=f"ds_step_{s['id']}",
                              help=f"预计 {s['est']} 秒" if s["est"] < 60 else f"预计约 {s['est'] // 60} 分钟")
        if checked:
            selected.append(s["id"])

    est = pipe.estimate_seconds(selected)
    required_missing = [i for i in ("01", "02", "03", "08", "09") if i not in selected]
    if required_missing:
        st.warning(f"未选择界面必需步骤：{', '.join(required_missing)}；进入后相关页面会缺数据。", icon="⚠️")
    if est >= 60:
        st.warning(f"预计耗时约 {est // 60} 分钟（主要来自 RAG 建库）。运行期间可以最小化窗口，"
                   "分析在后台继续；刷新页面不会中断。", icon="⏳")
    else:
        st.info(f"预计耗时约 {max(est, 1)} 秒。", icon="⚡")

    c1, c2 = st.columns([1, 2])
    can_start = validated and bool(selected)
    if c1.button("开始分析", type="primary", disabled=not can_start, width="stretch", key="ds_start"):
        pending = st.session_state.get("ds_pending") or {}
        if not pending.get("input"):
            st.error("请先上传数据。")
        else:
            info = start_run(pending["input"], selected)
            st.session_state["ds_run"] = info
            st.session_state.pop("ds_saved_dir", None)
            st.rerun()
    if not validated:
        c2.caption("校验未通过，修正后重新上传即可。")
    elif not selected:
        c2.caption("至少选择一个步骤。")


@st.fragment(run_every=1.0)
def render_progress() -> None:
    """轮询 run.json，展示进度；完成后允许进入。"""
    info = st.session_state.get("ds_run")
    if not info:
        return
    data = read_status(info["status_file"])
    state = data.get("status", "running")
    st.markdown({"running": "### ⏳ 正在分析…", "done": "### ✅ 分析完成",
                 "failed": "### ❌ 分析失败", "cancelled": "### ⏹ 已取消"}.get(state, "### 正在分析…"))
    steps = data.get("steps") or []
    total = len(steps) or 1
    done = sum(1 for s in steps if s["status"] == "done")
    st.progress(done / total, text=f"{done}/{total} 步完成")

    for s in steps:
        icon = {"done": "✅", "running": "⏳", "failed": "❌", "pending": "⬜"}.get(s["status"], "⬜")
        tail = f" · {s['seconds']}s" if s.get("seconds") is not None else ""
        st.markdown(f"{icon} **{s['id']} {s['name']}**{tail}")

    if state == "running":
        st.caption(f"开始时间 {data.get('started_at', '')} · 当前步骤 {data.get('current') or '—'}"
                   " · 分析在后台进程里运行，刷新页面不会中断")
        if st.button("取消分析", key="ds_cancel"):
            cancel = os.path.join(info["dir"], "cancel")
            with open(cancel, "w", encoding="utf-8") as f:
                f.write("cancel")
            st.info("已请求取消，将在当前步骤结束后停止。")
    elif state == "done":
        st.success("分析完成。", icon="✅")
        if not data.get("ui_ready", False):
            miss = "、".join(data.get("missing") or [])
            st.warning(f"界面必需文件不全（{miss}），进入后部分页面可能为空。", icon="⚠️")
        if st.button("进入智能体", type="primary", width="stretch", key="ds_enter_run"):
            _enter(info["out_dir"])
    elif state in ("failed", "cancelled"):
        st.error("分析失败：" + (data.get("message") or state), icon="❌")
        logs = os.path.join(info["dir"], "logs")
        for s in steps:
            log_path = os.path.join(logs, s["id"] + ".log")
            if os.path.isfile(log_path) and s["status"] in ("failed", "running"):
                with st.expander(f"{s['id']} 日志尾部", expanded=True):
                    with open(log_path, encoding="utf-8", errors="replace") as f:
                        st.code("".join(f.readlines()[-40:]), language="text")
        if st.button("重新开始", key="ds_restart"):
            st.session_state.pop("ds_run", None)
            st.rerun()
