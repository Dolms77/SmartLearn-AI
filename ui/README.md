# 智慧学伴 · 交互界面（C 角色）

Streamlit 三页应用：**学生诊断 / 班级概览 / 任务1 知识结构 / 数据质量复核**，可接入 DeepSeek API。

```
ui/
├─ app.py            # 入口（侧栏路由 + 全局状态）
├─ adapter.py        # 数据适配层：只读 output/*.json → 视图模型（证据门槛在此把关）
├─ charts.py         # Plotly 图表构件
├─ views.py          # 四个页面
├─ llm.py            # DeepSeek 接入（缓存 / 强校验 / 离线降级）
├─ llm_upgrade.py    # 批量生成 LLM 错因诊断（增量、断点续跑）
├─ selftest.py       # 不依赖 Streamlit 的自检脚本
└─ README.md
```

---

## 1. 安装

```powershell
cd "D:\学习资料\AI竞赛\工作区"
D:\python313\python.exe -m venv .venv-ui
mkdir D:\tmp-pip 2>nul
set TEMP=D:\tmp-pip
set TMP=D:\tmp-pip
.venv-ui\Scripts\python.exe -m pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-ui.txt
```

> **注意**：工程路径含中文时 pip 解包会失败（`pip-unpack-xxx` 找不到）。把 `TEMP` 指到 ASCII 目录（`D:\tmp-pip`）即可；仍失败则把整个工程挪到 `D:\AIComp` 这类纯英文路径。

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
$env:USERPROFILE="D:\学习资料\AI竞赛\工作区\.streamlit-home"
$env:HOME=$env:USERPROFILE
$env:TEMP="D:\学习资料\AI竞赛\工作区\.tmp"; $env:TMP=$env:TEMP
New-Item -ItemType Directory -Force "$env:USERPROFILE\.streamlit" | Out-Null
Set-Content "$env:USERPROFILE\.streamlit\credentials.toml" "[general]`nemail = `"`""
..\.venv-ui\Scripts\python.exe -m streamlit run app.py --server.headless=true
```

侧栏可改：**产物目录**（默认 `../output`）、**原始数据目录**（数据质量页用）、**DeepSeek API Key**（可留空）。

---

## 3. 接入 DeepSeek（可选，不接也能用）

三种方式任选：

1. 侧栏直接填 Key（仅存在当前会话内存）；
2. 环境变量：`set DEEPSEEK_API_KEY=sk-xxx`；
3. 工程根目录放 `api.txt`（内容只有 Key 一行）—— 本项目已支持自动读取。

**注意：`api.txt` 不要提交、不要出现在录屏里。**

有了 Key 以后有两处增强：

- **学生诊断页 → 错因诊断**：点「调用 DeepSeek 生成深度诊断」，右侧栏出现 AI 版错因（思维误区 + 补救提示）；
- **学生诊断页 → 问答**：预设 4 个问题或自定义提问，答案受"事实白名单"约束（只允许使用结构化统计里的数字）。

批量预生成（演示时就不用现场联网）：

```powershell
cd ui
..\.venv-ui\Scripts\python.exe llm_upgrade.py --limit 120
```

它只写 `output/error_diagnosis_llm.json`（**不覆盖** A 的 `error_diagnosis.json`），支持断点续跑；界面会自动读取并与规则结果并排展示。

---

## 4. 界面在做什么（答辩可直接用）

**第一层是"唤醒智能体"，不是一进来就给报表。**

```
落地页（智能体形象 + 呼吸光晕 + 对话气泡）
   └─ 点击「唤醒智慧学伴」
        └─ 选身份：🧑‍🎓 学生 / 🧑‍🏫 教师
             ├─ 学生 → 选一个账号（D01…D40，带班级与记录数）→ 进入
             └─ 教师 → 选一个班级（DC01/DC02）→ 进入
                  ↓
        智能体自动打开「对话窗口」并弹出对应导航
```

角色不同，导航不同：

| 角色 | 导航 | 内容 |
|---|---|---|
| 学生 | 💬 对话 · 📊 我的学情 · 🎯 学习建议 · 🗺 知识地图 · 📁 成果文件 | 只看自己；对话里先报"你有几条证据、几个指标可判定" |
| 教师 | 💬 对话 · 📈 班级概览 · 👥 学生名单 · 🧹 数据质量 · 📁 成果文件 | 看班级共性薄弱点，可下钻任意学生 |

关键点：

| 模块 | 说明 | 对应评分项 |
|---|---|---|
| 对话窗口 | 气泡样式与通用 AI 助手一致；带"正在思考"动画；回答受**事实白名单**约束，无 Key 时走离线模板 | 建议适切 / 创新点 |
| 我的学情 | 掌握度**只在证据 ≥3 条时给出**；证据不足单列；每条结论可下钻 `record_id`；含三主题得分率与 BKT 轨迹 | 数据处理 / 表现描述 |
| 错因双源 | 规则（可复算）+ DeepSeek（可解释），冲突以规则为准 | 问题识别 |
| 学习建议 | 读 B 的 `task3_recommendations.json`；缺失时给"第一步 + 补测题单"，不编造 | 建议适切 |
| 班级概览 | 班级×主题、指标排名、薄弱题 Top10、**评分点 Top12、错因分布、40×9 热力图** | 分析呈现 |
| 学生名单 | 40 人覆盖/掌握度/错因条数，证据不足者不参与"最差"排名 | 回应不同需求 |
| 数据质量 | 读原始 CSV 重算 8 条规则，给出命中记录编号 | 数据处理 |
| 成果文件 | 05/06 产物下载，图谱可内嵌预览，缺失项标原因 | 复核材料充分 |

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
| `task1_knowledge_structure.json`（B） | 用 `cleaned_data.knowledge_structure` 现组装，并标注"UI 组装版" |
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
