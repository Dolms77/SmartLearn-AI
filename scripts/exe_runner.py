# -*- coding: utf-8 -*-
"""Single-file Windows launcher for the SmartLearn data pipeline."""
from __future__ import annotations

import argparse
import os
import runpy
import shutil
import sys
from datetime import datetime
from pathlib import Path

import networkx as _networkx
from pyvis.network import Network as _PyvisNetwork


DATA_FILES = (
    "课程要求.csv",
    "题目与材料.csv",
    "模拟学生.csv",
    "测验节点.csv",
    "作答记录.csv",
)
PIPELINE = (
    ("01_data_loader.py", ()),
    ("02_bkt_model.py", ()),
    ("03_error_diagnosis.py", ()),
    ("05_knowledge_graph.py", ()),
    ("06_dashboard.py", ()),
    ("08_task3_generator.py", ("--all-students",)),
    ("09_task1_knowledge_structure.py", ()),
)
OUTPUT_FILES = (
    ("cleaned_data.json", "01 清洗后的作答与知识数据"),
    ("data_quality_report.json", "01 数据质量报告"),
    ("statistics.json", "01 多维统计"),
    ("mastery_matrix.json", "02 掌握度矩阵"),
    ("student_profiles.json", "02 学生画像"),
    ("error_diagnosis.json", "03 错因诊断"),
    ("error_pattern_summary.json", "03 错因汇总"),
    ("knowledge_graph.html", "05 可交互知识图谱"),
    ("dashboard.html", "06 学情仪表盘"),
    ("task3_recommendations.json", "08 任务3建议"),
    ("task1_knowledge_structure.json", "09 任务1知识结构"),
)


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_root() -> Path:
    if _is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _find_script_dir(project_root: Path) -> Path:
    if _is_frozen():
        path = _bundle_root() / "completed_scripts"
        if (path / "01_data_loader.py").is_file():
            return path
    else:
        for path in project_root.iterdir():
            if path.is_dir() and (path / "01_data_loader.py").is_file():
                return path
    raise FileNotFoundError("未找到包含 01_data_loader.py 的脚本目录。")


def _find_project_root() -> Path:
    if not _is_frozen():
        return Path(__file__).resolve().parent.parent

    executable_dir = Path(sys.executable).resolve().parent
    for candidate in (executable_dir, *executable_dir.parents):
        if (candidate / "ui" / "app.py").is_file():
            return candidate
    return executable_dir


def _default_data_dir(project_root: Path) -> Path:
    external = project_root / "赛题材料" / "赛题数据" / "赛题资料包" / "4_赛题数据" / "模拟学情数据"
    if external.is_dir():
        return external
    if _is_frozen():
        bundled = _bundle_root() / "embedded_data"
        if bundled.is_dir():
            return bundled
    return external


