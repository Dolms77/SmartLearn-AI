# 智慧学伴 · 交互界面（C 角色）

Streamlit 应用：**11 个页面**（学生 5 / 教师 6）+ 多智能体对话；入口为「选择身份 → 选身份 → 选账号」，欢迎页右侧还有「上传学情数据」入口。默认本地 Ollama 推理，可切云端 DeepSeek。

```
ui/
├─ app.py                # 入口（阶段路由 + 全局状态）
├─ dataset.py            # 上传学情数据：模板、校验、后台分析、进度
├─ adapter.py            # 数据适配层：只读 output/*.json → 视图模型（证据门槛在此把关）
├─ charts.py             # Plotly 图表构件
├─ comparison_dashboard.py # 班级对比 / 错因 waffle 的 React 组件桥接
├─ scoring_review.py     # 评分步骤列表的 React 组件桥接
├─ class_comparison/     # React 组件源码与 dist 构建（dist 已提交）
├─ views.py              # 班级概览 / 任务1 / 数据质量 / 知识与成果等页面组件
├─ llm.py                # 本地 Ollama / 云端 DeepSeek 双通道（缓存 / 守卫 / 离线降级）
├─ llm_upgrade.py        # 批量生成 LLM 错因诊断（增量、断点续跑）
├─ selftest.py           # 不依赖 Streamlit 的自检脚本
└─ README.md
```

---

## 1. 安装

```powershell
# From the repository root
.\scripts\bootstrap.ps1
```

Bootstrap creates `.venv-ui`, installs the UI and script dependencies from the repository manifests, and runs self-tests. It also redirects pip's temporary files into the repository.

验证：

```powershell
.venv-ui\Scripts\python.exe -m streamlit version
.venv-ui\Scripts\python.exe ui\selftest.py
```

`selftest.py` 不需要 Streamlit，先跑它确认数据链路是通的（预期输出 `[OK] 全部通过`）。

---

## 2. 启动

**推荐：一键脚本**（已修好 `WinError 5` 与首次邮件提示）

```powershell
cd ui
.\run.ps1          # 若提示"禁止运行脚本"，改用 .\run.bat
```

浏览器打开 `http://localhost:8501`。

> 直接 `streamlit run app.py` 会报
> `[WinError 5] 拒绝访问: 'C:\Users\Dongs\.streamlit'`，并卡在 `Email:` 提示。
> 原因是 Streamlit 首次启动要在用户目录建 `.streamlit`，而该位置不可写；
> `run.ps1` 会把 `USERPROFILE` / `HOME` 指到工作区 `.streamlit-home`，
> 并预写空的 `credentials.toml`（跳过邮件收集），同时把 `TEMP` 指到 `.tmp`。
> 脚本已实测可正常起服务（`/  → 200`，`/_stcore/health → ok`）。

手动等价命令：

