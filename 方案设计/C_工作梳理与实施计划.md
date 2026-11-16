# C 角色工作梳理与实施计划

> 角色：C —— 交互入口（Streamlit）+ LLM 诊断升级
> 前置事实核对时间：2026-11-16 15:56
> 依赖现状：`已完成脚本/01–06` 已就绪，`output/` 已有 01–03 的 11 个产物；04/05/06 的产物由 A 负责

---

## 0. 范围变更（2026-11-16 已确认，以下面为准）

| 事项 | 结论 | 对本计划的影响 |
|---|---|---|
| 依赖安装 | 授权 C 用 full-access 重试 | ⚠️ venv 已建好、pip 可用，但**包安装被中文路径卡住**；后续需你在自己终端执行 3 条命令（见 §2.2） |
| 04/05/06 产物 | **由 A 负责**，C 不补跑 | 我按"产物可能缺席"设计：所有读取都带 `PLACEHOLDER` 降级，不阻塞开发 |
| 演示视频 | **不再由 C 做**，你自己来 | 删去原 §6 视频分镜的执行义务，仅保留"分镜建议"供你参考 |
| C 最终交付 | ①Streamlit 三页应用 ②LLM 诊断升级 ③证据链组件 ④`ui_adapter` | 见 §1（已按此收敛） |

---

## 一、我负责什么（边界先划清）

| # | 交付物 | 归属 | 说明 |
|---|---|---|---|
| 1 | **Streamlit 三页应用** | C 独做 | 选学生→掌握概率→错因→建议；班级概览；任务1 知识结构 |
| 2 | **LLM 错因诊断升级** | C 独做 | 跑通 `03 --api-key`，产出 `error_diagnosis_llm.json`，界面双源对比 |
| 3 | ~~演示视频（5 分钟）~~ | **转交：你自己做** | 我仅保留分镜建议（§6），不承担录制与剪辑 |
| 4 | **UI 侧的"证据链"组件** | C 独做 | 每条结论可下钻到 `record_id`；证据不足的学生明确标注 |
| 5 | 界面截图包 | C 提供 | 供你/D 排版使用 |

**不做**（避免和 A/B 抢活）：不重写 01–06、不写 task1/task3 的 JSON 内容（B 写）、不做 BKT 算法改造（A 改）、不排 PDF（D 排）。
但我会做一层 **`ui_adapter.py`**：只读 A/B 的 JSON，做归一化与派生字段（证据量、是否不足、证据链索引），**不改他们的文件**。

---

## 二、必须先解决的 4 个现状问题（会直接影响我的交付）

### 2.1 视频素材缺一半：04/05/06 的产物不存在

`output/` 实际只有：`cleaned_data / statistics / data_quality_report / mastery_matrix / student_profiles / bkt_summary / error_diagnosis / error_pattern_summary`。
而两个 HTML 和知识库**没有生成**：

| 脚本 | 应有产物 | 当前 |
|---|---|---|
| 04 | `knowledge_base.json` + `chroma_db/` | ❌ 缺失 |
| 05 | `knowledge_graph.html` | ❌ 缺失 |
| 06 | `dashboard.html` | ❌ 缺失 |

→ 视频分镜第 1 段（仪表盘 1 分钟）和第 2 段（知识图谱 30 秒）**目前无素材**。需要在排期内先补跑 05、06；04 依赖向量模型下载，风险最高（见 2.2）。

### 2.2 环境：venv 已就绪，但包安装被"中文路径"卡住（需你执行 3 条命令）

已完成的：
- `.venv-ui/` 已用 `D:\python313` 创建成功，`pip 24.3.1` 可用（`ensurepip` 需写系统临时目录，在 full-access 下已通过）。
- 依赖清单已写进 `requirements-ui.txt`。

卡住的：`pip install` 解包时报
```
OSError: [Errno 2] No such file or directory:
'D:\\学习资料\\AI竞赛\\工作区\\pip-unpack-xxxx\\networkx-3.7-py3-none-any.whl'
```
原因是**工程路径含中文**，pip 的临时解包目录落在中文路径下（`.venv-ui` 的 `TMP/TEMP` 指向了工作区）。用 ASCII 临时目录重试的方案被否决，因此改由你在**自己的终端**执行（终端默认 `TEMP` 是 ASCII 的 `C:\Users\...\AppData\Local\Temp`，一般可直接成功）：