def _validate_data_dir(data_dir: Path) -> None:
    missing = [name for name in DATA_FILES if not (data_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"数据目录缺少必需 CSV：{', '.join(missing)}\n数据目录：{data_dir}"
        )


def _run_script(script: Path, args: tuple[str, ...] | list[str]) -> None:
    if not script.is_file():
        raise FileNotFoundError(f"未找到脚本：{script.name}")

    previous_argv = sys.argv
    sys.argv = [str(script), *args]
    try:
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise RuntimeError(f"{script.name} 退出码：{exc.code}") from exc
    finally:
        sys.argv = previous_argv


def _write_output_readme(staging_dir: Path, backup_name: str, started_at: datetime) -> None:
    lines = [
        "SmartLearn-AI 数据产物",
        f"生成时间：{started_at:%Y-%m-%d %H:%M:%S}",
        "",
        "界面读取本目录根层的 JSON 文件。请不要移动或重命名核心 JSON。",
        "更新产物后，如界面已打开，请重启界面以重新加载数据。",
        "",
        "核心产物：",
    ]
    lines.extend(f"- {name}：{description}" for name, description in OUTPUT_FILES)
    lines.extend([
        "",
        "可选产物：knowledge_base.json（04 RAG）。本 EXE 默认不运行 04，",
        "因此原有 knowledge_base.json 会保留；它不会由本次运行刷新。",
        "07 多智能体是交互式模块，当前不打入 EXE；待完成模型接入后再单独发布。",
        "未被本次生成覆盖的文件和子目录也会保留。",
        f"本次被替换文件的旧版本备份目录（如有）：{backup_name}",
        "",
    ])
    (staging_dir / "README_OUTPUT.txt").write_text("\n".join(lines), encoding="utf-8")


def _publish_staged_output(staging_dir: Path, output_dir: Path, run_id: str) -> Path | None:
    backup_dir = output_dir.parent / f"{output_dir.name}_backup_{run_id}"
    published: list[tuple[Path, Path | None]] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    staged_files = sorted(path for path in staging_dir.rglob("*") if path.is_file())
    if not staged_files:
        raise RuntimeError("暂存产物目录为空，拒绝更新 output。")

    try:
        for staged_file in staged_files:
            relative = staged_file.relative_to(staging_dir)
            target = output_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)

            backup_file = None
            if target.exists():
                if not target.is_file():
                    raise IsADirectoryError(f"产物路径被同名目录占用：{target}")
                backup_file = backup_dir / relative
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                temporary_backup = backup_file.with_name(backup_file.name + ".tmp")
                try:
                    shutil.copy2(target, temporary_backup)
                    os.replace(temporary_backup, backup_file)
                finally:
                    if temporary_backup.exists():
                        temporary_backup.unlink()

            published.append((target, backup_file))
            os.replace(staged_file, target)
    except Exception as exc:
        rollback_errors = []
        for target, backup_file in reversed(published):
            try:
                if backup_file is not None and backup_file.is_file():
                    os.replace(backup_file, target)
                elif target.exists():
                    target.unlink()
            except OSError as rollback_error:
                rollback_errors.append(f"{target}: {rollback_error}")
        if rollback_errors:
            raise RuntimeError(
                "更新 output 失败，自动回滚也未能完成；旧文件备份保留在 "
                f"{backup_dir}。回滚错误：{' | '.join(rollback_errors)}"
            ) from exc
        raise

    return backup_dir if backup_dir.is_dir() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="运行智慧学伴数据生成流程；默认输出到项目 output/。"
    )
    parser.add_argument("--data-dir", help="覆盖输入 CSV 目录")
    parser.add_argument("--output-dir", help="覆盖输出目录；UI 默认仍读取项目根目录 output/")
    args = parser.parse_args(argv)

    project_root = _find_project_root()
    script_dir = _find_script_dir(project_root)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else project_root / "output"
    if output_dir == project_root or output_dir in project_root.parents:
        raise ValueError("输出目录不能是项目根目录或其上级目录；请使用项目根目录下的 output/。")

    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else _default_data_dir(project_root)
    _validate_data_dir(data_dir)

    started_at = datetime.now()
    run_id = started_at.strftime("%Y%m%d_%H%M%S_%f")
    staging_dir = output_dir.parent / f".{output_dir.name}.staging_{run_id}"
    backup_name = f"{output_dir.name}_backup_{run_id}"
    staging_dir.mkdir(parents=True, exist_ok=False)

    print("=" * 68)
    print("SmartLearn-AI 数据生成")
    print(f"输入数据：{data_dir}")
    print(f"暂存位置：{staging_dir}")
    print("现有 output 只会在所有脚本和校验成功后更新；被覆盖文件会备份。")
    print("=" * 68)

    previous_env = {key: os.environ.get(key) for key in ("SS_DATA", "SS_OUT")}
    published = False
    try:
        os.environ["SS_DATA"] = str(data_dir)
        os.environ["SS_OUT"] = str(staging_dir)

        for filename, step_args in PIPELINE:
            print(f"\n=== {filename} ===")
            _run_script(script_dir / filename, step_args)
            sys.stdout.flush()

        print("\n=== verify.py ===")
        verify_script = _bundle_root() / "verification" / "verify.py" if _is_frozen() else (
            project_root / "scripts" / "verify.py"
        )
        _run_script(verify_script, ("--output-dir", str(staging_dir)))

        _write_output_readme(staging_dir, backup_name, started_at)
        backup_dir = _publish_staged_output(staging_dir, output_dir, run_id)
        published = True
        shutil.rmtree(staging_dir)

        print("\n" + "=" * 68)
        print(f"[OK] 已更新 UI 数据目录：{output_dir}")
        print(f"说明文件：{output_dir / 'README_OUTPUT.txt'}")
        if backup_dir:
            print(f"旧版文件备份：{backup_dir}")
        else:
            print("本次没有覆盖同名旧文件，因此未创建备份目录。")
        print("=" * 68)
        return 0
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if not published and staging_dir.exists():
            print(f"\n[未发布] 原 output 保持不变；暂存文件保留在：{staging_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
