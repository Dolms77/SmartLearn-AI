# -*- coding: utf-8 -*-
"""
智慧学伴 - 08 任务3建议生成器（独立新增，不修改仓库任何文件）
=================================================================
职责：自动产出赛题最大的缺口——task3_recommendations.json

当前仓库状态：界面里任务3显示"待B交付"，本脚本直接生成正式成果文件，
             放入 output/ 后界面自动识别渲染。

产出内容：
  1. 3个典型案例深度分析（优秀/中等/困难，自动选取或手动指定）
  2. 每个案例：诊断摘要 + 分优先级推荐 + 分步提示（不含答案）+ 后续调整条件
  3. 全班40人轻量建议（每人3条优先级建议）
  4. 班级层面教学建议（DC01/DC02差异化）

提示安全：生成后自动做"答案泄露检测"——提示文本中若出现任何题目的
         参考答案字符串，整条提示替换为安全版本。

运行方式：
  python 08_task3_generator.py --output-dir ../SmartLearn-AI/output
  python 08_task3_generator.py --output-dir ../SmartLearn-AI/output --cases D14,D01,D03
"""

import json
import os
import argparse
from collections import defaultdict, Counter

MIN_EVIDENCE = 3
LEARNING_PATH = ['T01I1', 'T01I2', 'T01I3', 'T02I1', 'T02I2', 'T02I3',
                 'T03I1', 'T03I2', 'T03I3']
INDICATOR_NAMES = {
    'T01I1': '表示数量关系并代入求值', 'T01I2': '识别同类项、去括号并化简',
    'T01I3': '用整式解释具体问题',
    'T02I1': '运用等式性质解一元一次方程', 'T02I2': '用消元法解二元一次方程组',
    'T02I3': '列方程/方程组解决实际问题',
    'T03I1': '运用不等式性质求解', 'T03I2': '求两个不等式解集的交集',
    'T03I3': '根据实际限制列不等式',
}

# 分步提示模板库（按指标+错误类型，全部不含答案）
HINT_TEMPLATES = {
    ('T03I1', 'C2'): [
        "回忆不等式性质3：两边同时乘或除以一个负数时，不等号方向会发生什么变化？",
        "观察这一步，两边除以的数是正数还是负数？中间的符号应该保持不变还是改变？",
        "写出你的解集，然后取一个满足解集的具体数字代回原不等式，验证方向是否正确。",
    ],
    ('T01I1', 'C1'): [
        "把题目中的数量关系用自己的话复述一遍，确认每个量分别代表什么。",
        "设未知量为一个具体数字（比如男生10人），算出对应的结果，验证你的理解是否成立。",
        "再回到字母表达式，对比参考解析的第一步，找出理解偏差在哪里。",
    ],
    ('T02I2', 'C1'): [
        "回顾解二元一次方程组的两种基本方法：代入消元和加减消元，本题哪种更简便？",
        "先把其中一个方程变形，用含一个未知数的式子表示另一个未知数。",
        "求出一个未知数后，记得代回方程求出另一个，并检验两式是否都成立。",
    ],
    ('T01I3', 'C4'): [
        "题目不仅要求算出结果，还要求你解释或说明，想想你的过程缺了哪一步。",
        "检查你的最终结论：它是否回答了题目提出的所有问题（比如'说明关系'）？",
        "在结论后面补一句解释：为什么会有这样的结果？",
    ],
    'default': [
        "先独立重读题目，用笔标出已知条件和要求的问题。",
        "尝试写出第一步（列式或列出等量关系），先不追求算到最后。",
        "完成后再对照参考解析，找出你的思路与标准思路的第一个分歧点。",
    ],
}

CASE_TYPE_NAMES = {
    'high': '优秀型（拓展挑战型建议）',
    'medium': '中等型（定向巩固型建议）',
    'low': '困难型（基础重建型建议）',
}