```powershell
cd /d "D:\学习资料\AI竞赛\工作区"
mkdir D:\tmp-pip 2>nul
set TEMP=D:\tmp-pip
set TMP=D:\tmp-pip
.venv-ui\Scripts\python.exe -m pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-ui.txt
.venv-ui\Scripts\python.exe -c "import streamlit, plotly, networkx, pandas; print('OK', streamlit.__version__)"
```

**若仍失败**：把工程挪到纯英文路径（如 `D:\AIComp`）再建 venv——这是 Windows + pip 最彻底的办法，代价是所有脚本里的 `OUTPUT_DIR` 要同步改。

### 2.3 `data_quality_report.json` 的 `issues` 是空数组（评分项硬伤）

```json
"issues": [],  "processing_summary": {"revised_events": 5, ...}
```
实测数据里至少有 8 类异常（见 `分析脚本/02`、`06`）：2 条得分越界（`DR0361` 10/1 分、`DR0535` 4/3 分）、1 条评分点和≠总分（`DR0133`）、1 条答对判 0（`DR0685`）、1 条节点越界（`DR0515` Q038 出现在未教不等式的 N01）、1 条主题错标（`DR0081`）、7 组 14 行修订版本（报告只记了 5 组）。

→ 这是任务2"数据处理"唯一可展示的证据，现在是空的。**我在界面上会做一个"数据质量"卡片**，直接读我提供的 `分析脚本` 结果补齐展示；同时建议 A 修 `01`。这一条会写进交接单。

### 2.4 `student_profiles.json` 存在"1 条证据=35.5% 掌握概率"

例：D01 的 `T02I2` 只有 **1 条**作答记录，却被判 `weak` 并进入推荐路径。

→ 界面上**不能**把 25%/35.5% 当成事实展示。我的处理：每个指标旁强制显示证据量徽标（`n=1 ⚠ 证据不足`），并对 `n<3` 的指标单独归入"待补充观察"，不参与"薄弱"排序。这既符合赛题口径，也给 A 留出修复时间。

---

## 三、我能直接用的数据契约（已核对字段名）

| 文件 | 结构 | 我取用的字段 |
|---|---|---|
| `mastery_matrix.json` | `{sid: {ind: float}}` | 9 指标概率（仅作参考展示，需配证据量） |
| `student_profiles.json` | `{sid: {…10 键}}` | `class_id / overall_mastery / overall_status / weak_developing_mastered_no_data / recommended_learning_path / indicator_details` |
| `error_diagnosis.json` | `list[385]` | `record_id / student_id / question_id / indicator_id / score / full_score / student_answer / error_type / error_type_code / error_description / diagnosis_source / confidence` |
| `statistics.json` | 7 个分区 | `overall / by_theme / by_indicator / by_scoring_point / by_student / by_class_theme / cross_node_changes` |
| `cleaned_data.json` | 大对象 | `records / students / items`（做证据下钻用） |
| **待 B 交付** | `task1_knowledge_structure.json`、`task3_recommendations.json` | 我的任务1页与建议页要读；未就绪前用 mock |

**我需要的 B 侧最小字段**（先给"能跑"的接口，B 可以后补）：
```json
// task3_recommendations.json
{"students": [{"student_id":"D01","diagnosis_summary":"…",
  "recommendations":[{"priority":1,"indicator":"T03I1","reason":"…",
    "recommended_questions":["Q041","Q042","Q043"],
    "step_hints":["…"],"follow_up_condition":"…"}]}]}
```

---

## 四、Streamlit 应用设计（三页 + 一个抽屉）

