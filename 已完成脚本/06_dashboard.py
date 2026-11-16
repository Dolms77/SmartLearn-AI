# -*- coding: utf-8 -*-
"""
智慧学伴 - 模块6：学情可视化仪表盘
================================
职责：生成8种交互式图表的HTML页面

安装依赖：
  pip install plotly

输入：
  - statistics.json（模块1输出）
  - mastery_matrix.json（模块2输出）
  - student_profiles.json（模块2输出）
  - error_pattern_summary.json（模块3输出）
  - cleaned_data.json（模块1输出）

输出：
  - dashboard.html（交互式学情仪表盘，浏览器直接打开）

运行方式：
  python 06_dashboard.py
"""

import json
import os
import sys
from collections import Counter, defaultdict

# ============================================================
# 配置区
# ============================================================

OUTPUT_DIR = os.environ.get("SS_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
INDICATOR_NAMES = {
    'T01I1': '表示数量关系并代入求值',
    'T01I2': '识别同类项、去括号并化简',
    'T01I3': '用整式解释具体问题',
    'T02I1': '运用等式性质解一元一次方程',
    'T02I2': '用消元法解二元一次方程组',
    'T02I3': '列方程/方程组解决实际问题',
    'T03I1': '运用不等式性质求解',
    'T03I2': '求两个不等式解集的交集',
    'T03I3': '根据实际限制列不等式'
}

INDICATORS = list(INDICATOR_NAMES.keys())


def check_dependencies():
    try:
        import plotly
    except ImportError:
        print("缺少依赖，请运行: pip install plotly")
        sys.exit(1)


def load_all_data():
    """加载所有模块的输出"""
    data = {}
    for name in ['statistics.json', 'mastery_matrix.json', 'student_profiles.json',
                 'error_pattern_summary.json', 'cleaned_data.json']:
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data[name.replace('.json', '')] = json.load(f)
        else:
            print(f"  [警告] {name} 不存在，部分图表将无法生成")
            data[name.replace('.json', '')] = {}
    return data


# ============================================================
# 图表生成函数
# ============================================================

def make_radar_chart(stats):
    """1. 九指标雷达图"""
    import plotly.graph_objects as go

    indicators = INDICATORS
    values = [stats.get('by_indicator', {}).get(ind, {}).get('score_rate', 0) * 100
              for ind in indicators]

    fig = go.Figure(data=go.Scatterpolar(
        r=values + [values[0]],
        theta=[INDICATOR_NAMES[ind] for ind in indicators] + [INDICATOR_NAMES[indicators[0]]],
        fill='toself',
        fillcolor='rgba(78, 205, 196, 0.3)',
        line=dict(color='#4ECDC4', width=2),
        name='全班得分率'
    ))

    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 100], tickfont=dict(size=10))),
        showlegend=True,
        title='九大观察指标得分率雷达图',
        height=450
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id='chart_radar')