```powershell
$env:USERPROFILE="$PWD\.streamlit-home"      # 指到工程内任意可写目录
$env:HOME=$env:USERPROFILE
$env:TEMP="$PWD\.tmp"; $env:TMP=$env:TEMP
New-Item -ItemType Directory -Force "$env:USERPROFILE\.streamlit" | Out-Null
Set-Content "$env:USERPROFILE\.streamlit\credentials.toml" "[general]`nemail = `"`""
..\.venv-ui\Scripts\python.exe -m streamlit run app.py --server.headless=true
```

侧栏可改：**模型后端**（本地 / 云端）、**选择班级**（教师端）、**上传 / 切换学情数据**、产物目录说明。

---

## 3. 本地模型（Ollama，默认） / 云端 API（可选回退）

**默认走本机 Ollama，不联网、不需要 API Key、不上传任何数据。**

```powershell
# 一次性准备（已装过可跳过）
ollama pull deepseek-r1:8b        # ≈5.2 GB；也可用 deepseek-r1:7b
ollama list                       # 确认模型在列表里
```

界面启动后侧栏「⚙ 模型与数据」会显示 `✅ 本地 · deepseek-r1:8b 已就绪`。
模型名字不用改代码：`llm.status()` 会自动在 `deepseek-r1:8b → 7b → 任意 deepseek-r1 → 第一个模型` 里挑。

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `SA_LLM_PROVIDER` | `ollama` | 设成 `api` 才走云端 DeepSeek |
| `SA_OLLAMA_MODEL` | 自动探测 | 指定模型名 |
| `SA_OLLAMA_THINK` | `0` | 设 `1` 打开 R1 思考链（更慢，约 6 倍） |
| `SA_OLLAMA_NUM_CTX` | `4096` | 上下文窗口；8 GB 显存不够就降到 `2048` |
| `SA_OLLAMA_TIMEOUT` | `180` | 单次调用超时（秒），冷启动需要 |

两处增强：

- **学生诊断页 → 错因诊断**：点「让本地模型复核这条诊断」，右栏显示模型是**同意**还是**改判**（改判会写明"规则 C1 → 模型 C2"及理由）；
- **对话窗口**：预设问题或自定义提问，答案受"事实白名单"约束（只允许使用结构化统计里的数字）。

批量预生成（演示时不用现场等）：

```powershell
cd ui
..\.venv-ui\Scripts\python.exe llm_upgrade.py --limit 173     # 约 11 分钟，本地零费用
..\.venv-ui\Scripts\python.exe llm_upgrade.py --limit 5 --think   # 打开思考链对比效果
```

实测（本机 4060 8 GB，`deepseek-r1:8b`，`think=0`）：**173/173 成功、约 3.9 秒/条、总计 11 分钟**；
模型对规则初判 **同意 148 条（86%）、改判 25 条（14%）**，改判均附具体理由。

只写 `output/error_diagnosis_llm.json`（**不覆盖** A 的 `error_diagnosis.json`），支持断点续跑；界面自动读取并与规则结果并排展示。

> **回退到云端**：`$env:SA_LLM_PROVIDER="api"` + 配置 `DEEPSEEK_API_KEY`（或根目录 `api.txt`）。
> 代码里两套通道都保留，切换只改环境变量，不改代码。

---

## 4. 界面在做什么（答辩可直接用）

**第一层是"选择身份"，不是一进来就给报表。**

```
欢迎页（形象 + 选择身份 / 上传学情数据）
   ├─ 点击「选择身份」
   │    └─ 选身份：🧑‍🎓 学生 / 🧑‍🏫 教师
   │         ├─ 学生 → 选一个账号（D01…D40，带班级与记录数）→ 进入
   │         └─ 教师 → 选一个班级（DC01/DC02）→ 进入
   │              ↓
   │       智能体自动打开「对话窗口」，侧栏出现对应导航
   └─ 点击「上传学情数据」
        └─ 下载 CSV 模板 → 上传 → 校验 → 勾选脚本 → 后台分析 → 完成后进入