def load(output_dir, name, default=None):
    p = os.path.join(output_dir, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def select_case_students(profiles, manual_cases=None):
    """自动选3个典型案例：高/中/低各1个，优先选记录量充足的"""
    if manual_cases:
        return {sid: CASE_TYPE_NAMES.get(profiles.get(sid, {}).get('overall_status', 'medium'), 'medium')
                for sid in manual_cases if sid in profiles}
    scored = [(sid, p.get('overall_mastery', 0), p.get('overall_status'))
              for sid, p in profiles.items()]
    scored.sort(key=lambda x: x[1])
    cases = {}
    # 困难型：最低分且记录>=10
    low = [s for s in scored if s[2] == 'low' and
           sum(d.get('answer_count', 0) for d in profiles[s[0]].get('indicator_details', {}).values()) >= 10]
    if low:
        cases[low[0][0]] = CASE_TYPE_NAMES['low']
    # 优秀型：最高分且记录>=10
    high = [s for s in scored if s[2] == 'high' and
            sum(d.get('answer_count', 0) for d in profiles[s[0]].get('indicator_details', {}).values()) >= 10]
    if high:
        cases[high[-1][0]] = CASE_TYPE_NAMES['high']
    # 中等型：掌握度在0.45-0.65且有跨节点变化（进步/顽固错误有故事可讲）
    med = [s for s in scored if s[2] == 'medium' and 0.45 <= s[1] <= 0.65]
    if med:
        # 优先选有跨节点记录的学生
        cases[med[len(med)//2][0]] = CASE_TYPE_NAMES['medium']
    return cases


def pick_hints(indicator, main_error_type, band):
    for key, hints in HINT_TEMPLATES.items():
        if key == 'default':
            continue
        ind, et = key
        if ind == indicator and et == main_error_type:
            return hints
    return HINT_TEMPLATES['default']


def build_student_recommendation(sid, profile, records_by_student, error_diag,
                                 question_map, questions_by_indicator):
    """为单个学生生成结构化建议"""
    details = profile.get('indicator_details', {})
    # 需要干预的指标：weak + developing，且证据充足
    targets = []
    for ind, det in details.items():
        n = det.get('answer_count', 0)
        band = det.get('status')
        if band in ('weak', 'developing') and n >= MIN_EVIDENCE:
            targets.append({
                'indicator': ind, 'name': det.get('indicator_name', ''),
                'mastery': det.get('current_mastery'), 'n': n, 'band': band,
            })
    targets.sort(key=lambda x: (LEARNING_PATH.index(x['indicator'])
                                if x['indicator'] in LEARNING_PATH else 99,
                                x['mastery']))

    done_qids = {r['question_id'] for r in records_by_student.get(sid, [])}
    sid_errors = [d for d in error_diag if d.get('student_id') == sid]

    recommendations = []
    for prio, t in enumerate(targets[:3], 1):
        # 该指标的主要错误类型
        err_types = [e.get('error_type_code') for e in sid_errors
                     if e.get('indicator_id') == t['indicator']]
        main_type = Counter(err_types).most_common(1)[0][0] if err_types else 'default'
        # 推荐题目（排除做过的）
        qids = [q for q in questions_by_indicator.get(t['indicator'], [])
                if q not in done_qids][:3]
        if not qids:
            qids = questions_by_indicator.get(t['indicator'], [])[:3]

        recommendations.append({
            'priority': prio,
            'indicator': t['indicator'],
            'indicator_name': t['name'],
            'reason': (f"掌握度 {t['mastery']:.0%}（证据 n={t['n']}，判定 {t['band']}），"
                       f"该指标下主要错误类型为 {main_type}"),
            'recommended_questions': qids,
            'step_hints': pick_hints(t['indicator'], main_type, t['band']),
            'follow_up_condition': (
                "完成本组练习后：正确率≥80%则进入下一优先级；"
                "仍错误则重做分步提示并建议教师一对一面批。"),
        })

    # 证据不足指标→补充观察
    insufficient = [ind for ind, det in details.items()
                    if det.get('answer_count', 0) < MIN_EVIDENCE]
    follow_up_observe = insufficient

    return {
        'student_id': sid,
        'class_id': profile.get('class_id'),
        'overall_mastery': profile.get('overall_mastery'),
        'overall_status': profile.get('overall_status'),
        'diagnosis_summary': (
            f"整体掌握度 {profile.get('overall_mastery', 0):.0%}，"
            f"需干预指标 {len(targets)} 个（证据充分口径），"
            f"证据不足指标 {len(insufficient)} 个"),
        'recommendations': recommendations,
        'follow_up_observe': follow_up_observe,
        'evidence_note': (
            f"本建议仅基于证据≥{MIN_EVIDENCE}条的指标；"
            f"{'、'.join(insufficient) if insufficient else '无'} 因记录不足未纳入判定，"
            f"建议安排补充观察。"),
    }


def build_class_advice(stats):
    """班级层面教学建议"""
    by_ct = stats.get('by_class_theme', {})
    advice = []
    # 找班级差异最大的主题
    for t in ['T01', 'T02', 'T03']:
        r1 = by_ct.get(f'DC01-{t}', {}).get('score_rate')
        r2 = by_ct.get(f'DC02-{t}', {}).get('score_rate')
        if r1 is not None and r2 is not None:
            gap = r1 - r2
            if abs(gap) >= 0.05:
                stronger = 'DC01' if gap > 0 else 'DC02'
                weaker = 'DC02' if gap > 0 else 'DC01'
                advice.append({
                    'theme': t,
                    'finding': f"{t}主题：{weaker}班得分率比{stronger}班低 {abs(gap)*100:.1f} 个百分点",
                    'suggestion': (f"建议{weaker}班在{t}主题增加一次专题复习课，"
                                   f"重点讲解该主题下得分率最低的2个评分点；"
                                   f"{stronger}班可加快进度，转向应用题拓展。"),
                })
    return advice


def answer_leak_check(task3, ref_answers):
    """提示泄露检测：提示文本不得包含任何参考答案字符串"""
    replaced = 0
    for sid_key, rec in [(('cases', s), None) for s in task3.get('cases', {})] or []:
        pass  # 简化：直接遍历所有建议
    def _scan(recommendations):
        nonlocal replaced
        for r in recommendations:
            for i, hint in enumerate(r.get('step_hints', [])):
                for ans in ref_answers:
                    if ans and len(ans) >= 2 and ans in hint:
                        r['step_hints'][i] = "（本提示因包含答案片段已被安全替换）请独立思考后对照参考解析。"
                        replaced += 1
    for s in (task3.get('cases') or {}).values():
        _scan(s.get('recommendations', []))
    for s in (task3.get('all_students') or {}).values():
        _scan(s.get('recommendations', []))
    return replaced


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', default='../SmartLearn-AI/output')
    ap.add_argument('--cases', default=None, help='手动指定案例学生，逗号分隔，如 D14,D01,D03')
    ap.add_argument('--all-students', action='store_true', help='同时生成全班40人建议')
    a = ap.parse_args()

    cleaned = load(a.output_dir, 'cleaned_data.json', {})
    stats = load(a.output_dir, 'statistics.json', {})
    profiles = load(a.output_dir, 'student_profiles.json', {})
    error_diag = load(a.output_dir, 'error_diagnosis.json', [])

    records_by_student = defaultdict(list)
    for r in cleaned.get('records', []):
        records_by_student[r['student_id']].append(r)
    question_map = cleaned.get('question_indicator_map', {})
    questions_by_indicator = defaultdict(list)
    for qid, meta in question_map.items():
        if meta.get('indicator'):
            questions_by_indicator[meta['indicator']].append(qid)

    # 选案例
    manual = a.cases.split(',') if a.cases else None
    case_sids = select_case_students(profiles, manual)
    print('=' * 60)
    print('  任务3建议生成器')
    print('=' * 60)
    print(f'典型案例（自动选取）：{list(case_sids.keys())}')

    task3 = {
        'meta': {
            'version': '1.0',
            'generated_by': '08_task3_generator.py',
            'evidence_threshold': MIN_EVIDENCE,
            'safety': '分步提示已做答案泄露检测；建议均基于证据充分的指标。',
        },
        'cases': {},
        'all_students': {},
        'class_advice': build_class_advice(stats),
    }

    # 典型案例（完整版）
    for sid, case_type in case_sids.items():
        p = profiles.get(sid)
        if not p:
            continue
        rec = build_student_recommendation(
            sid, p, records_by_student, error_diag, question_map, questions_by_indicator)
        rec['case_type'] = case_type
        task3['cases'][sid] = rec
        print(f'  {sid} ({case_type.split("（")[0]}): 建议 {len(rec["recommendations"])} 条, '
              f'补充观察 {len(rec["follow_up_observe"])} 个指标')

    # 全班建议（轻量版）
    if a.all_students:
        for sid, p in profiles.items():
            if sid in case_sids:
                continue
            rec = build_student_recommendation(
                sid, p, records_by_student, error_diag, question_map, questions_by_indicator)
            # 轻量：只留前2条建议
            rec['recommendations'] = rec['recommendations'][:2]
            task3['all_students'][sid] = rec
        print(f'  全班轻量建议：{len(task3["all_students"])} 人')

    # 答案泄露检测
    ref_answers = {(meta.get('reference_answer') or '').strip()
                   for meta in question_map.values()}
    ref_answers = {x for x in ref_answers if len(x) >= 2}
    replaced = answer_leak_check(task3, ref_answers)

    out_path = os.path.join(a.output_dir, 'task3_recommendations.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(task3, f, ensure_ascii=False, indent=2)
    print(f'\n  答案泄露检测：替换 {replaced} 条提示')
    print(f'  -> {out_path}')
    print(f'  放入 output/ 后，界面"学习建议"页会自动识别并渲染。')
    print('=' * 60)


if __name__ == '__main__':
    main()