def make_class_comparison_bar(stats):
    """2. 班级×主题对比柱状图"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    themes = ['T01', 'T02', 'T03']
    theme_names = {'T01': '代数式与整式', 'T02': '方程与方程组', 'T03': '不等式与不等式组'}

    dc01_rates = []
    dc02_rates = []
    for t in themes:
        key1 = f"DC01-{t}"
        key2 = f"DC02-{t}"
        dc01_rates.append(stats.get('by_class_theme', {}).get(key1, {}).get('score_rate', 0) * 100)
        dc02_rates.append(stats.get('by_class_theme', {}).get(key2, {}).get('score_rate', 0) * 100)

    fig = go.Figure(data=[
        go.Bar(name='DC01班', x=[theme_names[t] for t in themes], y=dc01_rates,
               marker_color='#4ECDC4', text=[f'{r:.1f}%' for r in dc01_rates], textposition='outside'),
        go.Bar(name='DC02班', x=[theme_names[t] for t in themes], y=dc02_rates,
               marker_color='#FF6B6B', text=[f'{r:.1f}%' for r in dc02_rates], textposition='outside')
    ])

    fig.update_layout(
        barmode='group',
        title='班级×主题得分率对比',
        yaxis=dict(range=[0, 100], title='得分率(%)'),
        height=400
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id='chart_class_bar')


def make_scoring_point_heatmap(stats):
    """3. 评分点热力图"""
    import plotly.graph_objects as go

    point_stats = stats.get('by_scoring_point', {})
    # 按题目分组
    question_points = defaultdict(list)
    for pid, info in point_stats.items():
        qid = pid[:4]  # 提取题目编号
        question_points[qid].append((pid, info['score_rate'] * 100))

    # 排序
    sorted_questions = sorted(question_points.keys())
    all_pids = []
    all_rates = []
    all_labels = []
    for qid in sorted_questions:
        for pid, rate in sorted(question_points[qid]):
            all_pids.append(pid)
            all_rates.append(rate)
            all_labels.append(f"{rate:.0f}%")

    # 颜色映射：红色=低，黄色=中，绿色=高
    colors = ['#FF4444' if r < 30 else '#FFAA00' if r < 50 else '#44AA44' for r in all_rates]

    fig = go.Figure(data=go.Bar(
        x=all_pids,
        y=all_rates,
        marker_color=colors,
        text=all_labels,
        textposition='outside'
    ))

    fig.update_layout(
        title='评分点得分率热力图（红色=重点关注）',
        xaxis=dict(title='评分点编号', tickangle=45),
        yaxis=dict(range=[0, 110], title='得分率(%)'),
        height=500
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id='chart_heatmap')


def make_student_distribution(stats):
    """4. 学生得分率分布图"""
    import plotly.graph_objects as go

    students = stats.get('by_student', {})
    sorted_students = sorted(students.items(), key=lambda x: x[1]['score_rate'])

    sids = [s[0] for s in sorted_students]
    rates = [s[1]['score_rate'] * 100 for s in sorted_students]
    classes = [s[1]['class'] for s in sorted_students]
    colors = ['#4ECDC4' if c == 'DC01' else '#FF6B6B' for c in classes]

    fig = go.Figure(data=go.Bar(
        x=sids, y=rates,
        marker_color=colors,
        text=[f'{r:.0f}%' for r in rates],
        textposition='outside'
    ))

    fig.update_layout(
        title='学生得分率分布（按得分率排序）',
        xaxis=dict(title='学生编号', tickangle=45),
        yaxis=dict(range=[0, 110], title='得分率(%)'),
        height=450,
        showlegend=False
    )

    # 添加图例注释
    fig.add_annotation(x=0.01, y=0.95, xref='paper', yref='paper',
                       text='<span style="color:#4ECDC4;">■</span> DC01班  <span style="color:#FF6B6B;">■</span> DC02班',
                       showarrow=False, font=dict(size=12))

    return fig.to_html(full_html=False, include_plotlyjs=False, div_id='chart_student_dist')


def make_mastery_heatmap(mastery_matrix):
    """5. 知识追踪掌握概率热力图"""
    import plotly.graph_objects as go

    if not mastery_matrix:
        return "<div>无数据</div>"

    sids = sorted(mastery_matrix.keys(),
                  key=lambda s: sum(mastery_matrix[s].values()) / len(mastery_matrix[s]))

    z = []
    for sid in sids:
        row = [mastery_matrix[sid].get(ind, 0) * 100 for ind in INDICATORS]
        z.append(row)

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=INDICATORS,
        y=sids,
        colorscale=[
            [0, '#FF4444'],     # 0% - 红
            [0.4, '#FFAA00'],   # 40% - 黄
            [0.7, '#44AA44'],   # 70% - 绿
            [1, '#006600']      # 100% - 深绿
        ],
        text=[[f'{v:.0f}%' for v in row] for row in z],
        texttemplate='%{text}',
        textfont={"size": 8},
        colorbar=dict(title='掌握<br>概率')
    ))

    fig.update_layout(
        title='学生×指标 掌握概率热力图（BKT模型）',
        xaxis=dict(title='观察指标', tickangle=45),
        yaxis=dict(title='学生编号'),
        height=700
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id='chart_mastery')


def make_error_type_pie(error_summary):
    """6. 错误类型分布饼图"""
    import plotly.graph_objects as go

    by_type = error_summary.get('by_error_type', {})
    if not by_type:
        return "<div>无数据</div>"

    type_names_cn = {
        'C1': '概念误解', 'C2': '符号错误', 'C3': '计算失误',
        'C4': '步骤遗漏', 'C5': '表达不规范', 'C6': '级联错误'
    }

    labels = [f"{code}({type_names_cn.get(code, code)})" for code in by_type.keys()]
    values = [info['count'] for info in by_type.values()]
    colors = ['#FF6B6B', '#FF9F43', '#FECA57', '#48DBFB', '#A29BFE', '#54A0FF']

    fig = go.Figure(data=go.Pie(
        labels=labels, values=values,
        hole=0.4,
        marker=dict(colors=colors),
        textinfo='label+percent'
    ))

    fig.update_layout(
        title='错误类型分布',
        height=400
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id='chart_error_pie')


def make_cross_node_chart(stats):
    """7. 跨节点变化图"""
    import plotly.graph_objects as go

    changes = stats.get('cross_node_changes', [])
    if not changes:
        return "<div>无数据</div>"

    type_names = {
        'improved': '进步',
        'regressed': '退步',
        'persistent_error': '顽固性错误',
        'still_wrong': '仍错(答案变了)',
        'both_correct': '都对'
    }

    type_counter = Counter(c['change_type'] for c in changes)

    fig = go.Figure(data=go.Bar(
        x=[type_names.get(k, k) for k in type_counter.keys()],
        y=list(type_counter.values()),
        marker_color=['#2ECC71', '#E74C3C', '#E67E22', '#F39C12', '#3498DB'],
        text=list(type_counter.values()),
        textposition='outside'
    ))

    fig.update_layout(
        title='跨节点(N01→N02)学习变化分析',
        xaxis=dict(title='变化类型'),
        yaxis=dict(title='记录数'),
        height=350
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id='chart_cross_node')


def make_critical_findings(error_summary):
    """8. 关键发现列表（HTML卡片）"""
    findings = error_summary.get('critical_findings', [])
    if not findings:
        return "<div>无关键发现</div>"

    severity_colors = {
        'critical': '#FF4444',
        'high': '#FF8800',
        'medium': '#FFAA00'
    }
    severity_labels = {
        'critical': '严重',
        'high': '高',
        'medium': '中'
    }

    cards = []
    for f in findings:
        color = severity_colors.get(f.get('severity', 'medium'), '#999')
        label = severity_labels.get(f.get('severity', 'medium'), '?')
        cards.append(f"""
        <div style="border-left:4px solid {color};background:#FAFAFA;padding:10px;margin:5px 0;border-radius:3px;">
            <span style="color:{color};font-weight:bold;">[{label}]</span>
            {f.get('description', '')}
        </div>
        """)

    return f"""
    <div style="margin:10px 0;">
        <h3>关键发现（自动识别）</h3>
        {''.join(cards)}
    </div>
    """


# ============================================================
# 组装仪表盘HTML
# ============================================================

def build_dashboard(data):
    """组装完整的仪表盘页面"""
    stats = data.get('statistics', {})
    mastery = data.get('mastery_matrix', {})
    error_summary = data.get('error_pattern_summary', {})

    # 生成各图表
    radar_html = make_radar_chart(stats)
    class_bar_html = make_class_comparison_bar(stats)
    heatmap_html = make_scoring_point_heatmap(stats)
    student_dist_html = make_student_distribution(stats)
    mastery_html = make_mastery_heatmap(mastery)
    error_pie_html = make_error_type_pie(error_summary)
    cross_node_html = make_cross_node_chart(stats)
    findings_html = make_critical_findings(error_summary)

    # 总体KPI
    overall = stats.get('overall', {})

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智慧学伴 - 学情诊断仪表盘</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Microsoft YaHei', sans-serif; background: #F5F5F5; color: #333; }}
        .header {{
            background: linear-gradient(135deg, #4ECDC4 0%, #45B7D1 100%);
            color: white; padding: 20px 30px; text-align: center;
        }}
        .header h1 {{ font-size: 24px; margin-bottom: 5px; }}
        .header p {{ font-size: 13px; opacity: 0.9; }}
        .kpi-row {{
            display: flex; justify-content: center; gap: 20px;
            padding: 20px; background: white; margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .kpi-card {{
            text-align: center; padding: 15px 25px;
            border-radius: 8px; min-width: 150px;
        }}
        .kpi-card .value {{ font-size: 28px; font-weight: bold; }}
        .kpi-card .label {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .section {{
            background: white; margin: 10px; padding: 20px;
            border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            font-size: 16px; color: #45B7D1;
            border-bottom: 2px solid #E0E0E0; padding-bottom: 8px; margin-bottom: 15px;
        }}
        .chart-grid {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 15px;
        }}
        .chart-grid > div {{ }}
        .footer {{
            text-align: center; padding: 20px; color: #999; font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>智慧学伴 · 学情诊断仪表盘</h1>
        <p>七年级数学 | 3主题 9指标 54题 40学生 790条记录</p>
    </div>

    <div class="kpi-row">
        <div class="kpi-card" style="background:#E8F5E9;">
            <div class="value" style="color:#2E7D32;">{overall.get('score_rate_percent','?')}</div>
            <div class="label">总体得分率</div>
        </div>
        <div class="kpi-card" style="background:#E3F2FD;">
            <div class="value" style="color:#1565C0;">{overall.get('total_records','?')}</div>
            <div class="label">已评分记录</div>
        </div>
        <div class="kpi-card" style="background:#FFF3E0;">
            <div class="value" style="color:#E65100;">40</div>
            <div class="label">学生人数</div>
        </div>
        <div class="kpi-card" style="background:#FCE4EC;">
            <div class="value" style="color:#C62828;">{len(error_summary.get('by_error_type',{}))}</div>
            <div class="label">错误类型</div>
        </div>
    </div>

    {findings_html}

    <div class="section">
        <h2>九指标得分率雷达图 & 班级×主题对比</h2>
        <div class="chart-grid">
            <div>{radar_html}</div>
            <div>{class_bar_html}</div>
        </div>
    </div>

    <div class="section">
        <h2>评分点得分率 & 错误类型分布</h2>
        <div class="chart-grid">
            <div>{heatmap_html}</div>
            <div>{error_pie_html}</div>
        </div>
    </div>

    <div class="section">
        <h2>学生得分率分布 & 跨节点变化</h2>
        <div class="chart-grid">
            <div>{student_dist_html}</div>
            <div>{cross_node_html}</div>
        </div>
    </div>

    <div class="section">
        <h2>BKT知识追踪 - 掌握概率热力图</h2>
        {mastery_html}
    </div>

    <div class="footer">
        智慧学伴智能体系统 | 数据驱动学情诊断 | 生成时间: 2026-11
    </div>
</body>
</html>"""

    output_path = os.path.join(OUTPUT_DIR, 'dashboard.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  -> {output_path}")


def main():
    print("\n" + "=" * 60)
    print("  智慧学伴 - 模块6：学情可视化仪表盘")
    print("=" * 60)

    check_dependencies()
    data = load_all_data()
    print(f"  数据加载完成")

    print(f"\n  生成图表中...")
    build_dashboard(data)

    print("\n" + "=" * 60)
    print("  模块6 完成！")
    print(f"  用浏览器打开 dashboard.html 即可查看仪表盘")
    print("=" * 60)


if __name__ == '__main__':
    main()
