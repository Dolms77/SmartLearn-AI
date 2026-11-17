# -*- coding: utf-8 -*-
"""
智慧学伴 - 模块6：学情可视化仪表盘（零依赖版）
================================================
职责：生成8种图表的HTML仪表盘页面

★ 本文件不需要安装任何第三方库，只用Python标准库 ★
不需要 pip install 任何东西，直接运行即可

输入：
  - statistics.json（模块1输出）
  - mastery_matrix.json（模块2输出）
  - student_profiles.json（模块2输出）
  - error_pattern_summary.json（模块3输出）

输出：
  - dashboard.html（浏览器直接打开，所有图表和样式内嵌，不需要联网）

运行方式：
  python 06_dashboard.py
"""

import json
import os
from collections import Counter, defaultdict

# ============================================================
# 配置区（改这两行路径就行）
# ============================================================

OUTPUT_DIR = os.environ.get("SS_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
INDICATOR_NAMES = {
    'T01I1': '表示数量关系并代入求值',
    'T01I2': '识别同类项去括号并化简',
    'T01I3': '用整式解释具体问题',
    'T02I1': '运用等式性质解一元一次方程',
    'T02I2': '用消元法解二元一次方程组',
    'T02I3': '列方程方程组解决实际问题',
    'T03I1': '运用不等式性质求解',
    'T03I2': '求两个不等式解集的交集',
    'T03I3': '根据实际限制列不等式'
}
INDICATORS = list(INDICATOR_NAMES.keys())


# ============================================================
# 数据加载
# ============================================================

def load_all_data():
    data = {}
    for name in ['statistics.json', 'mastery_matrix.json',
                 'student_profiles.json', 'error_pattern_summary.json']:
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data[name.replace('.json', '')] = json.load(f)
        else:
            print(f"  [警告] {name} 不存在，部分图表将无法生成")
            data[name.replace('.json', '')] = {}
    return data


# ============================================================
# HTML片段生成函数
# ============================================================

def bar_chart_html(title, labels, values, colors=None, max_val=100, unit='%'):
    """生成纯CSS柱状图"""
    if not labels:
        return f'<div class="chart-box"><h3>{title}</h3><p>无数据</p></div>'

    if colors is None:
        colors = ['#4ECDC4'] * len(labels)

    bars = ''
    for i, (label, val) in enumerate(zip(labels, values)):
        height = max(2, val / max_val * 200) if max_val > 0 else 2
        color = colors[i] if i < len(colors) else '#4ECDC4'
        bars += f'''
        <div class="bar-item">
            <div class="bar-value">{val:.1f}{unit}</div>
            <div class="bar-fill" style="height:{height}px;background:{color};"></div>
            <div class="bar-label">{label}</div>
        </div>'''

    return f'''
    <div class="chart-box">
        <h3>{title}</h3>
        <div class="bar-chart">{bars}</div>
    </div>'''


def grouped_bar_html(title, labels, series1, series2, name1, name2, max_val=100):
    """分组柱状图（两个班对比）"""
    if not labels:
        return f'<div class="chart-box"><h3>{title}</h3><p>无数据</p></div>'

    bars = ''
    for i, label in enumerate(labels):
        v1 = series1[i]
        v2 = series2[i]
        h1 = max(2, v1 / max_val * 200)
        h2 = max(2, v2 / max_val * 200)
        bars += f'''
        <div class="bar-item">
            <div class="bar-group">
                <div class="bar-value">{v1:.1f}%</div>
                <div class="bar-fill" style="height:{h1}px;background:#4ECDC4;"></div>
            </div>
            <div class="bar-group">
                <div class="bar-value">{v2:.1f}%</div>
                <div class="bar-fill" style="height:{h2}px;background:#FF6B6B;"></div>
            </div>
            <div class="bar-label">{label}</div>
        </div>'''

    return f'''
    <div class="chart-box">
        <h3>{title}</h3>
        <div class="legend"><span style="color:#4ECDC4;">■</span> {name1} &nbsp; <span style="color:#FF6B6B;">■</span> {name2}</div>
        <div class="bar-chart">{bars}</div>
    </div>'''


def radar_html(title, labels, values, max_val=100):
    """生成CSS雷达图（用SVG）"""
    if not labels:
        return f'<div class="chart-box"><h3>{title}</h3><p>无数据</p></div>'

    n = len(labels)
    cx, cy, r = 150, 160, 110
    import math

    # 计算各点坐标
    points = []
    for i in range(n):
        angle = -math.pi / 2 + i * 2 * math.pi / n
        x = cx + r * values[i] / max_val * math.cos(angle)
        y = cy + r * values[i] / max_val * math.sin(angle)
        points.append(f"{x:.1f},{y:.1f}")

    # 网格线（5圈）
    grid = ''
    for pct in [0.2, 0.4, 0.6, 0.8, 1.0]:
        pts = []
        for i in range(n):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            x = cx + r * pct * math.cos(angle)
            y = cy + r * pct * math.sin(angle)
            pts.append(f"{x:.1f},{y:.1f}")
        grid += f'<polygon points="{" ".join(pts)}" fill="none" stroke="#E0E0E0" stroke-width="1"/>'

    # 轴线
    axes = ''
    label_positions = ''
    for i in range(n):
        angle = -math.pi / 2 + i * 2 * math.pi / n
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        axes += f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#D0D0D0" stroke-width="1"/>'

        lx = cx + (r + 25) * math.cos(angle)
        ly = cy + (r + 25) * math.sin(angle)
        short_label = labels[i][:6]
        label_positions += f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="8" fill="#666">{short_label}</text>'
        label_positions += f'<text x="{lx:.1f}" y="{ly+10:.1f}" text-anchor="middle" font-size="8" fill="#4ECDC4">{values[i]:.0f}%</text>'

    polygon = f'<polygon points="{" ".join(points)}" fill="rgba(78,205,196,0.3)" stroke="#4ECDC4" stroke-width="2"/>'

    # 数据点
    dots = ''
    for p in points:
        x, y = p.split(',')
        dots += f'<circle cx="{x}" cy="{y}" r="3" fill="#4ECDC4"/>'

    return f'''
    <div class="chart-box">
        <h3>{title}</h3>
        <svg width="320" height="340" style="display:block;margin:auto;">
            {grid}
            {axes}
            {polygon}
            {dots}
            {label_positions}
        </svg>
    </div>'''


def heatmap_html(title, sids, indicators, matrix):
    """生成CSS热力图（学生×指标掌握概率）"""
    if not matrix:
        return f'<div class="chart-box"><h3>{title}</h3><p>无数据</p></div>'

    # 表头
    header = '<th style="width:50px;">学生</th>'
    for ind in indicators:
        header += f'<th class="rotate">{ind}</th>'

    # 数据行
    rows = ''
    for sid in sids:
        row_data = matrix.get(sid, {})
        row = f'<td class="sid">{sid}</td>'
        for ind in indicators:
            val = row_data.get(ind, 0)
            pct = val * 100
            if pct >= 70:
                color = '#2ECC71'
            elif pct >= 40:
                color = '#F39C12'
            else:
                color = '#E74C3C'
            text_color = 'white' if pct < 70 else '#333'
            row += f'<td class="heat-cell" style="background:{color};color:{text_color};">{pct:.0f}</td>'
        rows += f'<tr>{row}</tr>'

    return f'''
    <div class="chart-box" style="overflow-x:auto;">
        <h3>{title}</h3>
        <table class="heatmap-table">
            <thead><tr>{header}</tr></thead>
            <tbody>{rows}</tbody>
        </table>
        <div class="legend">
            <span style="color:#E74C3C;">■</span> &lt;40%薄弱 &nbsp;
            <span style="color:#F39C12;">■</span> 40-70%发展中 &nbsp;
            <span style="color:#2ECC71;">■</span> &ge;70%已掌握
        </div>
    </div>'''


def pie_html(title, labels, values, colors):
    """生成CSS饼图（用SVG conic-gradient替代）"""
    if not labels:
        return f'<div class="chart-box"><h3>{title}</h3><p>无数据</p></div>'

    total = sum(values)
    if total == 0:
        return f'<div class="chart-box"><h3>{title}</h3><p>无数据</p></div>'

    # 计算每段的角度
    segments = []
    start_angle = 0
    for i, (label, val) in enumerate(zip(labels, values)):
        pct = val / total
        angle = pct * 360
        segments.append((label, val, pct, start_angle, start_angle + angle, colors[i % len(colors)]))
        start_angle += angle

    # 用SVG画饼图
    import math
    cx, cy, r = 100, 100, 80
    paths = ''
    for label, val, pct, a1, a2, color in segments:
        x1 = cx + r * math.cos(math.radians(a1 - 90))
        y1 = cy + r * math.sin(math.radians(a1 - 90))
        x2 = cx + r * math.cos(math.radians(a2 - 90))
        y2 = cy + r * math.sin(math.radians(a2 - 90))
        large = 1 if (a2 - a1) > 180 else 0
        paths += f'<path d="M{cx},{cy} L{x1:.1f},{y1:.1f} A{r},{r} 0 {large} 1 {x2:.1f},{y2:.1f} Z" fill="{color}" stroke="white" stroke-width="2"/>'

    # 图例
    legend = ''
    for label, val, pct, _, _, color in segments:
        legend += f'<div class="pie-legend-item"><span style="color:{color};">■</span> {label}: {val}条 ({pct*100:.1f}%)</div>'

    return f'''
    <div class="chart-box">
        <h3>{title}</h3>
        <div style="display:flex;align-items:center;justify-content:center;gap:20px;">
            <svg width="200" height="200">{paths}<circle cx="{cx}" cy="{cy}" r="35" fill="white"/><text x="{cx}" y="{cy+5}" text-anchor="middle" font-size="14" fill="#666">共{total}条</text></svg>
            <div>{legend}</div>
        </div>
    </div>'''


def findings_html(findings):
    """关键发现卡片"""
    if not findings:
        return '<div class="chart-box"><h3>关键发现</h3><p>无关键发现</p></div>'

    severity_colors = {'critical': '#E74C3C', 'high': '#E67E22', 'medium': '#F39C12'}
    severity_labels = {'critical': '严重', 'high': '高', 'medium': '中'}

    cards = ''
    for f in findings:
        color = severity_colors.get(f.get('severity', 'medium'), '#999')
        label = severity_labels.get(f.get('severity', 'medium'), '?')
        cards += f'<div class="finding-card" style="border-left:4px solid {color};"><span style="color:{color};font-weight:bold;">[{label}]</span> {f.get("description", "")}</div>'

    return f'<div class="chart-box"><h3>关键发现（自动识别）</h3>{cards}</div>'


# ============================================================
# 组装仪表盘
# ============================================================

def build_dashboard(data):
    stats = data.get('statistics', {})
    mastery = data.get('mastery_matrix', {})
    error_summary = data.get('error_pattern_summary', {})
    profiles = data.get('student_profiles', {})

    # --- KPI ---
    overall = stats.get('overall', {})
    kpi_score = overall.get('score_rate_percent', '?')
    kpi_records = overall.get('total_records', '?')

    # --- 图1: 雷达图 ---
    radar_labels = [INDICATOR_NAMES[ind][:6] for ind in INDICATORS]
    radar_values = [stats.get('by_indicator', {}).get(ind, {}).get('score_rate', 0) * 100
                     for ind in INDICATORS]
    chart_radar = radar_html('九指标得分率雷达图', radar_labels, radar_values)

    # --- 图2: 班级对比 ---
    themes = ['T01', 'T02', 'T03']
    theme_names = ['代数式', '方程', '不等式']
    dc01_rates = [stats.get('by_class_theme', {}).get(f"DC01-{t}", {}).get('score_rate', 0) * 100 for t in themes]
    dc02_rates = [stats.get('by_class_theme', {}).get(f"DC02-{t}", {}).get('score_rate', 0) * 100 for t in themes]
    chart_class = grouped_bar_html('班级×主题对比', theme_names, dc01_rates, dc02_rates, 'DC01', 'DC02')

    # --- 图3: 评分点热力图 ---
    point_stats = stats.get('by_scoring_point', {})
    sorted_points = sorted(point_stats.items(), key=lambda x: x[1]['score_rate'])
    point_labels = [pid[:6] for pid, _ in sorted_points if pid]
    point_values = [info['score_rate'] * 100 for _, info in sorted_points if _]
    point_colors = ['#E74C3C' if v < 30 else '#F39C12' if v < 50 else '#2ECC71' for v in point_values]
    chart_points = bar_chart_html('评分点得分率（红色=重点关注）', point_labels, point_values, point_colors)

    # --- 图4: 学生分布 ---
    students = stats.get('by_student', {})
    sorted_students = sorted(students.items(), key=lambda x: x[1]['score_rate'])
    stu_labels = [s[0] for s in sorted_students]
    stu_values = [s[1]['score_rate'] * 100 for s in sorted_students]
    stu_colors = ['#4ECDC4' if s[1].get('class') == 'DC01' else '#FF6B6B' for s in sorted_students]
    chart_students = bar_chart_html('学生得分率分布（青=DC01 红=DC02）', stu_labels, stu_values, stu_colors)

    # --- 图5: 掌握概率热力图 ---
    if mastery:
        sorted_sids = sorted(mastery.keys(),
                             key=lambda s: sum(mastery[s].values()) / len(mastery[s]))
    else:
        sorted_sids = []
    chart_mastery = heatmap_html('BKT掌握概率热力图', sorted_sids, INDICATORS, mastery)

    # --- 图6: 错误类型饼图 ---
    by_type = error_summary.get('by_error_type', {})
    type_names_cn = {'C1': '概念误解', 'C2': '符号错误', 'C3': '计算失误',
                     'C4': '步骤遗漏', 'C5': '表达不规范', 'C6': '级联错误'}
    pie_labels = [f"{code}({type_names_cn.get(code, code)})" for code in by_type.keys()]
    pie_values = [info['count'] for info in by_type.values()]
    pie_colors = ['#FF6B6B', '#FF9F43', '#FECA57', '#48DBFB', '#A29BFE', '#54A0FF']
    chart_pie = pie_html('错误类型分布', pie_labels, pie_values, pie_colors)

    # --- 图7: 跨节点变化 ---
    changes = stats.get('cross_node_changes', [])
    type_counter = Counter(c['change_type'] for c in changes)
    type_names = {'improved': '进步', 'regressed': '退步', 'persistent_error': '顽固错误',
                  'still_wrong': '仍错(答案变)', 'both_correct': '都对'}
    change_labels = [type_names.get(k, k) for k in type_counter.keys()]
    change_values = list(type_counter.values())
    change_colors = ['#2ECC71', '#E74C3C', '#E67E22', '#F39C12', '#3498DB']
    chart_changes = bar_chart_html('跨节点(N01→N02)学习变化', change_labels, change_values,
                                    change_colors, max_val=max(change_values) if change_values else 1, unit='条')

    # --- 图8: 关键发现 ---
    chart_findings = findings_html(error_summary.get('critical_findings', []))

    # --- 组装HTML ---
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>智慧学伴 - 学情诊断仪表盘</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Microsoft YaHei','PingFang SC','Helvetica Neue',sans-serif;
       background:#F5F5F5; color:#333; line-height:1.6; }}
.header {{
    background:linear-gradient(135deg,#4ECDC4 0%,#45B7D1 100%);
    color:white; padding:25px 30px; text-align:center;
}}
.header h1 {{ font-size:24px; margin-bottom:5px; }}
.header p {{ font-size:13px; opacity:0.9; }}
.kpi-row {{
    display:flex; justify-content:center; gap:15px;
    padding:20px; flex-wrap:wrap;
}}
.kpi-card {{
    text-align:center; padding:15px 25px; border-radius:8px; min-width:130px;
    box-shadow:0 1px 3px rgba(0,0,0,0.1);
}}
.kpi-card .value {{ font-size:26px; font-weight:bold; }}
.kpi-card .label {{ font-size:12px; color:#666; margin-top:3px; }}
.section {{
    background:white; margin:10px; padding:20px; border-radius:8px;
    box-shadow:0 1px 3px rgba(0,0,0,0.1);
}}
.section h2 {{
    font-size:16px; color:#45B7D1;
    border-bottom:2px solid #E0E0E0; padding-bottom:8px; margin-bottom:15px;
}}
.chart-grid {{
    display:grid; grid-template-columns:1fr 1fr; gap:15px;
}}
@media(max-width:768px) {{
    .chart-grid {{ grid-template-columns:1fr; }}
}}
.chart-box {{
    padding:10px; border:1px solid #EEE; border-radius:6px;
}}
.chart-box h3 {{
    font-size:14px; color:#555; margin-bottom:10px; text-align:center;
}}
.bar-chart {{
    display:flex; align-items:flex-end; justify-content:center;
    gap:8px; height:240px; padding-bottom:30px; overflow-x:auto;
}}
.bar-item {{
    display:flex; flex-direction:column; align-items:center;
    min-width:40px; height:100%; justify-content:flex-end; position:relative;
}}
.bar-group {{
    display:flex; flex-direction:column; align-items:center; justify-content:flex-end;
    height:100%; margin:0 2px;
}}
.bar-fill {{
    width:24px; border-radius:3px 3px 0 0; transition:height 0.3s;
    min-height:3px;
}}
.bar-value {{
    font-size:9px; color:#666; margin-bottom:2px; white-space:nowrap;
}}
.bar-label {{
    font-size:8px; color:#888; margin-top:4px; text-align:center;
    white-space:nowrap; writing-mode:horizontal-tb;
    position:absolute; bottom:-20px; transform:rotate(-30deg); transform-origin:left top;
}}
.legend {{
    text-align:center; font-size:11px; color:#888; margin-bottom:10px;
}}
.heatmap-table {{
    border-collapse:collapse; font-size:10px; margin:auto;
}}
.heatmap-table th {{
    padding:8px 4px; color:#666; font-weight:normal;
}}
.heatmap-table th.rotate {{
    writing-mode:vertical-rl; text-orientation:upright; height:60px;
}}
.heatmap-table td {{
    padding:3px; text-align:center; border:1px solid #EEE;
}}
.heatmap-table td.sid {{
    font-weight:bold; background:#F8F8F8; text-align:right; padding-right:8px;
}}
.heat-cell {{
    width:40px; height:24px; font-size:9px;
}}
.finding-card {{
    background:#FAFAFA; padding:10px 12px; margin:5px 0;
    border-radius:3px; font-size:13px;
}}
.pie-legend-item {{
    font-size:11px; margin:3px 0;
}}
.footer {{
    text-align:center; padding:20px; color:#999; font-size:12px;
}}
</style>
</head>
<body>

<div class="header">
    <h1>智慧学伴 · 学情诊断仪表盘</h1>
    <p>七年级数学 | 3主题 9指标 54题 40学生 {kpi_records}条记录 | 得分率{kpi_score}</p>
</div>

<div class="kpi-row">
    <div class="kpi-card" style="background:#E8F5E9;">
        <div class="value" style="color:#2E7D32;">{kpi_score}</div>
        <div class="label">总体得分率</div>
    </div>
    <div class="kpi-card" style="background:#E3F2FD;">
        <div class="value" style="color:#1565C0;">{kpi_records}</div>
        <div class="label">已评分记录</div>
    </div>
    <div class="kpi-card" style="background:#FFF3E0;">
        <div class="value" style="color:#E65100;">40</div>
        <div class="label">学生人数</div>
    </div>
    <div class="kpi-card" style="background:#FCE4EC;">
        <div class="value" style="color:#C62828;">{len(by_type)}</div>
        <div class="label">错误类型</div>
    </div>
</div>

{chart_findings}

<div class="section">
    <h2>九指标得分率 & 班级×主题对比</h2>
    <div class="chart-grid">
        {chart_radar}
        {chart_class}
    </div>
</div>

<div class="section">
    <h2>评分点得分率 & 错误类型分布</h2>
    <div class="chart-grid">
        {chart_points}
        {chart_pie}
    </div>
</div>

<div class="section">
    <h2>学生得分率分布 & 跨节点变化</h2>
    <div class="chart-grid">
        {chart_students}
        {chart_changes}
    </div>
</div>

<div class="section">
    <h2>BKT知识追踪 - 掌握概率热力图</h2>
    {chart_mastery}
</div>

<div class="footer">
    智慧学伴智能体系统 | 数据驱动学情诊断 | 生成时间: 2026-11
</div>

</body>
</html>'''

    output_path = os.path.join(OUTPUT_DIR, 'dashboard.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  -> {output_path}")
    print(f"  文件大小: {os.path.getsize(output_path)//1024}KB")
    print(f"  用浏览器直接打开即可，不需要联网")


# ============================================================
# 主函数
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("  智慧学伴 - 模块6：学情可视化仪表盘（零依赖版）")
    print("=" * 60)
    print("  ★ 无需安装任何第三方库，直接运行 ★")

    data = load_all_data()
    print(f"  数据加载完成")

    print(f"\n  生成图表中...")
    build_dashboard(data)

    print("\n" + "=" * 60)
    print("  模块6 完成！")
    print("  用浏览器打开 dashboard.html 即可查看仪表盘")
    print("=" * 60)


if __name__ == '__main__':
    main()
