# -*- coding: utf-8 -*-
"""Plotly 图表构件（科研级视觉系统 v2）。

所有函数只吃 adapter 的视图模型，不直接读文件。

v2 相对初版的三个变更：
  1. 修复「图表标题渲染成 undefined」：旧 _layout 在无标题时执行
     update_layout(title=None)，经 plotly 7.x 序列化成 title:{}，
     前端 Plotly.js 把空标题对象渲染成英文 "undefined"。
     现在无标题时完全不写 title 字段。
  2. 修复「页面顶部黄色英文弃用警告」：st.plotly_chart(fig, width="stretch")
     是 Streamlit 1.52+ 的新参数；装了 1.50 及更旧版本时它落进 **kwargs，
     触发 "keyword arguments have been deprecated..." 警告框。
     新增统一出口 show(fig)：按已装 Streamlit 版本自动选调用方式。
  3. 视觉升级为科研图表风：墨色文字/灰阶网格的克制配色、分级参考带、
     全体均值参考线、样本量与小样本标注、证据不足斜纹填充、
     对错事件驱动的 BKT 轨迹标记。
"""
from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

# ============================================================
# 设计系统（科研图表风：单色克制 + 语义红绿）
# ============================================================
INK = "#1F2A3D"     # 主文字（墨蓝黑）
SUB = "#5E6C80"     # 次级文字（蓝灰）
FAINT = "#9AA7B8"   # 弱提示文字
GRID = "#E6EBF2"     # 网格线
AXIS = "#C6D0DE"     # 轴线/描边
PAPER = "rgba(0,0,0,0)"
FONT = ("Helvetica Neue, PingFang SC, Hiragino Sans GB, "
        "Microsoft YaHei, Source Han Sans SC, sans-serif")

# 班级双色：钢蓝 / 赭橙（色觉安全对比）
CLASS_COLORS = {"DC01": "#3E7CB1", "DC02": "#D08770"}

BAND_COLOR = {"mastered": "#3E8E62", "developing": "#D9A441", "weak": "#BF4342",
              "insufficient": "#B7BFCA"}
BAND_TEXT = {"mastered": "已掌握", "developing": "发展中", "weak": "薄弱",
             "insufficient": "证据不足"}
# 语义渐变：低分红 → 琥珀 → 黄绿 → 高分绿（克制版，比彩虹色板更期刊）
PALETTE = ["#3E7CB1", "#8FA9C5", "#D9A441", "#B88AB6", "#5FA38B", "#C97B6D"]
RATE_SCALE = [[0.0, "#BF4342"], [0.35, "#D9A441"],
              [0.65, "#8CB66A"], [1.0, "#3E8E62"]]
BRAND_SCALE = [[0.0, "#D3E0EC"], [0.5, "#7FA3C6"], [1.0, "#2C5F8A"]]
FLAG_COLOR = {"critical": "#BF4342", "weak": "#D9A441", "normal": "#3E8E62"}

INDICATORS = ["T01I1", "T01I2", "T01I3", "T02I1", "T02I2", "T02I3",
              "T03I1", "T03I2", "T03I3"]
THEMES = ["T01", "T02", "T03"]
THEME_NAMES = {"T01": "代数式与整式", "T02": "方程与方程组", "T03": "不等式与不等式组"}
# 主题三阶单色系（深→中→浅钢蓝），分组柱比彩虹色更沉稳
THEME_SHADES = ["#2C5F8A", "#5B87AE", "#A3C0D8"]


