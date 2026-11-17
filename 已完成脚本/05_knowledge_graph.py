# -*- coding: utf-8 -*-
"""
智慧学伴 - 模块5：知识图谱可视化
================================
职责：用NetworkX构建知识图谱，用pyvis生成交互式HTML

安装依赖：
  pip install networkx pyvis

输入：cleaned_data.json + statistics.json（由模块1生成）
输出：
  - knowledge_graph.html（交互式知识图谱，浏览器直接打开）

运行方式：
  python 05_knowledge_graph.py
"""

import json
import os
import sys

# ============================================================
# 配置区
# ============================================================

OUTPUT_DIR = os.environ.get("SS_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
DATA_DIR = os.environ.get("SS_DATA") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "赛题材料", "赛题数据",
    "赛题资料包", "4_赛题数据", "模拟学情数据")
def check_dependencies():
    missing = []
    try:
        import networkx
    except ImportError:
        missing.append("networkx")
    try:
        from pyvis.network import Network
    except ImportError:
        missing.append("pyvis")
    if missing:
        print(f"缺少依赖，请运行: pip install {' '.join(missing)}")
        sys.exit(1)


def build_knowledge_graph(data_model, stats):
    """
    构建知识图谱
    节点类型：课标、主题、指标、题目、学习卡、教材
    边类型：包含、对应、练习、辅助
    """
    import networkx as nx
    from pyvis.network import Network

    G = nx.DiGraph()

    # 颜色配置
    COLORS = {
        'standard': '#FF6B6B',   # 课标 - 红色
        'theme': '#4ECDC4',      # 主题 - 青色
        'indicator': '#45B7D1',  # 指标 - 蓝色
        'question': '#96CEB4',   # 题目 - 绿色
        'card': '#FFEAA7',       # 学习卡 - 黄色
        'textbook': '#DDA0DD'    # 教材 - 紫色
    }

    # --- 添加节点 ---

    # 课标节点
    standards = {}
    for t_id, theme in data_model['knowledge_structure'].items():
        cr = theme['course_standard']
        if cr not in standards:
            standards[cr] = True
            G.add_node(cr, label=cr, color=COLORS['standard'], shape='box',
                       title=f'课程标准条目：{cr}', group='standard')

    # 主题节点
    for t_id, theme in data_model['knowledge_structure'].items():
        G.add_node(t_id, label=f"{t_id}\n{theme['theme_name']}",
                   color=COLORS['theme'], shape='ellipse',
                   title=f"主题目标：{theme['theme_goal']}\n教材页码：{theme.get('textbook_pages','')}",
                   group='theme')
        # 课标 → 主题
        G.add_edge(theme['course_standard'], t_id, label='包含', color='#CCCCCC')

    # 指标节点
    for t_id, theme in data_model['knowledge_structure'].items():
        for ind_id, ind in theme['indicators'].items():
            # 从stats获取得分率
            ind_stats = stats.get('by_indicator', {}).get(ind_id, {})
            rate = ind_stats.get('score_rate', 0)
            rate_str = f"{rate*100:.1f}%"

            G.add_node(ind_id, label=f"{ind_id}\n{ind['indicator_name']}\n得分率:{rate_str}",
                       color=COLORS['indicator'], shape='diamond',
                       title=f"指标：{ind['indicator_name']}\n得分率：{rate_str}\n记录数：{ind_stats.get('count', 0)}",
                       group='indicator')
            # 主题 → 指标
            G.add_edge(t_id, ind_id, label='包含', color='#CCCCCC')

    # 题目节点
    for q_id, q in data_model['question_indicator_map'].items():
        ind = q['indicator']
        # 从stats获取该题的评分点信息
        question_type = q['type']
        type_icon = {'填空题': '填', '选择题': '选', '解答题': '解'}.get(question_type, '?')

        G.add_node(q_id, label=f"{q_id}({type_icon})",
                   color=COLORS['question'], shape='dot', size=15,
                   title=f"题目：{q['question_text'][:50]}...\n题型：{question_type}\n指标：{ind}",
                   group='question')
        # 指标 → 题目
        if ind in G:
            G.add_edge(ind, q_id, label='练习', color='#AAAAAA')

    # 学习卡节点（从原始CSV读取）
    import csv
    csv_path = os.path.join(DATA_DIR, "题目与材料.csv")
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('材料类型') == '学习卡':
                card_id = row.get('材料编号', '')
                theme_id = row.get('主题编号', '')
                G.add_node(card_id, label=f"{card_id}\n学习卡",
                           color=COLORS['card'], shape='triangle',
                           title=f"学习卡内容：{row.get('题干或内容', '')[:80]}...",
                           group='card')
                if theme_id in G:
                    G.add_edge(theme_id, card_id, label='辅助', color='#CCCCCC')

            elif row.get('材料类型') == '教材':
                tb_id = row.get('材料编号', '')
                G.add_node(tb_id, label=f"{tb_id}\n教材",
                           color=COLORS['textbook'], shape='square',
                           title=f"教材内容：{row.get('题干或内容', '')}",
                           group='textbook')

    # --- 用pyvis生成交互式HTML ---
    net = Network(
        height='800px', width='100%',
        bgcolor='#FAFAFA', font_color='#333333',
        directed=True, notebook=False, cdn_resources='in_line'
    )

    # 物理布局设置
    net.set_options('''
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 100,
          "springConstant": 0.08,
          "damping": 0.4,
          "avoidOverlap": 0.5
        },
        "minVelocity": 0.75,
        "solver": "forceAtlas2Based"
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100,
        "navigationButtons": true,
        "keyboard": true
      },
      "configure": {
        "enabled": true,
        "filter": ["physics", "nodes", "edges"]
      }
    }
    ''')

    net.from_nx(G)

    # 添加图例
    legend_html = """
    <div style="position:absolute;top:10px;left:10px;background:white;padding:10px;border-radius:5px;
                box-shadow:0 2px 5px rgba(0,0,0,0.1);font-size:12px;z-index:1000;">
      <b>知识图谱图例</b><br>
      <span style="color:#FF6B6B;">■</span> 课标条目<br>
      <span style="color:#4ECDC4;">●</span> 学习主题<br>
      <span style="color:#45B7D1;">◆</span> 观察指标（含得分率）<br>
      <span style="color:#96CEB4;">●</span> 题目（填/选/解）<br>
      <span style="color:#FFEAA7;">▲</span> 学习卡<br>
      <span style="color:#DDA0DD;">■</span> 教材切片<br>
      <hr style="margin:5px 0;">
      <b>交互方式</b><br>
      鼠标悬停查看详情<br>
      拖拽节点调整位置<br>
      滚轮缩放
    </div>
    """

    output_path = os.path.join(OUTPUT_DIR, 'knowledge_graph.html')
    html = net.generate_html(notebook=False)
    html = html.replace('</body>', f'{legend_html}</body>')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"  知识图谱节点数: {G.number_of_nodes()}")
    print(f"  知识图谱边数: {G.number_of_edges()}")
    print(f"  -> {output_path}")

    return G


def main():
    print("\n" + "=" * 60)
    print("  智慧学伴 - 模块5：知识图谱可视化")
    print("=" * 60)

    check_dependencies()

    # 加载数据
    cleaned_path = os.path.join(OUTPUT_DIR, 'cleaned_data.json')
    stats_path = os.path.join(OUTPUT_DIR, 'statistics.json')
    print(f"\n加载模块1的输出数据...")
    with open(cleaned_path, 'r', encoding='utf-8') as f:
        data_model = json.load(f)
    with open(stats_path, 'r', encoding='utf-8') as f:
        stats = json.load(f)

    # 构建知识图谱
    print(f"\n构建知识图谱...")
    build_knowledge_graph(data_model, stats)

    print("\n" + "=" * 60)
    print("  模块5 完成！")
    print(f"  用浏览器打开 knowledge_graph.html 即可查看交互式图谱")
    print("=" * 60)


if __name__ == '__main__':
    main()
