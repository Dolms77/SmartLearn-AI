# -*- coding: utf-8 -*-
"""Plotly 图表构件。所有函数只吃 adapter 的视图模型，不直接读文件。"""
from __future__ import annotations

import plotly.graph_objects as go

BAND_COLOR = {"mastered": "#2E9E5B", "developing": "#E8A33D", "weak": "#D9534F",
              "insufficient": "#B9BFC7"}
BAND_TEXT = {"mastered": "已掌握", "developing": "发展中", "weak": "薄弱",
             "insufficient": "证据不足"}
INDICATORS = ["T01I1", "T01I2", "T01I3", "T02I1", "T02I2", "T02I3", "T03I1", "T03I2", "T03I3"]
THEMES = ["T01", "T02", "T03"]
THEME_NAMES = {"T01": "代数式与整式", "T02": "方程与方程组", "T03": "不等式与不等式组"}


def _layout(fig: go.Figure, height: int = 340, title: str = "") -> go.Figure:
    fig.update_layout(height=height, title=title, margin=dict(l=10, r=10, t=40 if title else 10, b=10),
                      font=dict(family="Microsoft YaHei, SimHei, sans-serif", size=12),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def student_radar(student: dict) -> go.Figure:
    """9 指标雷达：证据不足的指标画成灰色虚线，不与"薄弱"混淆。"""
    codes = INDICATORS
    labels = [f"{c}<br><span style='font-size:9px'>{'·' * min(x['n'], 6)}</span>"
              for c, x in zip(codes, [next(i for i in student["indicators"] if i["code"] == c)
                                      for c in codes])]
    values = [next(i for i in student["indicators"] if i["code"] == c)["mastery"] or 0 for c in codes]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=values + [values[0]], theta=labels + [labels[0]],
                                  fill="toself", name=student["sid"],
                                  line=dict(color="#2F6FED", width=2),
                                  fillcolor="rgba(47,111,237,0.18)"))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 1], tickvals=[0.2, 0.4, 0.6, 0.8, 1.0],
                                                  ticktext=["20%", "40%", "60%", "80%", "100%"])),
                      showlegend=False)
    return _layout(fig, 380)


def indicator_bars(student: dict) -> go.Figure:
    """按指标画掌握度，颜色=分级，灰色=证据不足；hover 显示证据量。"""
    xs = [x["code"] for x in student["indicators"]]
    ys = [x["mastery"] if x["mastery"] is not None else 0 for x in student["indicators"]]
    colors = [BAND_COLOR[x["band"]] for x in student["indicators"]]
    texts = [BAND_TEXT[x["band"]] for x in student["indicators"]]
    custom = [[x["n"], BAND_TEXT[x["band"]], x["name"]] for x in student["indicators"]]
    fig = go.Figure(go.Bar(
        x=xs, y=ys, marker_color=colors,
        text=[f"{y:.0%}" if v["band"] != "insufficient" else "—"
              for y, v in zip(ys, student["indicators"])],
        textposition="outside", customdata=custom,
        hovertemplate="%{x} %{customdata[2]}<br>掌握度 %{y:.1%}<br>证据 %{customdata[0]} 条"
                      "<br>判定 %{customdata[1]}<extra></extra>",
    ))
    fig.update_yaxes(range=[0, 1.1], tickformat=".0%", title="掌握度")
    fig.update_xaxes(tickangle=-40)
    return _layout(fig, 340)


def evidence_bars(student: dict) -> go.Figure:
    """证据量条形：直观暴露"哪几个指标其实没数据"。"""
    xs = [x["code"] for x in student["indicators"]]
    ns = [x["n"] for x in student["indicators"]]
    colors = [BAND_COLOR[x["band"]] for x in student["indicators"]]
    fig = go.Figure(go.Bar(x=xs, y=ns, marker_color=colors,
                           text=ns, textposition="outside",
                           hovertemplate="%{x}：%{y} 条证据<extra></extra>"))
    fig.add_hline(y=3, line_dash="dot", line_color="#888",
                  annotation_text="证据门槛 3 条", annotation_position="top left")
    fig.update_yaxes(title="已评分记录数")
    fig.update_xaxes(tickangle=-40)
    return _layout(fig, 280)


def class_theme_chart(class_rows: dict) -> go.Figure:
    """班级 × 主题分组柱。"""
    classes = [c for c in class_rows]
    fig = go.Figure()
    for t in THEMES:
        fig.add_trace(go.Bar(
            name=THEME_NAMES[t], x=classes,
            y=[class_rows[c].get(t) or 0 for c in classes],
            text=[f"{(class_rows[c].get(t) or 0):.1%}" for c in classes],
            textposition="outside",
        ))
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title="得分率")
    fig.update_layout(barmode="group", legend=dict(orientation="h", y=-0.2))
    return _layout(fig, 360)