def _ramp(v: float) -> str:
    """0→红、0.35→琥珀、0.65→黄绿、1→绿 的插值色。"""
    stops = [(0.0, (191, 67, 66)), (0.35, (217, 164, 65)),
             (0.65, (140, 182, 106)), (1.0, (62, 142, 98))]
    v = max(0.0, min(1.0, float(v)))
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if v <= p1:
            t = 0.0 if p1 == p0 else (v - p0) / (p1 - p0)
            return "#%02X%02X%02X" % tuple(
                int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return "#3E8E62"


def _ramp_brand(v: float) -> str:
    """浅蓝 → 钢蓝，用于计数类。"""
    v = max(0.0, min(1.0, float(v)))
    c0, c1 = (211, 224, 236), (44, 95, 138)
    return "#%02X%02X%02X" % tuple(
        int(c0[i] + (c1[i] - c0[i]) * v) for i in range(3))


# ============================================================
# 统一渲染出口（修黄色弃用警告）
# ============================================================

def _st_ge(major: int, minor: int) -> bool:
    """当前 Streamlit 版本 >= major.minor ？解析失败按新版本处理。"""
    try:
        p = st.__version__.split(".")
        return (int(p[0]), int(p[1])) >= (major, minor)
    except Exception:  # noqa: BLE001
        return True


def show(fig: go.Figure) -> None:
    """跨 Streamlit 版本渲染图表，撑满容器且不触发弃用警告。

    - Streamlit >= 1.52：width="stretch"（新 API）
    - Streamlit <= 1.50：直接调用（默认即撑满容器，width 参数不存在）
    """
    if _st_ge(1, 52):
        st.plotly_chart(fig, width="stretch")
    else:
        st.plotly_chart(fig)


# ============================================================
# 统一版式（修 undefined 标题 + 科研排版）
# ============================================================

def _layout(fig: go.Figure, height: int = 340, title: str = "") -> go.Figure:
    """所有图表的公共版式。无 title 时不写 title 字段（防止前端渲染 undefined）。"""
    args = dict(
        height=height,
        margin=dict(l=8, r=8, t=30 if title else 22, b=8),
        colorway=PALETTE,
        font=dict(family=FONT, size=12, color=INK),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=AXIS,
                        font=dict(family=FONT, size=12, color=INK)),
        paper_bgcolor=PAPER, plot_bgcolor=PAPER,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=11, color=SUB),
                    bgcolor="rgba(0,0,0,0)", borderwidth=0),
    )
    if title:  # 关键修复：无标题时完全不传 title
        args["title"] = dict(text=title, x=0, xanchor="left", y=0.98,
                             yanchor="top", font=dict(size=14, color=INK),
                             pad=dict(t=2, b=4))
    fig.update_layout(**args)
    for ax in (fig.update_xaxes, fig.update_yaxes):
        ax(gridcolor=GRID, zeroline=False, linecolor=AXIS, showline=True,
           ticks="outside", tickcolor=AXIS, ticklen=4, tickwidth=1,
           tickfont=dict(size=10.5, color=SUB),
           title_font=dict(size=11, color=SUB))
    for tr in fig.data:
        if getattr(tr, "type", "") == "bar":
            try:
                tr.marker.cornerradius = 2   # 近直角：比大圆角更接近期刊风
                tr.marker.line = dict(width=0)
                tr.textfont = dict(size=10.5, color=INK)
            except Exception:  # noqa: BLE001
                pass
    fig.update_layout(bargap=0.32, bargroupgap=0.18)
    return fig


def _mean_line_h(fig: go.Figure, mean: float, axis: str = "y",
                  label: str = "全体均值") -> None:
    """均值参考线（虚线 + 角标），科研图表标配。"""
    if mean is None:
        return
    if axis == "y":
        fig.add_hline(y=mean, line=dict(color=FAINT, width=1.2, dash="dot"),
                      annotation_text=f"{label} {mean:.1%}",
                      annotation_position="top right",
                      annotation_font=dict(size=9.5, color=FAINT))
    else:
        fig.add_vline(x=mean, line=dict(color=FAINT, width=1.2, dash="dot"),
                      annotation_text=f"{label} {mean:.1%}",
                      annotation_position="top right",
                      annotation_font=dict(size=9.5, color=FAINT))


_HATCH = dict(shape="/", solidity=0.30, fillmode="overlay")


# ============================================================
# 学生个体视图
# ============================================================

def _radar_label(name: str, width: int = 7) -> str:
    """雷达轴标签：中文长名按固定宽度折行，避免窄列里被裁掉。"""
    text = str(name or "").strip()
    if len(text) <= width:
        return text
    return "<br>".join(text[i:i + width] for i in range(0, len(text), width))