```

角色不同，导航不同：

| 角色 | 导航 | 内容 |
|---|---|---|
| 学生 | 💬 对话 · 🤖 智能体 · 📊 我的学情 · 🎯 学习建议 · 🗺 知识与成果 | 只看自己；对话里先报"你有几条证据、几个指标可判定" |
| 教师 | 💬 对话 · 🤖 智能体 · 📈 班级概览 · 👥 学生名单 · 🧹 数据质量 · 🗺 知识与成果 | 看班级共性薄弱点，可下钻任意学生；侧栏可切班级 |

关键点：

| 模块 | 说明 | 对应评分项 |
|---|---|---|
| 对话窗口 | 气泡样式与通用 AI 助手一致；回答时显示进度提示；回答受**事实白名单**约束，无 Key 时走离线模板 | 建议适切 / 创新点 |
| 我的学情 | 掌握度**只在证据 ≥3 条时给出**；证据不足单列；每条结论可下钻 `record_id`；含三主题得分率与 BKT 轨迹 | 数据处理 / 表现描述 |
| 错因双源 | 规则（可复算）+ DeepSeek（可解释），冲突以规则为准 | 问题识别 |
| 学习建议 | 读 B 的 `task3_recommendations.json`；缺失时给"第一步 + 补测题单"，不编造 | 建议适切 |
| 班级概览 | 三个标签页：**班级对比**（React 组件：主题 / 指标 / 题目）、**薄弱点**（评分步骤列表 + 错因 waffle + 40×9 热力图）、**学生**（名单与可判定掌握度） | 分析呈现 |
| 学生名单 | 40 人覆盖/掌握度/错因条数，证据不足者不参与"最差"排名；下钻使用与「我的学情」相同的页面 | 回应不同需求 |
| 数据质量 | 读原始 CSV 重算 8 条规则，给出命中记录编号 | 数据处理 |
| 知识与成果 | 按主题浏览知识图谱，支持缩放和平移；下方查看知识结构和下载成果 | 复核材料充分 |

动画都在 `ui/theme.py` 里（纯 CSS，无外部资源）：形象浮动、双环脉冲、光晕呼吸、眨眼、页面淡入、"思考中"三点跳动。

**三条口径写死在代码里**（`adapter.MIN_EVIDENCE` / `llm.validate_diagnosis` / `views`）：

1. 指标证据 < 3 条 → 状态只能是 `证据不足`，不参与薄弱排序；
2. 整体掌握度只用"可判定指标"计算，全无证据时显示 `—`；
3. LLM 输出必须能映射到 C1–C6 且指标在 9 个之内，否则整条丢弃。

---

## 5. 数据依赖与降级

| 依赖 | 缺失时 |
|---|---|
| `output/cleaned_data.json` | 直接报错并提示先跑 `01_data_loader.py` |
| `statistics.json` / `student_profiles.json` | 对应页面降级/报错，学生诊断仍可用 |
| `task1_knowledge_structure.json`（B） | 由 `09_task1_knowledge_structure.py` 正式生成；缺失时用 `cleaned_data.knowledge_structure` 现组装并标注"UI 组装版" |
| `task3_recommendations.json`（B） | 建议区显示"待 B 交付"+ 只给排序依据 |
| `knowledge_base.json`（A 的 04） | 本界面不依赖它，无需处理 |
| DeepSeek Key | 全部功能可用，问答走离线模板 |

---

## 6. 常见问题

- **`[WinError 5] 拒绝访问: 'C:\Users\<name>\.streamlit'`** → 用 `.\run.ps1`（或 `.\run.bat`），它会重定向配置目录。
- **提示"禁止运行脚本 / UnauthorizedAccess"** → 用 `.\run.bat`，或 `powershell -ExecutionPolicy Bypass -File run.ps1`。
- **卡在 `Email:`** → 同上；`run.ps1` 已预写空 `credentials.toml`。
- **`ModuleNotFoundError: streamlit`** → 用了系统 Python；请用 `.venv-ui\Scripts\python.exe -m streamlit run app.py`。
- **中文乱码/表格错位** → 终端编码问题，浏览器界面不受影响；必要时 `chcp 65001`。
- **改动后页面没刷新** → Streamlit 会自动重跑；数据文件变更时按 `R` 或点侧栏「Rerun」。
- **首次点「调用 DeepSeek」较慢** → 单次 3–10 秒；结果会落盘到 `output/llm_cache/`，第二次即时返回。

---

## 7. 演示建议（3 分钟）

1. **落地页停 3 秒**：让形象脉冲两下，念一句"这是智能体，不是报表"；点「唤醒」；
2. 选 **学生 → D01**：对话窗口自动弹出，它先报"你 21 条记录、4 个指标可判定"；
   点推荐问题「我哪一块最薄弱？」，看思考动画 → 回答带题号与评分点；
3. 切 **我的学情**：点开薄弱指标 → 下钻到 `DR0001` 原始作答 → 展示证据链；
4. **切换身份 → 教师 → DC01**：班级概览看评分点 Top12 与 40×9 热力图；
5. **学生名单 → D17**：显示"没有任何指标达到门槛，不下结论"——这是最容易拿分的一句。
