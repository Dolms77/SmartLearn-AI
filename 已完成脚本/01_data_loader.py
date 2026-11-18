# -*- coding: utf-8 -*-
"""
智慧学伴 - 模块1：数据加载与清洗
================================
职责：读取6张CSV表，建立关联关系，清洗异常数据，输出结构化JSON

输入：6张CSV文件（课程要求、题目与材料、模拟学生、测验节点、作答记录、字段说明）
输出：
  - cleaned_data.json    清洗后的全量数据（供模块2和模块3使用）
  - data_quality_report.json  数据质量报告
  - statistics.json      多维度统计结果

运行方式：
  python 01_data_loader.py
"""

import csv
import json
import os
import re
from collections import defaultdict, Counter
from datetime import datetime

# ============================================================
# 第一部分：配置区（你需要改的地方只有这里）
# ============================================================

# CSV文件所在目录（把6个CSV放同一个文件夹，改这里）
DATA_DIR = os.environ.get("SS_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "赛题材料", "赛题数据", "赛题资料包", "4_赛题数据", "模拟学情数据")
# 输出目录
OUTPUT_DIR = os.environ.get("SS_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHANGE_TYPE_LABELS = {
    'regressed': '后续节点退步',
    'improved': '后续节点进步',
    'persistent_error': '同题持续答错（最终答案相同）',
    'still_wrong': '后续仍答错（最终答案变化）',
    'both_correct': '两个节点均答对'
}


def parse_scoring_point_definitions(value):
    """Parse rubric point IDs, descriptions, and maximum scores."""
    definitions = {}
    for item in re.split(r'[；;\r\n]+', value or ''):
        match = re.fullmatch(r'\s*([A-Z]\d+P\d+)\s+(.+?)\s+(\d+)分\s*', item)
        if match:
            point_id, description, full_score = match.groups()
            definitions[point_id] = {
                'description': description.strip(),
                'full_score': int(full_score)
            }
    return definitions


def parse_scoring_point_details(score_value, definition_value):
    """Return structured score-point results while preserving the original text."""
    definitions = parse_scoring_point_definitions(definition_value)
    details = []
    for item in re.split(r'[；;\r\n]+', score_value or ''):
        match = re.fullmatch(r'\s*([A-Z]\d+P\d+)\s*=\s*(-?\d+)\s*', item)
        if not match:
            continue
        point_id, score = match.groups()
        definition = definitions.get(point_id, {})
        details.append({
            'scoring_point_id': point_id,
            'description': definition.get('description', ''),
            'score': int(score),
            'full_score': definition.get('full_score')
        })
    return details


# ============================================================
# 第二部分：数据加载
# ============================================================

def load_csv(filename):
    """读取CSV文件，返回字典列表"""
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_all_data():
    """加载全部6张表"""
    print("=" * 50)
    print("步骤1：加载数据文件")
    print("=" * 50)

    data = {}
    data['course_requirements'] = load_csv('课程要求.csv')
    data['questions'] = load_csv('题目与材料.csv')
    data['students'] = load_csv('模拟学生.csv')
    data['test_nodes'] = load_csv('测验节点.csv')
    data['records'] = load_csv('作答记录.csv')
    # 字段说明只是参考文档，不参与计算

    # 打印加载概况
    print(f"  课程要求: {len(data['course_requirements'])} 条")
    print(f"  题目与材料: {len(data['questions'])} 条")
    print(f"  模拟学生: {len(data['students'])} 条")
    print(f"  测验节点: {len(data['test_nodes'])} 条")
    print(f"  作答记录: {len(data['records'])} 条")

    return data


def audit_source_quality(records, questions, test_nodes):
    """Audit the original CSV rows without rewriting their submitted values."""
    question_map = {q.get('材料编号', ''): q for q in questions}
    node_scope = {
        node.get('节点编号', ''): set(
            item.strip() for item in (node.get('可用题目编号') or '').split('、') if item.strip()
        )
        for node in test_nodes
    }
    checks = []
    flags_by_record = defaultdict(list)

    def add_check(rule_id, name, matched_records, disposition, evaluated=True):
        record_ids = [r.get('记录编号', '') for r in matched_records if r.get('记录编号')]
        checks.append({
            'rule_id': rule_id,
            'name': name,
            'evaluated': evaluated,
            'hit_count': len(record_ids),
            'record_ids': record_ids,
            'disposition': disposition
        })
        for record_id in record_ids:
            flags_by_record[record_id].append(rule_id)

    def integer_value(record, field):
        value = record.get(field, '')
        try:
            return int(value) if value != '' else None
        except (TypeError, ValueError):
            return None

    over_scored = []
    point_mismatches = []
    pending = []
    unanswered = []
    node_scope_mismatches = []
    theme_mismatches = []
    answer_score_conflicts = []
    event_groups = defaultdict(list)

    for record in records:
        event_groups[(record.get('作答事件编号') or '').strip()].append(record)
        score = integer_value(record, '得分')
        full_score = integer_value(record, '满分')
        status = record.get('评分状态', '').strip()
        point_scores = record.get('评分点得分', '')
        question = question_map.get(record.get('材料编号', ''), {})

        if score is not None and full_score is not None and score > full_score:
            over_scored.append(record)

        if status == '已评分' and score is not None and point_scores:
            point_sum = sum(int(value) for value in re.findall(r'=(\d+)', point_scores))
            if point_sum != score:
                point_mismatches.append(record)
        if status == '待评分':
            pending.append(record)
        if status == '未作答':
            unanswered.append(record)

        node_id = record.get('节点编号', '')
        if test_nodes and record.get('材料编号', '') not in node_scope.get(node_id, set()):
            node_scope_mismatches.append(record)
        if record.get('主题编号', '') != question.get('主题编号', ''):
            theme_mismatches.append(record)

        if (question.get('题型') == '填空题' and status == '已评分' and score == 0):
            def normalize_answer(value):
                return re.sub(r'^(x|y|a|n)=|[\s，,。；;]', '', str(value or ''))

            answer = normalize_answer(record.get('学生最终作答', ''))
            reference = normalize_answer(question.get('参考答案', ''))
            if answer and answer == reference:
                answer_score_conflicts.append(record)

    duplicate_records = []
    for versions in event_groups.values():
        if len(versions) > 1:
            duplicate_records.extend(versions)

    add_check(
        'R1', '得分超过满分', over_scored,
        '保留原始得分并标记；未自动截断或重算，复核前相关统计含原始录入值。'
    )
    add_check(
        'R2', '评分点得分之和与总分不一致', point_mismatches,
        '保留原始总分及评分点并标记；未自动按评分点重算。'
    )
    add_check(
        'R3', '同一作答事件存在多个版本', duplicate_records,
        '统计仅纳入最新的已评分版本；其他版本按状态隔离，全部记录编号保留在此报告。'
    )
    add_check(
        'R4', '评分状态为待评分', pending,
        '不纳入已评分统计，记录编号及事件信息单独保留。'
    )
    add_check(
        'R5', '评分状态为未作答', unanswered,
        '不作为答错或掌握度证据，单独统计。'
    )
    add_check(
        'R6', '题目不在对应测验节点范围内', node_scope_mismatches,
        '仅标记节点口径异常，不自动改节点或删除记录。',
        evaluated=bool(test_nodes)
    )
    add_check(
        'R7', '记录主题与题目主题不一致', theme_mismatches,
        '保留原始主题并标记；未自动按题目表修正。'
    )
    add_check(
        'R8', '填空题答案与参考答案一致但得分为零', answer_score_conflicts,
        '保留原始评分并标记为待复核；不自动改分。'
    )

    revision_groups = []
    for event_id, versions in event_groups.items():
        if len(versions) > 1:
            ordered = sorted(versions, key=lambda row: int(row.get('修订版本') or 1))
            revision_groups.append({
                'event_id': event_id,
                'record_ids': [row.get('记录编号', '') for row in ordered],
                'latest_revision_record_id': ordered[-1].get('记录编号', ''),
                'latest_revision_status': ordered[-1].get('评分状态', '')
            })

    for record_id in flags_by_record:
        flags_by_record[record_id].sort()

    return {
        'total_records': len(records),
        'rule_count': len(checks),
        'checks': checks,
        'revision_event_groups': revision_groups
    }, dict(flags_by_record)


# ============================================================
# 第三部分：数据清洗
# ============================================================

def clean_records(records, questions, students):
    """
    清洗作答记录，返回：
    - cleaned_records: 清洗后的有效记录
    - quality_report: 数据质量报告
    """
    print("\n" + "=" * 50)
    print("步骤2：数据清洗")
    print("=" * 50)

    quality_report = {
        'total_records': len(records),
        'issues': [],
        'processing_summary': {}
    }

    # --- 2.1 分类记录 ---
    scored = []
    pending = []
    unanswered = []

    for r in records:
        status = r.get('评分状态', '').strip()
        if status == '已评分':
            scored.append(r)
        elif status == '待评分':
            pending.append(r)
        elif status == '未作答':
            unanswered.append(r)
        else:
            quality_report['issues'].append({
                'type': '未知评分状态',
                'record_id': r.get('记录编号'),
                'status': status
            })

    print(f"  已评分: {len(scored)} 条")
    print(f"  待评分: {len(pending)} 条（标注保留，不计入统计）")
    print(f"  未作答: {len(unanswered)} 条（排除但不删除）")

    quality_report['processing_summary']['scored'] = len(scored)
    quality_report['processing_summary']['pending'] = len(pending)
    quality_report['processing_summary']['unanswered'] = len(unanswered)

    # --- 2.2 处理修订版本 > 1 的记录 ---
    # 同一作答事件（学生+节点+题目）取最新版本
    event_groups = defaultdict(list)
    for r in scored:
        event_id = r.get('作答事件编号', '')
        event_groups[event_id].append(r)

    cleaned_scored = []
    revised_events = []

    for event_id, versions in event_groups.items():
        # 按修订版本号排序，取最新
        versions.sort(key=lambda x: int(x.get('修订版本', '1')))
        latest = versions[-1]
        cleaned_scored.append(latest)

        if len(versions) > 1:
            revised_events.append({
                'event_id': event_id,
                'versions': len(versions),
                'student_id': latest.get('学生编号'),
                'question_id': latest.get('材料编号'),
                'node_id': latest.get('节点编号'),
                'final_score': latest.get('得分'),
                'final_full': latest.get('满分'),
                'note': '取最新版本，旧版本保留用于过程分析'
            })

    print(f"  修订记录: {len(revised_events)} 条（取最新版本）")
    print(f"  去重后已评分记录: {len(cleaned_scored)} 条")

    quality_report['processing_summary']['revised_events'] = len(revised_events)
    quality_report['processing_summary']['deduplicated_scored'] = len(cleaned_scored)
    quality_report['revised_events_detail'] = revised_events

    # --- 2.3 检查记录量不足的学生 ---
    student_record_counts = Counter(r.get('学生编号') for r in cleaned_scored)
    insufficient_students = []

    for sid, count in student_record_counts.items():
        if count < 8:  # 少于8条记录视为样本不足
            insufficient_students.append({
                'student_id': sid,
                'record_count': count,
                'note': '样本不足，分析结论置信度较低，不直接判定掌握情况'
            })

    print(f"  样本不足学生（<8条）: {len(insufficient_students)} 人")

    quality_report['processing_summary']['insufficient_students'] = len(insufficient_students)
    quality_report['insufficient_students_detail'] = insufficient_students
    process_recorded = sum(1 for r in cleaned_scored if r.get('解答过程', '').strip())
    quality_report['process_coverage'] = {
        'scored_record_count': len(cleaned_scored),
        'recorded_count': process_recorded,
        'not_recorded_count': len(cleaned_scored) - process_recorded,
        'coverage_rate': round(process_recorded / len(cleaned_scored), 4) if cleaned_scored else 0,
        'note': '未记录表示源数据没有提供文字过程，不代表学生没有解题步骤。'
    }

    # --- 2.4 标注待评分和未作答记录详情 ---
    quality_report['pending_records'] = [
        {
            'record_id': r.get('记录编号'),
            'student_id': r.get('学生编号'),
            'question_id': r.get('材料编号'),
            'node_id': r.get('节点编号'),
            'note': '待评分，暂不计入统计，保留记录'
        }
        for r in pending
    ]

    quality_report['unanswered_records'] = [
        {
            'record_id': r.get('记录编号'),
            'student_id': r.get('学生编号'),
            'question_id': r.get('材料编号'),
            'node_id': r.get('节点编号'),
            'note': '未作答，不判定掌握情况'
        }
        for r in unanswered
    ]

    return cleaned_scored, pending, unanswered, quality_report


# ============================================================
# 第四部分：多维度统计分析
# ============================================================

def compute_statistics(scored_records, questions, students):
    """
    计算多维度统计，返回statistics字典
    维度：总体 → 主题 → 指标 → 评分点 → 学生 → 班级×主题
    """
    print("\n" + "=" * 50)
    print("步骤3：多维度统计分析")
    print("=" * 50)

    # 建立查找表
    question_map = {q['材料编号']: q for q in questions}
    student_map = {s['学生编号']: s for s in students}

    stats = {}

    # --- 3.1 总体统计 ---
    total_score = sum(int(r['得分']) for r in scored_records if r.get('得分'))
    total_full = sum(int(r['满分']) for r in scored_records if r.get('满分'))
    overall_rate = total_score / total_full if total_full > 0 else 0

    stats['overall'] = {
        'total_records': len(scored_records),
        'total_score': total_score,
        'total_full': total_full,
        'score_rate': round(overall_rate, 4),
        'score_rate_percent': f"{overall_rate*100:.2f}%"
    }
    print(f"  总体得分率: {overall_rate*100:.2f}% ({total_score}/{total_full})")

    # --- 3.2 主题级别统计 ---
    theme_stats = defaultdict(lambda: {'score': 0, 'full': 0, 'count': 0})
    for r in scored_records:
        t = r.get('主题编号', '')
        theme_stats[t]['score'] += int(r['得分']) if r.get('得分') else 0
        theme_stats[t]['full'] += int(r['满分']) if r.get('满分') else 0
        theme_stats[t]['count'] += 1

    stats['by_theme'] = {}
    for t in sorted(theme_stats.keys()):
        info = theme_stats[t]
        rate = info['score'] / info['full'] if info['full'] > 0 else 0
        stats['by_theme'][t] = {
            'count': info['count'],
            'score': info['score'],
            'full': info['full'],
            'score_rate': round(rate, 4),
            'score_rate_percent': f"{rate*100:.1f}%"
        }
        print(f"  {t}: {rate*100:.1f}% ({info['count']}条)")

    # --- 3.3 指标级别统计 ---
    indicator_stats = defaultdict(lambda: {'score': 0, 'full': 0, 'count': 0})
    for r in scored_records:
        q_info = question_map.get(r.get('材料编号', ''), {})
        ind = q_info.get('指标编号', '')
        if ind:
            indicator_stats[ind]['score'] += int(r['得分']) if r.get('得分') else 0
            indicator_stats[ind]['full'] += int(r['满分']) if r.get('满分') else 0
            indicator_stats[ind]['count'] += 1

    stats['by_indicator'] = {}
    for ind in sorted(indicator_stats.keys()):
        info = indicator_stats[ind]
        rate = info['score'] / info['full'] if info['full'] > 0 else 0
        stats['by_indicator'][ind] = {
            'count': info['count'],
            'score': info['score'],
            'full': info['full'],
            'score_rate': round(rate, 4),
            'score_rate_percent': f"{rate*100:.1f}%"
        }
        print(f"  {ind}: {rate*100:.1f}% ({info['count']}条)")

    # --- 3.4 评分点级别统计（核心差异化） ---
    point_stats = defaultdict(lambda: {'total': 0, 'correct': 0})
    for r in scored_records:
        point_str = r.get('评分点得分', '')
        if point_str:
            points = point_str.split('；')
            for p in points:
                p = p.strip()
                if '=' in p:
                    parts = p.split('=')
                    pid = parts[0].strip()
                    score = int(parts[1].strip())
                    point_stats[pid]['total'] += 1
                    if score == 1:
                        point_stats[pid]['correct'] += 1

    stats['by_scoring_point'] = {}
    print("\n  评分点统计（得分率低于30%的重点标注）:")
    for pid in sorted(point_stats.keys()):
        info = point_stats[pid]
        rate = info['correct'] / info['total'] if info['total'] > 0 else 0
        flag = ' *** 重点关注 ***' if rate < 0.3 else ''
        stats['by_scoring_point'][pid] = {
            'total': info['total'],
            'correct': info['correct'],
            'score_rate': round(rate, 4),
            'score_rate_percent': f"{rate*100:.1f}%",
            'flag': 'critical' if rate < 0.3 else ('weak' if rate < 0.5 else 'normal')
        }
        if rate < 0.5:
            print(f"    {pid}: {rate*100:.1f}% ({info['correct']}/{info['total']}){flag}")

    # --- 3.5 学生级别统计 ---
    student_stats = defaultdict(lambda: {
        'score': 0, 'full': 0, 'count': 0,
        'themes': defaultdict(lambda: {'score': 0, 'full': 0, 'count': 0}),
        'indicators': defaultdict(lambda: {'score': 0, 'full': 0, 'count': 0})
    })

    for r in scored_records:
        sid = r.get('学生编号', '')
        student_stats[sid]['score'] += int(r['得分']) if r.get('得分') else 0
        student_stats[sid]['full'] += int(r['满分']) if r.get('满分') else 0
        student_stats[sid]['count'] += 1

        t = r.get('主题编号', '')
        student_stats[sid]['themes'][t]['score'] += int(r['得分']) if r.get('得分') else 0
        student_stats[sid]['themes'][t]['full'] += int(r['满分']) if r.get('满分') else 0
        student_stats[sid]['themes'][t]['count'] += 1

        q_info = question_map.get(r.get('材料编号', ''), {})
        ind = q_info.get('指标编号', '')
        if ind:
            student_stats[sid]['indicators'][ind]['score'] += int(r['得分']) if r.get('得分') else 0
            student_stats[sid]['indicators'][ind]['full'] += int(r['满分']) if r.get('满分') else 0
            student_stats[sid]['indicators'][ind]['count'] += 1

    stats['by_student'] = {}
    for sid in sorted(student_stats.keys()):
        info = student_stats[sid]
        rate = info['score'] / info['full'] if info['full'] > 0 else 0
        cls = student_map.get(sid, {}).get('模拟班级编号', '?')

        # 找最薄弱指标
        weak_indicators = []
        for ind, idata in info['indicators'].items():
            if idata['full'] > 0:
                irate = idata['score'] / idata['full']
                weak_indicators.append({
                    'indicator': ind,
                    'score_rate': round(irate, 4),
                    'count': idata['count']
                })
        weak_indicators.sort(key=lambda x: x['score_rate'])

        # 主题得分率
        theme_rates = {}
        for t, tdata in info['themes'].items():
            if tdata['full'] > 0:
                theme_rates[t] = round(tdata['score'] / tdata['full'], 4)

        stats['by_student'][sid] = {
            'class': cls,
            'count': info['count'],
            'score': info['score'],
            'full': info['full'],
            'score_rate': round(rate, 4),
            'score_rate_percent': f"{rate*100:.2f}%",
            'theme_rates': theme_rates,
            'weakest_indicators': weak_indicators[:3],
            'level': 'high' if rate >= 0.7 else ('medium' if rate >= 0.4 else 'low')
        }

    # --- 3.6 班级×主题统计 ---
    class_theme_stats = defaultdict(lambda: {'score': 0, 'full': 0, 'count': 0})
    for r in scored_records:
        sid = r.get('学生编号', '')
        cls = student_map.get(sid, {}).get('模拟班级编号', '?')
        t = r.get('主题编号', '')
        key = f"{cls}-{t}"
        class_theme_stats[key]['score'] += int(r['得分']) if r.get('得分') else 0
        class_theme_stats[key]['full'] += int(r['满分']) if r.get('满分') else 0
        class_theme_stats[key]['count'] += 1

    stats['by_class_theme'] = {}
    for key in sorted(class_theme_stats.keys()):
        info = class_theme_stats[key]
        rate = info['score'] / info['full'] if info['full'] > 0 else 0
        stats['by_class_theme'][key] = {
            'count': info['count'],
            'score_rate': round(rate, 4),
            'score_rate_percent': f"{rate*100:.1f}%"
        }

    # --- 3.7 班级×题目及班级×评分点统计 ---
    class_question_stats = defaultdict(
        lambda: defaultdict(lambda: {'score': 0, 'full': 0, 'count': 0})
    )
    class_point_stats = defaultdict(
        lambda: defaultdict(lambda: {'score': 0, 'full': 0, 'count': 0})
    )
    for r in scored_records:
        sid = r.get('学生编号', '')
        class_id = student_map.get(sid, {}).get('模拟班级编号', '?')
        question_id = r.get('材料编号', '')
        question = question_map.get(question_id, {})
        question_stats = class_question_stats[class_id][question_id]
        question_stats['score'] += int(r['得分']) if r.get('得分') else 0
        question_stats['full'] += int(r['满分']) if r.get('满分') else 0
        question_stats['count'] += 1

        for point in parse_scoring_point_details(
                r.get('评分点得分', ''), question.get('评分点', '')):
            point_stats_for_class = class_point_stats[class_id][point['scoring_point_id']]
            point_stats_for_class['score'] += point['score']
            point_stats_for_class['full'] += point['full_score'] or 0
            point_stats_for_class['count'] += 1

    stats['by_class_question'] = {}
    for class_id, questions_for_class in sorted(class_question_stats.items()):
        stats['by_class_question'][class_id] = {}
        for question_id, info in sorted(questions_for_class.items()):
            rate = info['score'] / info['full'] if info['full'] > 0 else 0
            stats['by_class_question'][class_id][question_id] = {
                'count': info['count'],
                'score': info['score'],
                'full': info['full'],
                'score_rate': round(rate, 4),
                'score_rate_percent': f"{rate*100:.1f}%"
            }

    stats['by_class_scoring_point'] = {}
    for class_id, points_for_class in sorted(class_point_stats.items()):
        stats['by_class_scoring_point'][class_id] = {}
        for point_id, info in sorted(points_for_class.items()):
            rate = info['score'] / info['full'] if info['full'] > 0 else 0
            stats['by_class_scoring_point'][class_id][point_id] = {
                'count': info['count'],
                'score': info['score'],
                'full': info['full'],
                'score_rate': round(rate, 4),
                'score_rate_percent': f"{rate*100:.1f}%"
            }

    # --- 3.8 跨节点变化统计 ---
    # 同一学生同一题目在N01和N02都有记录的情况
    cross_node = defaultdict(dict)
    for r in scored_records:
        sid = r.get('学生编号', '')
        qid = r.get('材料编号', '')
        node = r.get('节点编号', '')
        event_key = f"{sid}-{qid}"
        cross_node[event_key][node] = {
            'score': int(r['得分']) if r.get('得分') else 0,
            'full': int(r['满分']) if r.get('满分') else 0,
            'answer': r.get('学生最终作答', '')
        }

    progress_records = []
    for event_key, nodes in cross_node.items():
        if 'N01' in nodes and 'N02' in nodes:
            n01 = nodes['N01']
            n02 = nodes['N02']
            n01_correct = n01['score'] == n01['full']
            n02_correct = n02['score'] == n02['full']

            if n01_correct and not n02_correct:
                change_type = 'regressed'  # 退步
            elif not n01_correct and n02_correct:
                change_type = 'improved'   # 进步
            elif not n01_correct and not n02_correct:
                # 检查是否顽固性错误（答案相同）
                if n01['answer'] == n02['answer'] and n01['answer']:
                    change_type = 'persistent_error'  # 顽固性错误
                else:
                    change_type = 'still_wrong'  # 仍然错误但答案变了
            else:
                change_type = 'both_correct'  # 都对

            progress_records.append({
                'student_id': event_key.split('-')[0],
                'question_id': event_key.split('-')[1],
                'N01': n01,
                'N02': n02,
                'change_type': change_type,
                'change_type_label': CHANGE_TYPE_LABELS[change_type]
            })

    stats['cross_node_changes'] = progress_records
    print(f"\n  跨节点变化记录: {len(progress_records)} 条")
    change_counter = Counter(r['change_type'] for r in progress_records)
    for ct, count in change_counter.most_common():
        print(f"    {ct}: {count} 条")

    return stats


# ============================================================
# 第五部分：构建关联数据模型（供BKT和错因诊断使用）
# ============================================================

def build_data_model(scored_records, questions, students, course_reqs, test_nodes,
                     quality_flags_by_record=None):
    """
    构建关联数据模型，输出cleaned_data.json
    这个文件是模块2（BKT）和模块3（错因诊断）的输入
    """
    print("\n" + "=" * 50)
    print("步骤4：构建关联数据模型")
    print("=" * 50)

    # 建立查找表
    question_map = {q['材料编号']: q for q in questions}
    student_map = {s['学生编号']: s for s in students}

    # 构建知识结构
    knowledge_structure = {}
    for source_row, cr in enumerate(course_reqs, start=2):
        t_id = cr.get('主题编号', '')
        ind_id = cr.get('指标编号', '')
        if t_id not in knowledge_structure:
            knowledge_structure[t_id] = {
                'theme_name': cr.get('主题', ''),
                'theme_goal': cr.get('主题目标', ''),
                'course_standard': cr.get('课标整理编号', ''),
                'textbook_pages': cr.get('教材正文页', ''),
                'source_file': '课程要求.csv',
                'source_rows': [],
                'indicators': {}
            }
        knowledge_structure[t_id]['source_rows'].append(source_row)
        knowledge_structure[t_id]['indicators'][ind_id] = {
            'indicator_name': cr.get('观察指标', ''),
            'course_standard_ref': cr.get('课标文件页／正文页', ''),
            'source_file': '课程要求.csv',
            'source_row': source_row
        }

    # 构建题目→指标映射
    question_indicator_map = {}
    for source_row, q in enumerate(questions, start=2):
        if q.get('材料类型') == '题目':
            question_indicator_map[q['材料编号']] = {
                'indicator': q.get('指标编号', ''),
                'theme': q.get('主题编号', ''),
                'type': q.get('题型', ''),
                'question_text': q.get('题干或内容', ''),
                'options': q.get('选项', ''),
                'reference_answer': q.get('参考答案', ''),
                'reference_solution': q.get('参考解析', ''),
                'full_score': int(q.get('满分', 0)) if q.get('满分') else 0,
                'scoring_points': q.get('评分点', ''),
                'scoring_point_definitions': parse_scoring_point_definitions(
                    q.get('评分点', '')
                ),
                'source': q.get('来源或资料文件', ''),
                'source_file': '题目与材料.csv',
                'source_row': source_row
            }

    # 构建结构化作答记录（供BKT和错因诊断使用）
    structured_records = []
    for r in scored_records:
        qid = r.get('材料编号', '')
        q_info = question_map.get(qid, {})

        record = {
            'record_id': r.get('记录编号', ''),
            'student_id': r.get('学生编号', ''),
            'class_id': student_map.get(r.get('学生编号', ''), {}).get('模拟班级编号', ''),
            'question_id': qid,
            'theme_id': r.get('主题编号', ''),
            'indicator_id': q_info.get('指标编号', ''),
            'node_id': r.get('节点编号', ''),
            'event_id': r.get('作答事件编号', ''),
            'revision': int(r.get('修订版本', '1')),
            'submit_time': r.get('模拟提交时间', ''),
            'score': int(r['得分']) if r.get('得分') else 0,
            'full_score': int(r['满分']) if r.get('满分') else 0,
            'is_correct': int(r['得分']) == int(r['满分']) if r.get('得分') and r.get('满分') else False,
            'student_answer': r.get('学生最终作答', ''),
            'student_process': r.get('解答过程', ''),
            'student_process_status': (
                'recorded' if r.get('解答过程', '').strip() else 'not_recorded'
            ),
            'student_process_status_label': (
                '已记录' if r.get('解答过程', '').strip() else '未记录'
            ),
            'scoring_point_scores': r.get('评分点得分', ''),
            'scoring_point_details': parse_scoring_point_details(
                r.get('评分点得分', ''), q_info.get('评分点', '')
            ),
            'quality_flags': (quality_flags_by_record or {}).get(
                r.get('记录编号', ''), []
            ),
            # 附加题目信息（方便后续模块直接使用）
            'question_type': q_info.get('题型', ''),
            'question_text': q_info.get('题干或内容', ''),
            'reference_answer': q_info.get('参考答案', ''),
            'reference_solution': q_info.get('参考解析', ''),
            'scoring_points_def': q_info.get('评分点', ''),
            'question_source': q_info.get('来源或资料文件', ''),
            'question_source_file': '题目与材料.csv'
        }
        structured_records.append(record)

    # 按学生+时间排序（BKT需要按时间顺序处理）
    structured_records.sort(key=lambda r: (r['student_id'], r['submit_time']))

    data_model = {
        'meta': {
            'schema_version': '1.1',
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_records': len(structured_records),
            'total_students': len(students),
            'total_questions': len([q for q in questions if q.get('材料类型') == '题目']),
            'total_indicators': 9,
            'total_themes': 3
        },
        'knowledge_structure': knowledge_structure,
        'question_indicator_map': question_indicator_map,
        'students': {s['学生编号']: s for s in students},
        'test_nodes': {n['节点编号']: n for n in test_nodes},
        'records': structured_records
    }

    print(f"  知识结构: {len(knowledge_structure)} 主题")
    print(f"  题目映射: {len(question_indicator_map)} 道题")
    print(f"  结构化记录: {len(structured_records)} 条")
    print(f"  数据已按学生+时间排序（供BKT使用）")

    return data_model


# ============================================================
# 第六部分：主函数
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("  智慧学伴 - 模块1：数据加载与清洗")
    print("=" * 60)

    # 1. 加载数据
    data = load_all_data()

    # 2. 清洗数据
    scored_records, pending, unanswered, quality_report = clean_records(
        data['records'],
        data['questions'],
        data['students']
    )
    quality_audit, quality_flags_by_record = audit_source_quality(
        data['records'],
        data['questions'],
        data['test_nodes']
    )
    quality_report['source_quality_audit'] = quality_audit

    # 3. 统计分析
    stats = compute_statistics(
        scored_records,
        data['questions'],
        data['students']
    )

    # 4. 构建关联数据模型
    data_model = build_data_model(
        scored_records,
        data['questions'],
        data['students'],
        data['course_requirements'],
        data['test_nodes'],
        quality_flags_by_record
    )

    # 5. 输出文件
    print("\n" + "=" * 50)
    print("步骤5：输出结果文件")
    print("=" * 50)

    # cleaned_data.json（供模块2和模块3使用）
    cleaned_path = os.path.join(OUTPUT_DIR, 'cleaned_data.json')
    with open(cleaned_path, 'w', encoding='utf-8') as f:
        json.dump(data_model, f, ensure_ascii=False, indent=2)
    print(f"  -> {cleaned_path}")

    # data_quality_report.json
    quality_path = os.path.join(OUTPUT_DIR, 'data_quality_report.json')
    with open(quality_path, 'w', encoding='utf-8') as f:
        json.dump(quality_report, f, ensure_ascii=False, indent=2)
    print(f"  -> {quality_path}")

    # statistics.json
    stats_path = os.path.join(OUTPUT_DIR, 'statistics.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"  -> {stats_path}")

    # 同时输出一份人类可读的统计摘要
    summary_path = os.path.join(OUTPUT_DIR, 'statistics_summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("智慧学伴 - 统计分析摘要\n")
        f.write("=" * 50 + "\n\n")

        f.write(f"总体得分率: {stats['overall']['score_rate_percent']}\n")
        f.write(f"总记录数: {stats['overall']['total_records']}\n\n")

        f.write("主题得分率:\n")
        for t, info in stats['by_theme'].items():
            f.write(f"  {t}: {info['score_rate_percent']} ({info['count']}条)\n")

        f.write("\n指标得分率（从低到高）:\n")
        sorted_inds = sorted(stats['by_indicator'].items(), key=lambda x: x[1]['score_rate'])
        for ind, info in sorted_inds:
            f.write(f"  {ind}: {info['score_rate_percent']} ({info['count']}条)\n")

        f.write("\n重点关注评分点（得分率<30%）:\n")
        for pid, info in stats['by_scoring_point'].items():
            if info['flag'] == 'critical':
                f.write(f"  {pid}: {info['score_rate_percent']} ({info['correct']}/{info['total']})\n")

        f.write("\n班级×主题对比:\n")
        for key, info in sorted(stats['by_class_theme'].items()):
            f.write(f"  {key}: {info['score_rate_percent']} ({info['count']}条)\n")

        f.write("\n学生得分率分布:\n")
        sorted_students = sorted(stats['by_student'].items(),
                                key=lambda x: x[1]['score_rate'])
        for sid, info in sorted_students:
            f.write(f"  {sid}({info['class']}): {info['score_rate_percent']} "
                   f"({info['count']}条) [{info['level']}]\n")

    print(f"  -> {summary_path}")

    print("\n" + "=" * 60)
    print("  模块1 完成！请检查输出文件。")
    print("=" * 60)

    return data_model, quality_report, stats


if __name__ == '__main__':
    main()