def student_radar(student: dict) -> go.Figure:
    """学生掌握度雷达图；证据不足的指标留空，不当作零掌握度。"""
    by_code = {
        x["code"]: x
        for x in student.get("indicators", [])
    }
    ordered = [
        by_code[code]
        for code in INDICATORS
        if code in by_code
    ]

    fig = go.Figure()
    if not ordered:
        return _layout(fig, 380)

    labels = [_radar_label(x.get("name") or x["code"]) for x in ordered]
    full_names = [x.get("name") or x["code"] for x in ordered]
    values = [
        x.get("mastery")
        if x.get("band") != "insufficient"
        else None
        for x in ordered
    ]
    colors = [
        BAND_COLOR.get(x.get("band"), "#B7BFCA")
        for x in ordered
    ]
    symbols = [
        "circle-open"
        if x.get("band") == "insufficient"
        else "circle"
        for x in ordered
    ]
    custom = [
        [
            x.get("n", 0),
            x["code"],
            BAND_TEXT.get(x.get("band"), "暂不判定"),
            full_names[i],
        ]
        for i, x in enumerate(ordered)
    ]

    fig.add_trace(
        go.Scatterpolar(
            r=values + [values[0]],
            theta=labels + [labels[0]],
            mode="lines+markers",
            fill="toself",
            connectgaps=False,
            name=student.get("sid", "学生"),
            line=dict(
                color="#3E7CB1",
                width=2.2,
                shape="linear",
            ),
            fillcolor="rgba(62,124,177,0.14)",
            marker=dict(
                size=6,
                color=colors + [colors[0]],
                symbol=symbols + [symbols[0]],
                line=dict(width=1.6, color="#3E7CB1"),
            ),
            customdata=custom + [custom[0]],
            hovertemplate=(
                "%{customdata[3]}（%{customdata[1]}）"
                "<br>%{customdata[2]}"
                " · 掌握度 %{r:.0%}"
                " · 证据 %{customdata[0]} 条"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        polar=dict(
            # 留出四周刻度文字的空间：窄列（两栏布局）里长指标名最容易贴边被裁
            domain=dict(x=[0.10, 0.90], y=[0.06, 0.94]),
            radialaxis=dict(
                range=[0, 1],
                tickvals=[0.2, 0.4, 0.6, 0.8, 1.0],
                ticktext=["20%", "40%", "60%", "80%", "100%"],
                tickfont=dict(size=9, color=FAINT),
                gridcolor=GRID,
                linecolor=AXIS,
            ),
            angularaxis=dict(
                # 旋转半步，避开 0° 轴上的 20%–100% 径向刻度文字
                rotation=20,
                gridcolor=GRID,
                linecolor=AXIS,
                tickfont=dict(size=9.5, color=SUB),
            ),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=False,
    )

    fig = _layout(fig, 400)
    # 四边留白给刻度文字：默认 8px 会把 9 个长指标名裁掉
    fig.update_layout(margin=dict(l=64, r=64, t=32, b=32))
    return fig



def indicator_bars(student: dict) -> go.Figure:
    """按指标画掌握度：分级参考带 + 语义分色 + 证据不足斜纹。"""
    inds = student["indicators"]
    short = {x["code"]: (x["name"] or x["code"]) for x in inds}
    xs = [x["code"] for x in inds]
    ys = [x["mastery"] if x["mastery"] is not None else 0 for x in inds]
    # 证据不足 → 浅灰（与薄弱/发展的语义色区分开，避免把"没数据"误读成"差"）
    colors = ["#DCE2EA" if x["band"] == "insufficient"
              else BAND_COLOR.get(x["band"], "#7FA3C6") for x in inds]
    custom = [[x["n"], BAND_TEXT[x["band"]], short[x["code"]]] for x in inds]
    fig = go.Figure(go.Bar(
        x=xs, y=ys,
        marker=dict(color=colors, cornerradius=2, line_width=0),
        text=[f"{y:.0%}" if v["band"] != "insufficient" else "—"
              for y, v in zip(ys, inds)],
        textposition="outside", customdata=custom,
        hovertemplate="%{x} %{customdata[2]}<br>掌握度 %{y:.1%}"
                      "<br>证据 %{customdata[0]} 条 · 判定 %{customdata[1]}<extra></extra>",
    ))
    # 分级参考带（底层淡色区 + 右侧微标注）
    fig.add_hrect(y0=0, y1=0.4, line_width=0,
                  fillcolor="rgba(191,67,66,0.045)", layer="below")
    fig.add_hrect(y0=0.4, y1=0.7, line_width=0,
                  fillcolor="rgba(217,164,65,0.035)", layer="below")
    fig.add_hrect(y0=0.7, y1=1.0, line_width=0,
                  fillcolor="rgba(62,142,98,0.045)", layer="below")
    for y, t in ((0.2, "薄弱 <40%"), (0.55, "发展中"), (0.85, "已掌握 ≥70%")):
        fig.add_annotation(x=1.0, xref="paper", y=y, yref="y",
                           text=t, showarrow=False,
                           font=dict(size=8.5, color=FAINT),
                           xanchor="left", xshift=4)
    fig.update_yaxes(range=[0, 1.12], tickformat=".0%", title="掌握度")
    fig.update_xaxes(tickangle=-40,
                     ticktext=[short.get(c, c) for c in xs], tickvals=xs)
    return _layout(fig, 340)


def evidence_bars(student: dict) -> go.Figure:
    """证据量条形：证据不足区阴影带 + 门槛线 + 低证据斜纹柱。"""
    inds = student["indicators"]
    short = {x["code"]: (x["name"] or x["code"]) for x in inds}
    xs = [x["code"] for x in inds]
    ns = [x["n"] for x in inds]
    mx = max(ns) or 1
    # n<3（证据不足）→ 浅灰，其余按数量走钢蓝渐变
    colors = ["#DCE2EA" if n < 3 else _ramp_brand(n / mx) for n in ns]
    fig = go.Figure(go.Bar(
        x=xs, y=ns,
        marker=dict(color=colors, cornerradius=2, line_width=0),
        text=[f"{n}" for n in ns], textposition="outside",
        hovertemplate="%{x}（%{customdata[0]}）：%{y} 条证据<extra></extra>",
        customdata=[[short[c]] for c in xs],
    ))
    fig.add_hrect(y0=0, y1=3, line_width=0,
                  fillcolor="rgba(191,67,66,0.05)", layer="below")
    fig.add_hline(y=3, line=dict(color="#BF4342", width=1.3, dash="dot"),
                  annotation_text="证据门槛 3 条（低于此值不下结论）",
                  annotation_position="top left",
                  annotation_font=dict(size=9.5, color="#BF4342"))
    fig.update_yaxes(title="已评分记录数", range=[0, max(ns) * 1.25 + 0.8])
    fig.update_xaxes(tickangle=-40, ticktext=[short.get(c, c) for c in xs],
                     tickvals=xs)
    return _layout(fig, 300)


def theme_rates_chart(rates: dict) -> go.Figure:
    """个体三主题得分率（横条 + 均值线）。"""
    keys = [t for t in THEMES if t in rates]
    vals = [rates[k] for k in keys]
    if not vals:
        return _layout(go.Figure(), 240)
    mean = sum(vals) / len(vals)
    fig = go.Figure(go.Bar(
        y=[THEME_NAMES.get(k, k) for k in keys], x=vals, orientation="h",
        marker=dict(color=[_ramp(v) for v in vals], cornerradius=2, line_width=0),
        text=[f"{v:.1%}" for v in vals], textposition="outside",
        hovertemplate="%{y}：得分率 %{x:.1%}<extra></extra>",
    ))
    _mean_line_h(fig, mean, axis="x", label="三主题均值")
    fig.update_xaxes(range=[0, 1.08], tickformat=".0%")
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11, color=SUB))
    return _layout(fig, 240)


def timeline_chart(history: list, name: str,
                   corrects: list | None = None) -> go.Figure:
    """BKT 掌握概率轨迹：面积线 + 答题事件标记（绿三角=答对，红三角=答错）。

    history[0] 为初始先验，之后每个点对应一次作答更新；
    corrects 为各次作答的对错序列（与 history[1:] 对齐时才画标记）。
    """
    ys = list(history or [])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=ys, mode="lines", name="掌握概率",
        line=dict(color="#3E7CB1", width=2.4, shape="spline", smoothing=0.5),
        fill="tozeroy", fillcolor="rgba(62,124,177,0.10)",
        hovertemplate="第 %{x} 步 · 掌握概率 %{y:.1%}<extra></extra>"))
    if ys:
        fig.add_trace(go.Scatter(
            x=[0], y=[ys[0]], mode="markers", name="初始估计",
            marker=dict(symbol="diamond", size=8, color="#FFFFFF",
                        line=dict(width=1.8, color=SUB)),
            hovertemplate="初始先验 %{y:.1%}<extra></extra>"))
    if corrects and ys and len(corrects) == len(ys) - 1:
        xs_c = [i + 1 for i, c in enumerate(corrects) if c]
        ys_c = [ys[i + 1] for i, c in enumerate(corrects) if c]
        xs_w = [i + 1 for i, c in enumerate(corrects) if not c]
        ys_w = [ys[i + 1] for i, c in enumerate(corrects) if not c]
        if xs_c:
            fig.add_trace(go.Scatter(x=xs_c, y=ys_c, mode="markers", name="答对",
                                     marker=dict(symbol="triangle-up", size=9,
                                                 color=BAND_COLOR["mastered"]),
                                     hovertemplate="第 %{x} 步答对 → %{y:.1%}<extra></extra>"))
        if xs_w:
            fig.add_trace(go.Scatter(x=xs_w, y=ys_w, mode="markers", name="答错",
                                     marker=dict(symbol="triangle-down", size=9,
                                                 color=BAND_COLOR["weak"]),
                                     hovertemplate="第 %{x} 步答错 → %{y:.1%}<extra></extra>"))
    fig.update_xaxes(title="作答次序（0 = 初始估计）",
                     range=[-0.15, max(len(ys), 2) + 0.15])
    fig.update_yaxes(range=[0, 1.05], tickformat=".0%", title="掌握概率")
    return _layout(fig, 260)


