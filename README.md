# 智慧学伴 · 学情诊断与个性化学习智能体

第二届北京市大学生"人工智能+"创新大赛 · 北京数据集团赛题

> 赛题数据（课标、学情记录等）仅限本次大赛使用，不得外传或用于其他用途，赛后须按要求删除。

## 第一次用？直接打开 [00_开始使用.html](00_开始使用.html)（或双击根目录三个 bat 文件）

## 30 秒跑起来

```powershell
.\scripts\bootstrap.ps1                                   # 建环境 + 装依赖 + 自检
.\scripts\run_all.ps1                                       # 01–09 一键（08 含全班建议；04 默认跳过）
# 若已激活旧虚拟环境：.\scripts\run_all.ps1 -Python (Get-Command python).Source
cd ui ; .\run.bat                                           # 启动界面 http://localhost:8501
```

详细说明、文件清单、常见错误：**[docs/复现手册.md](docs/复现手册.md)**
技术方案（含创新点、评分对齐、答辩预案）：**[docs/技术文档.md](docs/技术文档.md)**
界面与智能体流程的验证记录：**[docs/界面验证记录.md](docs/界面验证记录.md)**

## 单文件 EXE（队内使用）

```powershell
.\.venv-ui\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build_exe.ps1
.\dist\SmartLearn-AI.exe
```

EXE 将赛题 CSV 嵌入单文件，默认生成到项目根目录 `output/`，供现有 UI 读取；生成先在暂存目录完成并通过校验，再更新产物，旧版同名文件会备份到 `output_backup_*`。04 RAG 因依赖和模型体积较大、07 多智能体因仍需接入模型，均不打入 EXE；已有 `knowledge_base.json` 会保留。赛题数据和 EXE 仅限队内使用。

## 这套东西是什么

| 模块 | 目录 | 产出 |
|---|---|---|
| 数据治理与统计 | `已完成脚本/01_data_loader.py` | 清洗后数据、质量报告、五维统计 |
| 知识追踪 | `已完成脚本/02_bkt_model.py` | 40×9 掌握概率、学生画像 |
| 错因诊断 | `已完成脚本/03_error_diagnosis.py` | 385 条结构化错因（C1–C6） |
| 知识库（可选） | `已完成脚本/04_rag_knowledge.py` | 课标/教材/题目向量索引 |
| 知识图谱 | `已完成脚本/05_knowledge_graph.py` | 交互式 HTML |
| 学情仪表盘 | `已完成脚本/06_dashboard.py` | 8 图 HTML |
| 多智能体演示 | `已完成脚本/07_multi_agent.py` | 可解释的智能体路由与建议 |
| 任务3建议生成 | `已完成脚本/08_task3_generator.py` | 3 个典型案例 + 全班建议，需人工审校标记项 |
| 任务1知识结构 | `已完成脚本/09_task1_knowledge_structure.py` | 可追溯的课标、教材、题目及作答证据映射 |
| 交互界面 | `ui/` | Streamlit 四页 + DeepSeek 诊断 |

## 三条口径（代码里写死，答辩可直接讲）

1. 指标证据 < 3 条 → 只输出「证据不足」，不判掌握/薄弱；
2. 整体掌握度只用"可判定指标"计算，全无证据时显示 `—`；
3. LLM 输出必须可映射到 C1–C6 且指标在 9 个之内，否则整条丢弃，以规则结果为准。

## 环境

Python ≥ 3.10；运行时依赖（界面 + 脚本）见 `requirements.txt`，RAG 可选依赖见 `requirements-rag.txt`，打包 exe 见 `requirements-build.txt`。