```
app.py                       # 入口：侧栏选学生 / 切页
pages/
  1_学生诊断.py               # 默认页：整体画像 → 指标雷达 → 错因 → 建议 → 证据下钻
  2_班级概览.py               # 班级×主题、指标排名、共性薄弱题
  3_任务1_知识结构.py          # 课标↔教材↔指标↔题目 四列联动 + 学习卡
components/
  evidence.py                # 证据链组件：结论 → record_id → 原始作答/过程/评分点
  badges.py                  # 证据量徽标：n>=3 正常 / n<3 灰 + "证据不足"
  charts.py                  # 复用 06 的图表数据，Plotly 重绘（不嵌 iframe）
services/
  loader.py                  # 只读 output/*.json，缓存
  llm.py                     # provider 链：rule → DeepSeek API → 离线模板
ui_adapter.py                # 归一化 + 派生（证据量、insufficient、证据索引）
```

**页面 1（核心，占 70% 演示时间）**
1. 顶部：学生选择 + 班级 + 整体掌握度 + **覆盖率角标**（`可判定 4/9 指标`）
2. 左：9 指标雷达（红黄绿），灰色=证据不足
3. 中：按指标折叠的错因卡（`error_type / 一句话描述 / 关联题号 / n 条证据`）
4. 右：建议路径（读 B 的 `task3_recommendations.json`；无则显示"待 B 交付"占位，不编造）
5. 底部抽屉：任点一条结论 → 展开原始记录（作答、解答过程、评分点得分）

**页面 2**：`by_class_theme` 柱状 + `by_indicator` 排名 + `by_question` 薄弱 Top5（全部来自 `statistics.json`，不重算）。

**页面 3**：任务1 四列联动（课标页 → 教材页 → 指标 → 题目），读 B 的 `task1_knowledge_structure.json`；未就绪时用我生成的占位（明确标 `PLACEHOLDER`，禁止伪造成果）。

**关键取舍**：不做自由聊天框。改做**受控问答**（下拉预设 6 个问题 + 一句自由输入），答案由 `statistics.json` 事实注入 + LLM 改写。理由：自由聊天在答辩现场最容易被问崩，且无法保证数字正确。

---

## 五、LLM 诊断升级（任务 4）怎么做才不翻车

1. 先跑规则层基线（已有 385 条，`diagnosis_source=rule`）；
2. 用 `api.txt` 里的 Key 跑 `python 03_error_diagnosis.py --api-key …`，只对**解答题错误记录**（约 100+ 条，不是 385 条全跑）调用，控制成本与时间；
3. 产出 `error_diagnosis_llm.json`，**保留 rule 版本**，界面双列对比："规则判定 / AI 判定"；
4. 校验：LLM 结果必须含 `error_type_code ∈ {C1..C6}` 且引用的题号存在于题目表，否则回退规则结果；
5. 缓存到磁盘，演示时**不实时调 API**（避免现场网络抖动）。

**加分点**：把"规则可复算、AI 可解释、两者不一致时以规则为准"写成一句答辩话术——比"我们用了大模型"高级得多。

---

## 六、视频分镜（我出脚本，与 D 交接）

| 时间 | 画面 | 对应文件 | 旁白要点 |
|---|---|---|---|
| 0:00–0:30 | 赛题三问 + 系统总览 | `app.py` 首屏 | 三任务一句话 |
| 0:30–1:30 | 任务1：四列联动 + 图谱 | 页面3 → `knowledge_graph.html` | 课标→教材→题号可追溯 |
| 1:30–3:00 | 任务2：选 D01 → 雷达 → 错因 → 证据下钻 | 页面1 | 每条结论点开是原始记录 |
| 3:00–4:00 | 任务3：三档建议（D14/D01/D03）对比 | 页面1 建议区 | 同一指标不同需求 |
| 4:00–4:40 | 班级讲评 + 数据质量卡片 | 页面2 / 质量卡 | 共性薄弱点、缺失处理 |
| 4:40–5:00 | 泛化：换一个未见过学生 | 页面1 | 不依赖硬编码 |

**录屏前检查表**：① 断网可跑；② 首屏 3 秒内；③ 不出现真实姓名；④ 不出现 API Key；⑤ 缩放 125%、深色主题统一。

---

## 七、排期（2 天，去掉视频段）

| 时段 | 任务 | 验收 |
|---|---|---|
| D0 上午 | `ui_adapter.py` + `PLACEHOLDER` 降级 + `app.py` 骨架（不依赖 04–06） | `streamlit run app.py` 出首屏 |
| D0 下午 | 页面1 全量（雷达/错因/证据抽屉/证据量徽标） | D17（证据不足）与 D01 都不崩 |
| D1 上午 | 页面2 + 页面3（B 的 JSON 未到则占位） | 三页可切换 |
| D1 下午 | LLM 升级 + 双源对比 + 缓存 + 截图包 | 100 条 LLM 诊断落盘；截图齐 |