# ============================================================
# 班级/群体视图
# ============================================================

def class_theme_chart(class_rows: dict) -> go.Figure:
    """两班主题哑铃图：每一行只比较同一主题的两端，避免折线误导与标签遮挡。"""
    classes = list(class_rows)[:2]
    if len(classes) < 2:
        return _layout(go.Figure(), 300)
    left, right = classes
    rows = [(THEME_NAMES[t], class_rows[left].get(t), class_rows[right].get(t), t) for t in THEMES]
    fig = go.Figure()
    for label, a, b, code in rows:
        if a is None or b is None:
            continue
        fig.add_shape(type='line', x0=min(a, b), x1=max(a, b), y0=label, y1=label, line=dict(color='#C9D5E3', width=3))
        fig.add_trace(go.Scatter(x=[a], y=[label], mode='markers+text', name=left, legendgroup=left, showlegend=(label == rows[0][0]),
            marker=dict(size=13, color=CLASS_COLORS.get(left, '#3E7CB1'), line=dict(color='white', width=2)), text=[f'{a:.1%}'], textposition='middle left',
            hovertemplate=f'{left} · {label}：%{{x:.1%}}<extra></extra>'))
        fig.add_trace(go.Scatter(x=[b], y=[label], mode='markers+text', name=right, legendgroup=right, showlegend=(label == rows[0][0]),
            marker=dict(size=13, color=CLASS_COLORS.get(right, '#D08770'), line=dict(color='white', width=2)), text=[f'{b:.1%}'], textposition='middle right',
            hovertemplate=f'{right} · {label}：%{{x:.1%}}<extra></extra>'))
    fig.update_xaxes(range=[0, 1.12], tickformat='.0%', title='主题得分率')
    fig.update_yaxes(autorange='reversed')
    return _layout(fig, 310)


