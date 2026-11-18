# -*- coding: utf-8 -*-
"""
智慧学伴 - 08V2 任务3建议生成器（教育话语增强版）
====================================================
相比 V1 的升级：
  1. 教师话语体系：从"数据分析员"改为"教师"——教学归因 + 干预动作 + 情感支持
  2. 错误类型×学生水平 交叉话语库（优秀/中等/困难各有话术风格）
  3. 诊断摘要改为叙事体（有故事、有温度、有教学判断）
  4. 每道推荐题带"为什么选这道"的选题理由
  5. 分步提示贴合课堂教学场景（脚手架式，可操作）
  6. 生成后标记【人工审校点】，B 只需核对标记处即可定稿

运行：
  python 08_task3_generator_v2.py --output-dir ../SmartLearn-AI/output --all-students
  python 08_task3_generator_v2.py --output-dir ../SmartLearn-AI/output --cases D14,D01,D03
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

# ============================================================
# 教育话语库（核心升级）
# ============================================================

# --- 教学归因话语：错误类型 → 教师视角的"为什么会错" ---
ATTRIBUTION = {
    'C1': "这不是粗心，而是对概念本身的理解还没有建立起来——学生记住的是'操作步骤'，没有理解'为什么这样操作'。这类问题靠多做题目收效很慢，需要先回到概念的直观理解。",
    'C2': "学生对符号规则处于'知道但不会用'的状态——课堂上能复述规则，独立解题时就会遗漏。这需要在出错的当下被'拦住一次'，形成深刻印象。",
    'C3': "运算基本功的问题。学生思路是对的，但每一步的准确性不稳定。这类问题适合通过'放慢速度、逐步验算'来改善，不适合加大题量。",
    'C4': "解题结构不完整——会做主体步骤，但缺少检验、解释或规范表达。这反映学生把'解出答案'当成任务终点，还没有建立'完整作答'的习惯。",
    'C5': "表达规范问题。数学结论需要单位、格式和完整性，这直接影响得分但最容易通过示范和对照来纠正。",
    'C6': "典型的'一步卡壳、满盘皆输'——前面的步骤都对了，某一步出错后，后面全部不得分。对这类学生，最优先的不是学新内容，而是把'卡壳的那一步'单独拿出来攻克。",
    'default': "需要结合具体作答过程进一步判断错误性质。",
}

# --- 分层话术风格：开头引导语（按学生水平）---
TONE_OPENER = {
    'high': [
        "这位同学的整体表现已经很扎实，下面的建议以保持性和拓展性为主。",
        "从作答证据看，该生基础掌握牢固。建议的重点不在'补漏'，而在'提升解释与迁移能力'。",
    ],
    'medium': [
        "该生处于'部分掌握'状态——有些环节站住了，有些还在晃。下面的建议按优先级补最要紧的缺口。",
        "从跨节点记录看，该生的学习是动态的。建议盯住顽固错误，同时利用已有的进步势头。",
    ],
    'low': [
        "该生目前基础尚未站稳，建议放慢节奏、缩小步子，从最有把握建立信心的内容开始。",
        "对这位同学，'补课'不如'补成功体验'——先让他完整做对一道简单题，比做十道难题有用。",
    ],
    'insufficient': [
        "该生有效作答记录较少，多项指标证据不足。当前不建议直接下掌握结论，优先安排补充观察。",
    ],
}

# --- 按错误类型的分步提示（脚手架式，三阶递进，不含答案）---
SCAFFOLD_HINTS = {
    'C1': [
        "第一步（建直觉）：先丢掉字母，设一个具体数字。比如题目里的 n 就当是 3，把整个问题用数字完整算一遍，看看结果是什么。",
        "第二步（找规律）：数字算对了之后，回头看看——刚才的计算过程中，哪一步用到了'n 是整数'这个条件？这一步往往就是理解的钥匙。",
        "第三步（回到抽象）：现在把数字换回字母，重新做一遍。如果中途卡住，对比第一步的数字计算，看卡在哪一步。",
    ],
    'C2': [
        "第一步（说规则）：不看任何资料，用自己的话说一遍——不等式两边同时乘或除以一个负数，不等号方向会怎样？说不出来就先翻书，能说出来再继续。",
        "第二步（慢动作）：做题时强制自己在'除以负数'这一步停下来，先写出'方向要变'三个字，再动笔写不等号。先求对，再求快。",
        "第三步（自验证）：解出后必须代回原不等式检验。取一个你认为在解集里的数和一个不在的数，各代一次——方向错了立刻就能暴露。",
    ],
    'C3': [
        "第一步（降速）：把演算速度降到平时的一半，每一步只做一件事（只移项、或只合并、或只去括号），不要合并动作。",
        "第二步（留痕）：每一步的中间结果都写下来，不要在脑子里跳步。写出来之后，从第一步开始逐步验算。",
        "第三步（对答案的习惯）：算完先自己验算一遍再对答案。错的题不要擦掉，把错误的那一步圈出来——你会发现错误往往集中在同一类。",
    ],
    'C4': [
        "第一步（列清单）：解这类题的标准步骤一共有几步？先在草稿纸上列出来，做完后对照清单打勾，看缺了哪步。",
        "第二步（补关键步）：特别注意两类容易漏的步骤——检验（把解代回原式）和解释（题目问'为什么'就必须回答为什么）。",
        "第三步（完整重做）：找一道做过的题，按完整规范重新写一遍，从设未知数到写答句，一步不少。",
    ],
    'C5': [
        "第一步（对照范本）：找一道教材例题，逐行对照自己的作答——单位的书写位置、'解：'的格式、结论句的完整表达。",
        "第二步（自查口诀）：交卷前默念'有没有单位？有没有答句？结论写全了吗？'——养成 10 秒自查习惯。",
        "第三步（同伴互查）：和同桌交换检查对方的规范表达，找别人毛病比找自己的容易，印象也更深。",
    ],
    'C6': [
        "第一步（定位卡点）：把做错的题重新做一遍，做到'和上次不一样的那一步'就是卡点。把它单独抄在错题本上。",
        "第二步（专项小练）：只针对卡点的那一类操作找 2-3 道题练，其他步骤可以只写思路不细算，节省时间。",
        "第三步（整题重验）：卡点练顺之后，回到原题完整重做一遍，确认全流程能走通。",
    ],
    'default': [
        "第一步（复述题意）：不看题目，用自己的话把这道题的条件和问题说一遍。说不出来就再读一遍——很多错误源于没读懂题。",
        "第二步（写第一步）：不追求做完整道题，只写出第一步（列式/设未知数/画出等量关系）。",
        "第三步（对照分歧）：完成后对照参考解析，找到你的思路和标准思路的第一个分歧点——那通常就是需要理解的地方。",
    ],
}

# --- 选题理由模板（按题目全班得分率分档）---
def question_reason(score_rate):
    if score_rate is None:
        return "作为该指标的针对性练习"
    if score_rate >= 0.7:
        return "全班得分率较高，适合先建立信心、热身进入状态"
    if score_rate >= 0.4:
        return "难度适中，正好处于'踮脚够得着'的区间，最适合巩固"
    return "全班普遍失分，属于必攻的关键题，建议在教师陪伴下完成"

# --- 调整条件话语（按水平差异化）---
FOLLOW_UP = {
    'high': "完成拓展任务后，请学生用自己的话向同伴讲解一遍解题思路（能讲清楚才算真掌握，费曼式检验）；讲解顺畅则进入下一主题的自学。",
    'medium': "完成推荐题目后若正确率≥80%，进入下一优先级；若仍出错，做一次错题复盘（说出错在哪一步、为什么），再决定是否需要面批。",
    'low': "只要能独立完整做对推荐题目中的 2 道，就给予明确肯定并进入下一组（小步子原则，先积累成功体验）；连续两组未达标则建议教师一对一面批，而不是继续加题。",
}


def load(output_dir, name, default=None):
    p = os.path.join(output_dir, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# 学生画像构建（含错因统计、跨节点变化）
# ============================================================

def build_student_context(sid, profiles, records_by_student, error_diag,
                          stats, question_map):
    """构建单个学生的完整上下文（供话语生成使用）"""
    p = profiles.get(sid, {})
    details = p.get('indicator_details', {})

    # 错因统计
    sid_errors = [e for e in error_diag if e.get('student_id') == sid]
    type_counter = Counter(e.get('error_type_code') for e in sid_errors)

    # 跨节点变化
    changes = [c for c in stats.get('cross_node_changes', [])
               if c.get('student_id') == sid]
    improved = [c for c in changes if c['change_type'] == 'improved']
    persistent = [c for c in changes if c['change_type'] == 'persistent_error']
    regressed = [c for c in changes if c['change_type'] == 'regressed']

    # 总答题量
    total_n = sum(d.get('answer_count', 0) for d in details.values())

    # 水平判定
    level = p.get('overall_status', 'medium')

    return {
        'profile': p, 'details': details, 'level': level,
        'errors': sid_errors, 'type_counter': type_counter,
        'improved': improved, 'persistent': persistent, 'regressed': regressed,
        'total_n': total_n,
        'insufficient': [ind for ind, d in details.items()
                         if d.get('answer_count', 0) < MIN_EVIDENCE],
    }


# ============================================================
# 教育性叙事诊断摘要
# ============================================================

def narrative_summary(sid, ctx):
    """生成叙事体诊断摘要——像教师写给同事的学情通报"""
    p = ctx['profile']
    parts = []

    # 开场：水平定调（分层话术）
    openers = TONE_OPENER.get(ctx['level'], TONE_OPENER['medium'])
    parts.append(openers[0])

    # 证据规模
    if ctx['total_n'] >= 15:
        parts.append(f"已有 {ctx['total_n']} 条有效作答记录，证据基础较充分。")
    elif ctx['total_n'] >= 8:
        parts.append(f"目前有 {ctx['total_n']} 条有效作答记录，基本可以判断大方向，但部分指标的结论仍需更多证据。")
    else:
        parts.append(f"有效作答记录仅 {ctx['total_n']} 条，多项指标证据不足——当前最重要的不是下结论，而是安排补充观察。")

    # 顽固错误与进步（有故事可讲）
    if ctx['persistent']:
        qids = '、'.join(c['question_id'] for c in ctx['persistent'][:3])
        parts.append(f"值得注意的是，该生在 {qids} 上两次作答给出完全相同的错误答案——这不是随机失误，说明错误理解已经固化，普通刷题难以纠正，需要针对性干预。")
    if ctx['improved']:
        qids = '、'.join(c['question_id'] for c in ctx['improved'][:3])
        parts.append(f"同时也有积极信号：{qids} 从前期错误到后来做对，说明具备学习能力，教学干预是有效的。")
    if ctx['regressed'] and not ctx['persistent']:
        qids = '、'.join(c['question_id'] for c in ctx['regressed'][:2])
        parts.append(f"需要留意 {qids} 出现了'原来会做、后来做错'的情况，建议排查是遗忘还是知识干扰。")

    # 主要错因画像
    if ctx['type_counter']:
        main_type, main_n = ctx['type_counter'].most_common(1)[0]
        type_names = {'C1': '概念理解', 'C2': '符号规则应用', 'C3': '运算准确性',
                      'C4': '步骤完整性', 'C5': '表达规范', 'C6': '级联失分'}
        parts.append(f"错因分析显示，其错误主要集中在{type_names.get(main_type, main_type)}（{main_n} 条，占其错误的 {main_n/max(len(ctx['errors']),1)*100:.0f}%）。")

    return ''.join(parts)


# ============================================================
# 单条建议生成（教育话语版）
# ============================================================

def edu_recommendation(ind_ctx, ctx, question_map, questions_by_indicator,
                       done_qids, point_stats, prio):
    """生成一条教育性建议"""
    ind, name = ind_ctx['indicator'], ind_ctx['name']
    mastery, n, band = ind_ctx['mastery'], ind_ctx['n'], ind_ctx['band']

    # 该指标下的主要错误类型
    ind_errors = [e for e in ctx['errors'] if e.get('indicator_id') == ind]
    type_counter = Counter(e.get('error_type_code') for e in ind_errors)
    main_type = type_counter.most_common(1)[0][0] if type_counter else 'default'

    # 理由（叙事+归因）
    reason_parts = []
    band_cn = {'weak': '薄弱', 'developing': '发展中'}.get(band, band)
    reason_parts.append(
        f"该生在此指标上判定为「{band_cn}」（得分依据 {n} 条记录，加权掌握度 {mastery:.0%}）。")
    # 教学归因话语
    reason_parts.append(ATTRIBUTION.get(main_type, ATTRIBUTION['default']))

    # 顽固错误特写
    persistent_here = [c for c in ctx['persistent'] if
                       question_map.get(c['question_id'], {}).get('indicator') == ind]
    if persistent_here:
        reason_parts.append(
            f"特别提示：{persistent_here[0]['question_id']} 已两次犯同样的错误（作答「{persistent_here[0]['N01']['answer'][:20]}」），"
            f"建议教师直接就该题进行一次面谈式追问，弄清学生的真实想法。")

    # 推荐题目（带选题理由）
    cand = [q for q in questions_by_indicator.get(ind, []) if q not in done_qids]
    if not cand:
        cand = questions_by_indicator.get(ind, [])
    # 按全班得分率排序：低水平先易后难，高水平先难后易
    def q_rate(q):
        # 用该题评分点的平均得分率近似
        rates = [v['score_rate'] for k, v in point_stats.items()
                 if k.startswith(q) and k[len(q):len(q)+1] == 'P']
        return sum(rates) / len(rates) if rates else None
    ranked = sorted(cand, key=lambda q: (q_rate(q) is None, q_rate(q) or 0),
                    reverse=(ctx['level'] == 'high'))
    rec_qids = ranked[:3]

    question_details = []
    for q in rec_qids:
        r = q_rate(q)
        question_details.append({
            'question_id': q,
            'why_this': question_reason(r),
        })

    # 分步提示（按主要错误类型选脚手架）
    hints = SCAFFOLD_HINTS.get(main_type, SCAFFOLD_HINTS['default'])

    # 调整条件（按水平）
    follow_up = FOLLOW_UP.get(ctx['level'], FOLLOW_UP['medium'])

    return {
        'priority': prio,
        'indicator': ind,
        'indicator_name': name,
        'mastery': mastery,
        'evidence_n': n,
        'band': band,
        'reason': ''.join(reason_parts),
        'recommended_questions': rec_qids,
        'question_details': question_details,
        'step_hints': hints,
        'hint_style': '脚手架三阶递进（建直觉→慢操作→自验证），不含答案',
        'follow_up_condition': follow_up,
        'main_error_type': main_type,
        'evidence_ids': [e.get('record_id') for e in ind_errors[:5]],
        'human_review': '【人工审校点】请核对顽固错误特写与选题顺序是否符合该生实际',
    }


# ============================================================
# 主流程
# ============================================================

def generate_for_student(sid, profiles, records_by_student, error_diag,
                         stats, question_map, questions_by_indicator,
                         point_stats):
    ctx = build_student_context(sid, profiles, records_by_student,
                                error_diag, stats, question_map)
    p = ctx['profile']
    details = ctx['details']

    # 干预目标：weak/developing 且证据充分
    targets = []
    for ind, det in details.items():
        n, band = det.get('answer_count', 0), det.get('status')
        if band in ('weak', 'developing') and n >= MIN_EVIDENCE:
            targets.append({'indicator': ind, 'name': det.get('indicator_name', ''),
                            'mastery': det.get('current_mastery'), 'n': n, 'band': band})
    targets.sort(key=lambda x: (LEARNING_PATH.index(x['indicator'])
                                if x['indicator'] in LEARNING_PATH else 99, x['mastery']))

    done_qids = {r['question_id'] for r in records_by_student.get(sid, [])}
    recommendations = [edu_recommendation(t, ctx, question_map,
                                           questions_by_indicator, done_qids,
                                           point_stats, i)
                       for i, t in enumerate(targets[:3], 1)]

    # 优秀生无薄弱时的拓展建议
    if not recommendations:
        # 找最强的2个已掌握指标做拓展
        mastered = [{'indicator': ind, 'name': det.get('indicator_name', ''),
                     'mastery': det.get('current_mastery'), 'n': det.get('answer_count', 0),
                     'band': 'mastered'}
                    for ind, det in details.items()
                    if det.get('status') == 'mastered']
        mastered.sort(key=lambda x: -x['mastery'])
        for i, t in enumerate(mastered[:2], 1):
            cand = [q for q in questions_by_indicator.get(t['indicator'], [])
                    if q not in done_qids][:2]
            recommendations.append({
                'priority': i, 'indicator': t['indicator'],
                'indicator_name': t['name'],
                'mastery': t['mastery'],
                'evidence_n': t['n'],
                'band': t.get('band', 'mastered'),
                'reason': (f"该生已稳定掌握此指标（掌握度 {t['mastery']:.0%}，n={t['n']}）。"
                           "建议进行拓展性任务：不是再做同类型题，而是转向'能讲给别人听'的输出式训练——"
                           "给学生一道该指标的中等题，让他给同伴讲解完整思路，讲得清才算真掌握。"),
                'recommended_questions': cand,
                'question_details': [{'question_id': q, 'why_this': '拓展检验：讲题任务载体'}
                                     for q in cand],
                'step_hints': [
                    "第一步：独立完成这道题，写出完整规范过程。",
                    "第二步：合上答案，向一位同学完整讲解你的思路——从读题到最后检验。",
                    "第三步：请对方追问你两个'为什么'。如果哪里讲卡了，那里就是下一步要深挖的点。"],
                'hint_style': '费曼式输出训练',
                'follow_up_condition': FOLLOW_UP['high'],
                'main_error_type': '—',
                'evidence_ids': [],
                'human_review': '【人工审校点】拓展任务形式可根据课堂实际调整',
            })

    return {
        'student_id': sid,
        'class_id': p.get('class_id'),
        'level': ctx['level'],
        'diagnosis_summary': narrative_summary(sid, ctx),
        'diagnosis_summary_style': '叙事体（教师学情通报口吻）',
        'recommendations': recommendations,
        'follow_up_observe': ctx['insufficient'],
        'insufficient_note': (
            f"以下指标证据不足（有效作答 < {MIN_EVIDENCE} 条），未纳入判定，"
            f"建议优先安排补充观察而非直接补课：{'、'.join(ctx['insufficient']) if ctx['insufficient'] else '无'}。"),
    }


def select_cases(profiles, manual=None):
    if manual:
        return [s for s in manual if s in profiles]
    scored = sorted(profiles.items(), key=lambda kv: kv[1].get('overall_mastery', 0))
    # 困难：最低且有>=10条记录
    low = [s for s, p in scored
           if p.get('overall_status') == 'low'
           and sum(d.get('answer_count', 0) for d in p.get('indicator_details', {}).values()) >= 10]
    high = [s for s, p in scored
            if p.get('overall_status') == 'high'
            and sum(d.get('answer_count', 0) for d in p.get('indicator_details', {}).values()) >= 10]
    med = [s for s, p in scored
          if p.get('overall_status') == 'medium'
          and 0.45 <= p.get('overall_mastery', 0) <= 0.65]
    cases = []
    if low: cases.append(low[0])
    if high: cases.append(high[-1])
    if med: cases.append(med[len(med)//2])
    return cases


def build_class_advice(stats):
    """根据两个班的主题得分差异给出可追溯的教学建议。"""
    by_ct = stats.get('by_class_theme', {})
    advice = []
    for theme in ['T01', 'T02', 'T03']:
        rate1 = by_ct.get(f'DC01-{theme}', {}).get('score_rate')
        rate2 = by_ct.get(f'DC02-{theme}', {}).get('score_rate')
        if rate1 is None or rate2 is None:
            continue
        gap = rate1 - rate2
        if abs(gap) < 0.05:
            continue
        stronger, weaker = ('DC01', 'DC02') if gap > 0 else ('DC02', 'DC01')
        advice.append({
            'theme': theme,
            'finding': (
                f"{theme}主题：{weaker}班得分率比{stronger}班低 "
                f"{abs(gap) * 100:.1f} 个百分点"),
            'suggestion': (
                f"建议{weaker}班在{theme}主题增加一次专题复习，重点讲解该主题下"
                f"得分率最低的评分点；{stronger}班可转向应用题拓展。"),
        })
    return advice


def main():
    ap = argparse.ArgumentParser()
    default_output_dir = os.environ.get('SS_OUT') or os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'output'))
    ap.add_argument('--output-dir', default=default_output_dir)
    ap.add_argument('--cases', default=None)
    ap.add_argument('--all-students', action='store_true', help='同时生成全班学生建议')
    a = ap.parse_args()

    cleaned = load(a.output_dir, 'cleaned_data.json', {})
    stats = load(a.output_dir, 'statistics.json', {})
    profiles = load(a.output_dir, 'student_profiles.json', {})
    error_diag = load(a.output_dir, 'error_diagnosis.json', [])
    if not cleaned.get('records') or not profiles or not cleaned.get('question_indicator_map'):
        raise SystemExit('缺少 01-03 生成的数据，请先运行数据加载、统计和错因诊断脚本。')

    records_by_student = defaultdict(list)
    for r in cleaned.get('records', []):
        records_by_student[r['student_id']].append(r)
    question_map = cleaned.get('question_indicator_map', {})
    questions_by_indicator = defaultdict(list)
    for qid, meta in question_map.items():
        if meta.get('indicator'):
            questions_by_indicator[meta['indicator']].append(qid)
    point_stats = stats.get('by_scoring_point', {})

    case_sids = select_cases(profiles, a.cases.split(',') if a.cases else None)
    print('=' * 62)
    print('  任务3建议生成器 V2（教育话语增强版）')
    print('=' * 62)
    print(f'典型案例：{case_sids}')

    task3 = {
        'meta': {'version': '2.0-edu', 'generated_by': '08_task3_generator.py',
                 'evidence_threshold': MIN_EVIDENCE,
                 'style': '教师话语体系：教学归因+干预动作+情感支持',
                 'human_review_note': '所有标有【人工审校点】处需B核对后定稿'},
        'cases': {}, 'all_students': {},
        'class_advice': build_class_advice(stats),
    }

    for sid in case_sids:
        rec = generate_for_student(sid, profiles, records_by_student, error_diag,
                                   stats, question_map, questions_by_indicator, point_stats)
        task3['cases'][sid] = rec
        print(f'\n── {sid}（{rec["level"]}）──')
        print(f'  摘要：{rec["diagnosis_summary"][:120]}...')
        for r in rec['recommendations']:
            print(f'  P{r["priority"]} {r["indicator"]}: 题{r["recommended_questions"]} '
                  f'[{r["hint_style"][:12]}]')

    if a.all_students:
        for sid in profiles:
            if sid in case_sids:
                continue
            rec = generate_for_student(sid, profiles, records_by_student, error_diag,
                                       stats, question_map, questions_by_indicator, point_stats)
            rec['recommendations'] = rec['recommendations'][:2]
            task3['all_students'][sid] = rec
        print(f'\n  全班轻量建议：{len(task3["all_students"])} 人')

    # 答案泄露检测
    ref_answers = {(m.get('reference_answer') or '').strip()
                   for m in question_map.values()}
    ref_answers = {x for x in ref_answers if len(x) >= 2}
    replaced = 0
    def scan(recs):
        nonlocal replaced
        for r in recs:
            for i, h in enumerate(r.get('step_hints', [])):
                for ans in ref_answers:
                    if ans in h:
                        r['step_hints'][i] = "（安全替换）请独立完成后对照参考解析。"
                        replaced += 1
    for s in task3['cases'].values(): scan(s.get('recommendations', []))
    for s in task3['all_students'].values(): scan(s.get('recommendations', []))

    out_path = os.path.join(a.output_dir, 'task3_recommendations.json')
    os.makedirs(a.output_dir, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(task3, f, ensure_ascii=False, indent=2)
    print(f'\n  泄露检测替换 {replaced} 条提示')
    print(f'  -> {out_path}')
    print('=' * 62)


if __name__ == '__main__':
    main()