---

## 八、风险与降级

| 风险 | 影响 | 降级方案 |
|---|---|---|
| pip 装不上（HTTPS 被断） | 无法运行/录屏 | 你先在自己终端装；我只交代码 + 严格校验逻辑 |
| 04 需要下载 embedding 模型 | 知识库页空 | 用 `knowledge_base.json`（若已有）或纯关键词检索兜底 |
| B 的 task1/task3 JSON 迟到 | 两页空 | 占位 + `PLACEHOLDER` 水印，绝不编造数据 |
| API 限流/欠费 | LLM 段落缺 | 规则结果为准，界面标"AI 诊断：离线" |
| 现场断网 | 演示失败 | 全部预生成 + 缓存，LLM 结果读本地 JSON |

---

## 九、已确认的三项决策（原"待确认"）

| 问题 | 决策 | 影响 |
|---|---|---|
| 装包由谁 | 授权 C 用 full-access 重试 → 实际被中文路径拦住 → **改由你在自己终端装**（命令见 §2.2） | 我不再尝试提权安装；代码照写，逻辑用静态校验 |
| 04/05/06 | **由 A 负责** | 我全部读取路径都做 `PLACEHOLDER` 降级，产物缺席也能演示前两页 |
| 视频 | **你自己做**，C 不参与 | §6 仅作分镜参考 |

**我现在可以直接开工的部分（不需要任何安装）**：`ui_adapter.py`、`app.py` 骨架、三页布局、证据链组件、`requirements-ui.txt`（已完成）。
需要安装才能验证的部分：`streamlit run` 真正渲染、Plotly 图、LLM 调用。

---

## 十一、交付记录（2026-11-16 完成）

| 文件 | 作用 | 状态 |
|---|---|---|
| `ui/app.py` | 入口：侧栏路由、产物目录/原始目录/API Key 配置、缓存 | ✅ |
| `ui/adapter.py` | 数据适配：证据门槛、`insufficient`、证据链、班级聚合、知识结构、质量复核 8 规则 | ✅ |
| `ui/charts.py` | 5 种 Plotly 图（雷达/指标条/证据量/班级×主题/指标排名/薄弱题） | ✅ |
| `ui/views.py` | 四个页面 + 规则 vs DeepSeek 双源对比 + 受控问答 + 导出 JSON | ✅ |
| `ui/llm.py` | DeepSeek 接入：Key 解析、磁盘缓存、强校验、离线兜底 | ✅ |
| `ui/llm_upgrade.py` | 批量生成 `error_diagnosis_llm.json`（不回写 A 的文件） | ✅ |
| `ui/selftest.py` | 无 Streamlit 依赖的自检 | ✅ 全绿 |
| `requirements-ui.txt` / `ui/README.md` | 依赖与运行说明 | ✅ |

**已验证**（本机 DSH Python，pandas 可用）：
- 6 个模块 `py_compile` 全通过；
- `selftest.py`：790 条记录 / 40 名学生 / 385 条诊断，40/40 学生视图正常，知识结构 9 行，质量复核命中 8 条规则，LLM 校验函数正常；
- **假 streamlit + 假 plotly 的干跑**：`render_diagnosis`（D01/D14/D17/D30）、`render_class`、`render_knowledge`、`render_quality` 全部执行无异常，共渲染 15 张图、18 个表格。

**未能验证**：真实 `streamlit run`（本机未装 Streamlit；pip 受中文路径与网络限制），需你在自己终端装包后跑一次。

**刻意做的口径修正**（相对 A 的输出）：
- `D17` 这类"4 条记录却被判 medium"的情况，界面显示为「0/9 指标可判定、暂无结论」；
- `D01` 的 `T02I2`（n=1）不再进入薄弱判定，改列「证据不足」；
- `data_quality_report.issues=[]` 的问题，用 UI 侧独立复核补出 8 条并给出记录编号。