def indicator_rank_chart(by_indicator: dict, names: dict | None = None) -> go.Figure:
    """9 指标得分率排序（横条 + 中文短名 + 均值线）。names: 编号→中文名。"""
    rows = sorted(((k, v['score_rate'], v.get('count') or 0)
                   for k, v in by_indicator.items() if v.get('score_rate') is not None), key=lambda x: x[1])
    if not rows:
        return _layout(go.Figure(), 300)
    codes = [r[0] for r in rows]
    rates = [r[1] for r in rows]
    counts = [r[2] for r in rows]
    ylabels = [f"{(names or {}).get(c, c)}" for c in codes]
    mean = sum(rates) / len(rates) if rates else None
    fig = go.Figure(go.Scatter(
        y=ylabels, x=rates, mode='markers+text',
        marker=dict(color=[_ramp(r) for r in rates], size=[8 + min(n, 100) ** 0.5 for n in counts], line=dict(color='white', width=1.5)),
        text=[f'{r:.0%}' for r in rates], textposition='middle right',
        customdata=list(zip(codes, counts)),
        hovertemplate='%{customdata[0]} · 证据 %{customdata[1]} 条 · 得分率 %{x:.1%}<extra></extra>'))
    _mean_line_h(fig, mean, axis='x', label='指标率算术均值（非总体得分率）')
    fig.update_xaxes(range=[0, 1.1], tickformat=".0%")
    fig.update_yaxes(tickfont=dict(size=10.5, color=SUB))
    return _layout(fig, 340)


