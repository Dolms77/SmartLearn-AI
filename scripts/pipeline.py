# -*- coding: utf-8 -*-
"""可被界面调用的分析流水线。

与 `run_all.ps1` 的区别：
  * 纯 Python，便于从 Streamlit 里以子进程方式启动（不依赖 PowerShell）；
  * 每一步都可以单独开关；缺少依赖的步骤在启动前就会被标记为不可用；
  * 每一步的状态、耗时、日志尾部写入 run.json，界面据此显示进度；
  * 支持取消（界面写 cancel 标记文件，本脚本在步骤之间检查）。

用法：
    python scripts/pipeline.py --data <输入目录> --out <输出目录> \
        --run <run.json> --logs <日志目录> --steps 01,02,03,06,08,09

退出码：0 成功；1 有步骤失败；2 参数/环境错误；3 已取消。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCRIPTS = os.path.join(ROOT, "已完成脚本")

# 步骤登记表：est 为“800 条样本数据”上的实测耗时（秒），用于给用户估时
STEPS = [
    {"id": "01", "name": "数据清洗与统计", "file": "01_data_loader.py", "args": [],
     "deps": [], "est": 2, "required": True,
     "produces": ["cleaned_data.json", "statistics.json", "data_quality_report.json"]},
    {"id": "02", "name": "BKT 掌握度建模", "file": "02_bkt_model.py", "args": [],
     "deps": [], "est": 2, "required": True,
     "produces": ["mastery_matrix.json", "student_profiles.json"]},
    {"id": "03", "name": "错因诊断（规则引擎）", "file": "03_error_diagnosis.py", "args": [],
     "deps": [], "est": 3, "required": True,
     "produces": ["error_diagnosis.json", "error_pattern_summary.json"]},
    {"id": "04", "name": "RAG 知识库（可选）", "file": "04_rag_knowledge.py", "args": [],
     "deps": ["langchain", "langchain_community", "chromadb", "sentence_transformers"],
     "est": 300, "required": False, "produces": ["knowledge_base.json"]},
    {"id": "05", "name": "交互式知识图谱（可选）", "file": "05_knowledge_graph.py", "args": [],
     "deps": ["networkx", "pyvis"], "est": 3, "required": False,
     "produces": ["knowledge_graph.html"]},
    {"id": "06", "name": "学情仪表盘（可选）", "file": "06_dashboard.py", "args": [],
     "deps": [], "est": 3, "required": False, "produces": ["dashboard.html"]},
    {"id": "07", "name": "多智能体引擎自检（无产物）", "file": "07_multi_agent.py", "args": ["--demo"],
     "deps": [], "est": 3, "required": False, "produces": []},
    {"id": "08", "name": "任务3 个性化建议", "file": "08_task3_generator.py", "args": ["--all-students"],
     "deps": [], "est": 4, "required": True, "produces": ["task3_recommendations.json"]},
    {"id": "09", "name": "任务1 知识结构", "file": "09_task1_knowledge_structure.py", "args": [],
     "deps": [], "est": 3, "required": True, "produces": ["task1_knowledge_structure.json"]},
]
STEP_BY_ID = {s["id"]: s for s in STEPS}
# 界面能正常展示所需的产物（缺了页面会缺块，但不至于白屏）
UI_REQUIRED = ["cleaned_data.json", "statistics.json", "mastery_matrix.json",
               "student_profiles.json", "error_diagnosis.json",
               "task3_recommendations.json", "task1_knowledge_structure.json"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def deps_status() -> dict[str, dict]:
    """每个步骤的可用性：{'01': {'ok': True, 'reason': ''}, ...}"""
    out = {}
    for s in STEPS:
        missing = [d for d in s["deps"] if importlib.util.find_spec(d) is None]
        out[s["id"]] = {
            "ok": not missing,
            "missing": missing,
            "reason": ("缺少依赖：" + "、".join(missing)) if missing else "",
        }
    return out


def load_status(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_status(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def estimate_seconds(step_ids: list[str]) -> int:
    return sum(STEP_BY_ID[i]["est"] for i in step_ids if i in STEP_BY_ID)


def check_artifacts(out_dir: str, step_ids: list[str]) -> tuple[bool, list[str]]:
    """返回 (界面可用, 缺失的界面必需文件)。"""
    missing = [n for n in UI_REQUIRED if not os.path.exists(os.path.join(out_dir, n))]
    return (not missing), missing


def run(data_dir: str, out_dir: str, run_path: str, log_dir: str,
        step_ids: list[str], cancel_path: str | None = None) -> int:
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    chosen = [s for s in STEPS if s["id"] in step_ids]
    if not chosen:
        print("没有选择任何步骤", file=sys.stderr)
        return 2

    status = {
        "status": "running",
        "started_at": _now(),
        "finished_at": "",
        "data_dir": data_dir,
        "out_dir": out_dir,
        "steps": [{"id": s["id"], "name": s["name"], "status": "pending",
                   "seconds": None, "log": os.path.join(log_dir, s["id"] + ".log")}
                  for s in chosen],
        "current": "",
        "message": "",
        "ui_ready": False,
        "missing": [],
    }
    _write_status(run_path, status)

    env = dict(os.environ)
    env["SS_DATA"] = data_dir
    env["SS_OUT"] = out_dir
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONUTF8", "1")

    for idx, step in enumerate(chosen):
        if cancel_path and os.path.exists(cancel_path):
            status.update(status="cancelled", finished_at=_now(),
                          current="", message="已取消")
            _write_status(run_path, status)
            return 3

        status["current"] = step["id"]
        status["steps"][idx].update(status="running", started_at=_now())
        _write_status(run_path, status)

        log_path = status["steps"][idx]["log"]
        started = time.time()
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"[{_now()}] {step['id']} {step['name']}\n")
            log.flush()
            try:
                proc = subprocess.run(
                    [sys.executable, os.path.join(SCRIPTS, step["file"]), *step["args"]],
                    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                    timeout=3600,
                )
                code = proc.returncode
            except subprocess.TimeoutExpired:
                code = 124
                log.write("\n[超时] 步骤超过 3600 秒被终止\n")
            except Exception as exc:  # noqa: BLE001
                code = 1
                log.write(f"\n[启动失败] {type(exc).__name__}: {exc}\n")

        seconds = round(time.time() - started, 2)
        ok = code == 0
        status["steps"][idx].update(
            status="done" if ok else "failed", seconds=seconds, exit_code=code)
        _write_status(run_path, status)
        if not ok:
            status.update(status="failed", finished_at=_now(), current="",
                          message=f"{step['id']} {step['name']} 失败（退出码 {code}）")
            _write_status(run_path, status)
            return 1

    ui_ready, missing = check_artifacts(out_dir, step_ids)
    status.update(status="done", finished_at=_now(), current="",
                  message="分析完成" if ui_ready else "分析完成，但界面所需文件不全",
                  ui_ready=ui_ready, missing=missing)
    _write_status(run_path, status)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SmartLearn 分析流水线")
    ap.add_argument("--data", help="输入目录（含 5 个 CSV）")
    ap.add_argument("--out", help="输出目录")
    ap.add_argument("--run", help="run.json 状态文件路径")
    ap.add_argument("--logs", help="日志目录")
    ap.add_argument("--steps", default="01,02,03,06,08,09",
                    help="逗号分隔的步骤编号，如 01,02,03,08,09")
    ap.add_argument("--cancel", default="", help="取消标记文件路径")
    ap.add_argument("--check", action="store_true", help="只打印环境检查结果")
    args = ap.parse_args(argv)

    if args.check:
        print(json.dumps(deps_status(), ensure_ascii=False, indent=2))
        return 0

    missing_args = [n for n in ("data", "out", "run", "logs") if not getattr(args, n)]
    if missing_args:
        print(f"缺少参数: {missing_args}", file=sys.stderr)
        return 2

    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    bad = [s for s in steps if s not in STEP_BY_ID]
    if bad:
        print(f"未知步骤: {bad}", file=sys.stderr)
        return 2
    return run(args.data, args.out, args.run, args.logs, steps, args.cancel or None)


if __name__ == "__main__":
    raise SystemExit(main())