def indicator_rank_chart(by_indicator: dict) -> go.Figure:
    """9 指标得分率排序（班级/全体）。"""
    rows = sorted(((k, v.get("score_rate", 0), v.get("count", 0)) for k, v in by_indicator.items()),
                  key=lambda x: x[1])
    if not rows:
        return _layout(go.Figure(), 300)
    codes = [r[0] for r in rows]
    rates = [r[1] for r in rows]
    counts = [r[2] for r in rows]
    colors = ["#D9534F" if r < 0.5 else ("#E8A33D" if r < 0.7 else "#2E9E5B") for r in rates]
    fig = go.Figure(go.Bar(y=codes, x=rates, orientation="h", marker_color=colors,
                           text=[f"{r:.0%}" for r in rates], textposition="outside",
                           customdata=counts,
                           hovertemplate="%{y}：得分率 %{x:.1%}，%{customdata} 条<extra></extra>"))
    fig.update_xaxes(range=[0, 1], tickformat=".0%")
    return _layout(fig, 340)


def question_rate_chart(by_question: dict, top: int = 10) -> go.Figure:
    """最薄弱题目 Top N。"""
    rows = [(q, v) for q, v in by_question.items() if v.get("n", 0) >= 5]
    rows.sort(key=lambda kv: kv[1]["rate"])
    rows = rows[:top]
    if not rows:
        return _layout(go.Figure(), 300)
    fig = go.Figure(go.Bar(
        y=[f"{q} {v['indicator']}" for q, v in rows],
        x=[v["rate"] for _, v in rows], orientation="h",
        marker_color="#D9534F",
        text=[f"{v['rate']:.0%} (n={v['n']})" for _, v in rows], textposition="outside",
        customdata=[v["text"][:40] for _, v in rows],
        hovertemplate="%{y}<br>%{customdata}<br>得分率 %{x:.1%}<extra></extra>",
    ))
    fig.update_xaxes(range=[0, 1], tickformat=".0%")
    return _layout(fig, 360)


def timeline_chart(history: list[float], name: str) -> go.Figure:
    """单个指标的掌握概率轨迹（BKT 输出），用于展示"变化过程"。"""
    fig = go.Figure(go.Scatter(y=history, mode="lines+markers", name=name,
                               line=dict(color="#2F6FED")))
    fig.update_xaxes(title="作答次序")
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title="掌握概率")
    return _layout(fig, 240)

# ---- 追加：评分点 / 错误类型 / 热力图 / 主题得分率 ----
FLAG_COLOR = {"critical": "#C0392B", "weak": "#E8A33D", "normal": "#2E9E5B"}


def scoring_point_chart(rows: list[dict], height: int = 420) -> go.Figure:
    """薄弱评分点 TopN（横向条，红色=0% 级 critical）。"""
    if not rows:
        return _layout(go.Figure(), height)
    labels = [f"{r['评分点']} {r['标记']}" for r in rows]
    vals = [r["得分率"] for r in rows]
    colors = [FLAG_COLOR.get(r["标记"], "#888") for r in rows]
    fig = go.Figure(go.Bar(
        y=labels, x=vals, orientation="h", marker_color=colors,
        text=[f"{v:.0%} (n={r['样本']})" for v, r in zip(vals, rows)],
        textposition="outside",
        customdata=[[r["指标"], r["题干"]] for r in rows],
        hovertemplate="%{y}<br>%{customdata[0]} · %{customdata[1]}"
                      "<br>得分率 %{x:.1%}<extra></extra>",
    ))
    fig.update_xaxes(range=[0, 1], tickformat=".0%")
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, height)


def error_type_chart(rows: list[dict]) -> go.Figure:
    """六类错因分布。"""
    if not rows:
        return _layout(go.Figure(), 320)
    fig = go.Figure(go.Bar(
        x=[f"{r['代码']} {r['类型']}" for r in rows], y=[r["条数"] for r in rows],
        text=[f"{r['条数']}（{r['占比']}%）" for r in rows], textposition="outside",
        marker_color="#4C78A8",
    ))
    fig.update_yaxes(title="错误记录数")
    return _layout(fig, 320)


def mastery_heatmap_chart(data: dict, height: int = 620) -> go.Figure:
    """学生×指标 热力图；空白=证据不足。"""
    fig = go.Figure(go.Heatmap(
        z=data["z"], x=data["indicators"], y=data["students"],
        customdata=data["hover"],
        colorscale=[[0, "#C0392B"], [0.4, "#E8A33D"], [0.7, "#9BC53D"], [1, "#2E9E5B"]],
        zmin=0, zmax=1,
        hovertemplate="%{customdata}<extra></extra>",
        colorbar=dict(title="掌握度", tickformat=".0%"),
        xgap=1, ygap=1,
    ))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=9))
    fig.update_xaxes(side="top")
    return _layout(fig, height)


def theme_rates_chart(rates: dict) -> go.Figure:
    """个体三主题得分率。"""
    keys = [t for t in THEMES if t in rates]
    vals = [rates[k] for k in keys]
    fig = go.Figure(go.Bar(
        x=[THEME_NAMES.get(k, k) for k in keys], y=vals,
        text=[f"{v:.0%}" for v in vals], textposition="outside",
        marker_color=["#D9534F" if v < 0.5 else ("#E8A33D" if v < 0.7 else "#2E9E5B") for v in vals],
    ))
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    return _layout(fig, 260)