def question_rate_chart(by_question: dict, top: int = 10,
                        names: dict | None = None) -> go.Figure:
    """最薄弱题目 Top N：小样本（n<10）降透明 + 标签警示。"""
    rows = [(q, v) for q, v in by_question.items() if v.get("n", 0) >= 5]
    rows.sort(key=lambda kv: kv[1]["rate"])
    rows = rows[:top]
    if not rows:
        return _layout(go.Figure(), 300)
    labels, vals, nvals, colors, alphas = [], [], [], [], []
    for q, v in rows:
        ind = v.get("indicator", "")
        labels.append(f"{q} · {(names or {}).get(ind, ind)}" if ind else q)
        vals.append(v["rate"])
        nvals.append(v["n"])
        colors.append(_ramp(v["rate"]))
        alphas.append(0.45 if v["n"] < 10 else 1.0)
    texts = [f"{r:.0%}（n={n}）" if n >= 10 else f"{r:.0%}（n={n} 小样本※）"
             for r, n in zip(vals, nvals)]
    fig = go.Figure()
    for label, val in zip(labels, vals):
        fig.add_shape(type='line', x0=0, x1=val, y0=label, y1=label, line=dict(color='#CCD8E4', width=2))
    fig.add_trace(go.Scatter(
        y=labels, x=vals, mode='markers+text',
        marker=dict(color=colors, opacity=alphas, size=[10 + min(n, 40) ** 0.5 for n in nvals]),
        text=texts, textposition='middle right',
        customdata=[[v.get('text', '')[:40]] for _, v in rows],
        hovertemplate='%{y}<br>%{customdata[0]}<br>得分率 %{x:.1%}<extra></extra>'))
    _mean_line_h(fig, sum(vals) / len(vals), axis='x', label='展示题目率均值（非全班总体）')
    fig.update_xaxes(range=[0, 1.12], tickformat=".0%")
    fig.update_yaxes(tickfont=dict(size=10.5, color=SUB))
    return _layout(fig, 360)


def scoring_point_chart(rows: list, height: int = 420,
                        names: dict | None = None) -> go.Figure:
    """薄弱评分点 TopN：红黄绿分档 + 小样本降透明 + 均值线。"""
    if not rows:
        return _layout(go.Figure(), height)
    labels = [f"{r['评分点']} {r['标记']}" for r in rows]
    vals = [r["得分率"] for r in rows]
    ns = [r["样本"] for r in rows]
    alphas = [0.45 if n < 10 else 1.0 for n in ns]
    fig = go.Figure(go.Scatter(
        y=labels, x=vals, mode='markers+text',
        marker=dict(color=[_ramp(v) for v in vals], opacity=alphas,
                    size=[8 + min(n, 100) ** 0.5 for n in ns], symbol='diamond'),
        text=[f'{v:.0%} (n={n})' for v, n in zip(vals, ns)],
        textposition='middle right',
        customdata=[[(names or {}).get(r.get('指标', ''), r.get('指标', '')), r.get('题干', '')] for r in rows],
        hovertemplate='%{y} · %{customdata[0]}<br>%{customdata[1]}<br>得分率 %{x:.1%}<extra></extra>'))
    _mean_line_h(fig, sum(vals) / len(vals), axis='x', label='评分点率算术均值')
    fig.update_xaxes(range=[0, 1.12], tickformat=".0%")
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=10.5, color=SUB))
    return _layout(fig, height)


def error_type_chart(rows: list) -> go.Figure:
    """六类错因分布：单色系 + 头部强调 + 总量注脚。"""
    if not rows:
        return _layout(go.Figure(), 320)
    mx = max(r["条数"] for r in rows)
    total = sum(r["条数"] for r in rows)
    colors = ["#2C5F8A" if r["条数"] == mx else "#8FA9C5" for r in rows]
    if not total:
        return _layout(go.Figure(), 320)
    fig = go.Figure(go.Pie(
        labels=[r['类型'] for r in rows], values=[r['条数'] for r in rows],
        hole=0.64, sort=False, marker=dict(colors=['#2C5F8A', '#467BA7', '#6997BB', '#91B2CD', '#B7CEDF', '#DDE7EF'][:len(rows)], line=dict(color='white', width=2)),
        textinfo='label+percent', textposition='outside',
        hovertemplate='%{label}：%{value} 条 · %{percent}<extra></extra>'))
    fig.add_annotation(x=0.5, y=0.5, xref='paper', yref='paper', text=f'{total}<br>错因记录', showarrow=False, font=dict(size=18, color=SUB))
    fig.update_layout(showlegend=False)
    return _layout(fig, 380)


def mastery_bubble_matrix_chart(data: dict, height: int | None = None) -> go.Figure:
    """学生×指标掌握度气泡矩阵；浅灰空心点明确表示证据不足。

    数据接口与 insights.mastery_heatmap 对齐：
    students / indicators / mastery / evidence / correct / indicator_names。
    """
    students = data.get("students") or []
    indicators = data.get("indicators") or []
    mastery = data.get("mastery") or []
    evidence = data.get("evidence") or []
    correct = data.get("correct") or []
    indicator_names = data.get("indicator_names") or {}

    if height is None:
        height = max(390, min(900, len(students) * 19 + 160))

    fig = go.Figure()
    # 分档与配色：科研语义色（红 <40% / 燕麦 40–80% / 绿 ≥80%）
    bands = [
        ("低于 40%", lambda value: value < 0.4, "#B4434D"),
        ('40%–70%', lambda value: 0.4 <= value < 0.7, '#C9A24E'),
        ('70% 及以上', lambda value: value >= 0.7, '#4C8A67'),
    ]
    for label, belongs, color in bands:
        xs, ys, sizes, custom = [], [], [], []
        for row_index, sid in enumerate(students):
            for col_index, code in enumerate(indicators):
                value = mastery[row_index][col_index]
                if value is None or not belongs(value):
                    continue
                n = evidence[row_index][col_index]
                xs.append(code)
                ys.append(sid)
                sizes.append(7 + 11 * value)
                custom.append([
                    sid, code, indicator_names.get(code, code),
                    value, correct[row_index][col_index], n,
                ])
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers", name=label,
            customdata=custom,
            marker=dict(
                size=sizes, sizemode="diameter", color=color, opacity=0.92,
                line=dict(color="rgba(255,255,255,0.85)", width=1),
            ),
            hovertemplate=("<b>学生 %{customdata[0]} · %{customdata[1]}</b>"
                           "<br>%{customdata[2]}"
                           "<br>掌握度 %{customdata[3]:.0%}"
                           "<br>答对 %{customdata[4]}/%{customdata[5]} 条"
                           "<extra></extra>"),
        ))

    missing_x, missing_y, missing_custom = [], [], []
    for row_index, sid in enumerate(students):
        for col_index, code in enumerate(indicators):
            if mastery[row_index][col_index] is not None:
                continue
            n = evidence[row_index][col_index]
            missing_x.append(code)
            missing_y.append(sid)
            note = (f"证据不足：已有 {n} 条记录，未达到 3 条判定门槛"
                    if n else "暂无作答记录，证据不足")
            missing_custom.append([sid, code, indicator_names.get(code, code), note])
    fig.add_trace(go.Scatter(
        x=missing_x, y=missing_y, mode="markers", name="证据不足",
        customdata=missing_custom,
        marker=dict(
            size=8, symbol="circle-open", color="#B7BFCA",
            line=dict(color="#B7BFCA", width=1.2),
        ),
        hovertemplate=("<b>学生 %{customdata[0]} · %{customdata[1]}</b>"
                       "<br>%{customdata[2]}<br>%{customdata[3]}"
                       "<extra></extra>"),
    ))

    fig.update_xaxes(
        side="top", categoryorder="array", categoryarray=indicators,
        showgrid=True, gridcolor=GRID, gridwidth=0.6,
        showline=False, ticks="", tickfont=dict(size=10, color=SUB),
    )
    fig.update_yaxes(
        autorange="reversed", categoryorder="array", categoryarray=students,
        showgrid=True, gridcolor=GRID, gridwidth=0.6,
        showline=False, ticks="", tickfont=dict(size=9, color=SUB),
    )
    fig = _layout(fig, height)
    # 气泡矩阵的图例在下方（学生数多，顶部放不下），hover 用深底白字更聚焦
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=-0.16, x=0,
                    font=dict(size=10, color=SUB)),
        hoverlabel=dict(bgcolor="#17212B", bordercolor="#38434D",
                        font=dict(color="#F5F7FA", size=12, family=FONT)),
        margin=dict(l=44, r=16, t=34, b=58),
        height=height,
        showlegend=True,
    )
    return fig
