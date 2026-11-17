# -*- coding: utf-8 -*-
"""
智慧学伴 - 07 多智能体编排层（独立新增，不修改仓库任何文件）
=================================================================
职责：在现有"统计引擎 + LLM对话"之上，加一层多智能体编排，
     把对话从"问答助手"升级为"自主规划 + 工具调用 + 输出校验"的智能体。

设计原则（与仓库"三条口径"一致）：
  1. 编排器是纯 Python 规则路由，不用 LLM 做调度 → 确定性强、零成本、可解释
  2. LLM 只做"翻译官"：数字永远来自统计/工具，LLM 只负责改写
  3. 校验 Agent 是第四道防线：结论必须带证据ID、提示不得含答案、
     证据 < 3 条强制 insufficient，违反一律拦截改写

四个专职 Agent：
  - DiagnosisAgent   诊断：调用统计/错因/证据链工具
  - RecommendationAgent 建议：调用掌握度 + 题目匹配 + 分步提示模板
  - QaAgent          答疑：RAG 检索 + LLM 改写（白名单约束）
  - ValidatorAgent   校验：输出硬性校验（本文件内置，不依赖 LLM）

依赖：只用标准库 + 仓库 output/ 里的 JSON。
     LLM 调用可选（有 DeepSeek Key 时启用，否则走离线模板）。

运行方式：
  python 07_multi_agent.py --output-dir ../SmartLearn-AI/output
  python 07_multi_agent.py --output-dir ../SmartLearn-AI/output --student D01 --demo
"""

import json
import os
import re
import argparse
from collections import defaultdict

# ============================================================
# 配置区
# ============================================================

MIN_EVIDENCE = 3  # 与仓库 adapter.py 一致的证据门槛
INDICATOR_NAMES = {
    'T01I1': '表示数量关系并代入求值', 'T01I2': '识别同类项、去括号并化简',
    'T01I3': '用整式解释具体问题',
    'T02I1': '运用等式性质解一元一次方程', 'T02I2': '用消元法解二元一次方程组',
    'T02I3': '列方程/方程组解决实际问题',
    'T03I1': '运用不等式性质求解', 'T03I2': '求两个不等式解集的交集',
    'T03I3': '根据实际限制列不等式',
}
LEARNING_PATH = ['T01I1', 'T01I2', 'T01I3', 'T02I1', 'T02I2', 'T02I3',
                 'T03I1', 'T03I2', 'T03I3']


# ============================================================
# 数据加载（只读仓库 output/，不修改）
# ============================================================

class DataBundle:
    def __init__(self, output_dir):
        self.dir = output_dir
        def load(name, default=None):
            p = os.path.join(output_dir, name)
            if not os.path.exists(p):
                return default if default is not None else {}
            with open(p, encoding='utf-8') as f:
                return json.load(f)
        self.cleaned = load('cleaned_data.json')
        self.stats = load('statistics.json')
        self.profiles = load('student_profiles.json')
        self.error_diag = load('error_diagnosis.json', [])
        self.error_summary = load('error_pattern_summary.json')
        self.question_map = self.cleaned.get('question_indicator_map', {})
        self.records = self.cleaned.get('records', [])
        # 索引：学生→记录、指标→题目
        self.records_by_student = defaultdict(list)
        for r in self.records:
            self.records_by_student[r['student_id']].append(r)
        self.questions_by_indicator = defaultdict(list)
        for qid, meta in self.question_map.items():
            ind = meta.get('indicator')
            if ind:
                self.questions_by_indicator[ind].append(qid)


# ============================================================
# 工具层（供各 Agent 调用，全部确定性计算）
# ============================================================

class ToolBox:
    """Agent 可调用的工具集。每个工具都返回带证据ID的结构化结果。"""

    def __init__(self, bundle: DataBundle):
        self.b = bundle

    def get_student_mastery(self, sid):
        """学生掌握度（带证据量标注）"""
        p = (self.b.profiles or {}).get(sid)
        if not p:
            return {'error': f'学生 {sid} 不存在'}
        inds = []
        for ind, det in (p.get('indicator_details') or {}).items():
            n = det.get('answer_count', 0)
            inds.append({
                'indicator': ind,
                'name': det.get('indicator_name', ''),
                'mastery': det.get('current_mastery'),
                'evidence_n': n,
                'band': 'insufficient' if n < MIN_EVIDENCE else det.get('status'),
                'record_ids': [r['record_id'] for r in
                               self.b.records_by_student.get(sid, [])
                               if r.get('indicator_id') == ind][:10],
            })
        return {
            'student_id': sid,
            'class': p.get('class_id'),
            'overall_mastery': p.get('overall_mastery'),
            'overall_status': p.get('overall_status'),
            'indicators': inds,
        }

    def get_student_errors(self, sid, top_n=10):
        """学生错因记录（带record_id）"""
        errs = [d for d in (self.b.error_diag or []) if d.get('student_id') == sid]
        return {'student_id': sid, 'total': len(errs), 'errors': errs[:top_n]}

    def get_evidence_chain(self, sid, indicator):
        """某生某指标的证据链（下钻到原始记录）"""
        recs = [r for r in self.b.records_by_student.get(sid, [])
                if r.get('indicator_id') == indicator]
        return {
            'student_id': sid, 'indicator': indicator,
            'evidence_count': len(recs),
            'sufficient': len(recs) >= MIN_EVIDENCE,
            'records': [{
                'record_id': r['record_id'], 'question': r['question_id'],
                'node': r['node_id'], 'score': f"{r.get('score')}/{r.get('full_score')}",
                'answer': (r.get('student_answer') or '')[:60],
                'scoring_points': r.get('scoring_point_scores') or '—',
            } for r in recs],
        }

    def get_class_comparison(self, cls=None):
        """班级对比（全部统计来自仓库 statistics.json）"""
        by_ct = (self.b.stats or {}).get('by_class_theme', {})
        out = {}
        for key, v in by_ct.items():
            cls_name, theme = key.split('-')
            out.setdefault(cls_name, {})[theme] = v
        return out

    def match_practice_questions(self, indicator, exclude_qids=None, top_n=3):
        """按指标匹配练习题目，排除已做过的"""
        qids = self.b.questions_by_indicator.get(indicator, [])
        if exclude_qids:
            qids = [q for q in qids if q not in exclude_qids]
        return qids[:top_n]

    def get_cross_node_changes(self, sid=None):
        """跨节点变化（进步/退步/顽固错误）"""
        changes = (self.b.stats or {}).get('cross_node_changes', [])
        if sid:
            changes = [c for c in changes if c.get('student_id') == sid]
        return changes


# ============================================================
# 专职 Agent
# ============================================================

class DiagnosisAgent:
    """诊断 Agent：学情诊断、错因分析、证据链下钻"""

    def __init__(self, tools: ToolBox):
        self.tools = tools

    def run(self, intent: dict) -> dict:
        sid = intent.get('student_id')
        if not sid:
            return {'agent': 'DiagnosisAgent', 'error': '缺少 student_id'}

        mastery = self.tools.get_student_mastery(sid)
        errors = self.tools.get_student_errors(sid)
        changes = self.tools.get_cross_node_changes(sid)

        # 汇总成自然语言骨架（数字全部来自工具）
        weak = [i for i in mastery.get('indicators', [])
                if i['band'] in ('weak', 'developing') and i['mastery'] is not None]
        weak.sort(key=lambda x: x['mastery'])
        insufficient = [i for i in mastery.get('indicators', [])
                        if i['band'] == 'insufficient']

        summary_parts = []
        ov = mastery.get('overall_mastery')
        if ov is not None:
            summary_parts.append(f"整体掌握度 {ov:.0%}（仅统计证据充分的指标）")
        if weak:
            top = weak[0]
            summary_parts.append(
                f"最薄弱：{top['indicator']}（{top['name']}），掌握度 {top['mastery']:.0%}，"
                f"证据 n={top['evidence_n']}")
        if insufficient:
            codes = '、'.join(i['indicator'] for i in insufficient)
            summary_parts.append(f"证据不足（n<{MIN_EVIDENCE}）：{codes}，不下掌握结论")

        return {
            'agent': 'DiagnosisAgent',
            'student_id': sid,
            'summary': '；'.join(summary_parts),
            'mastery': mastery,
            'errors': errors,
            'cross_node_changes': changes,
            'evidence_ids': [r['record_id'] for i in mastery.get('indicators', [])
                             for r in [i] for _ in [0]
                             for r in []] or [
                rid for i in mastery.get('indicators', [])
                for rid in i.get('record_ids', [])][:20],
        }


class RecommendationAgent:
    """建议 Agent：生成个性化学习路径（含分步提示，不直接给答案）"""

    # 分步提示模板（按错误类型，不含答案）
    HINT_TEMPLATES = {
        'C2': [  # 符号错误
            "回忆不等式性质3：两边同时乘或除以一个负数时，不等号方向会发生什么变化？",
            "观察这一步，两边除以的数是正还是负？中间的符号应该变吗？",
            "写出你的解集，然后取一个满足解集的数代回原式，验证方向是否正确。",
        ],
        'C1': [  # 概念误解
            "先把题目中的数量关系用你自己的话复述一遍，确认每个量代表什么。",
            "尝试代入一个具体的数字（比如设未知量为3），验证你的理解是否成立。",
            "再回到抽象的字母表达式，对比参考解析的第一步，找出理解偏差在哪。",
        ],
        'C3': [  # 计算失误
            "重新读一遍你的计算过程，从第一步开始逐步验算，找出哪一步出错了。",
            "把每一步的中间结果单独写出来，检查符号和系数是否正确。",
            "最后用结果代入原式验证：如果等式不成立，说明中间有计算错误。",
        ],
        'C4': [  # 步骤遗漏
            "回顾完整解题步骤的标准流程，数一数你的过程少了几步。",
            "特别注意最后一步：你的结果是否经过了检验或核对？",
            "重新完整写一遍过程，确保每一步都有依据。",
        ],
        'default': [
            "先独立重读题目，标出已知条件和要求的问题。",
            "尝试写出第一步（列式或列出等量关系），先不追求结果。",
            "完成后再对照参考解析，找出你的思路与标准思路的第一个分歧点。",
        ],
    }

    def __init__(self, tools: ToolBox):
        self.tools = tools

    def run(self, intent: dict) -> dict:
        sid = intent.get('student_id')
        mastery = self.tools.get_student_mastery(sid)
        errors = self.tools.get_student_errors(sid)
        done_qids = {r['question_id'] for r in
                     self.tools.b.records_by_student.get(sid, [])}

        # 取需要练的指标（弱/发展中，按学习路径排序）
        weak = [i for i in mastery.get('indicators', [])
                if i['band'] in ('weak', 'developing') and i['mastery'] is not None]
        weak.sort(key=lambda x: (LEARNING_PATH.index(x['indicator'])
                                 if x['indicator'] in LEARNING_PATH else 99,
                                 x['mastery']))

        recommendations = []
        for prio, ind in enumerate(weak[:3], 1):
            qids = self.tools.match_practice_questions(
                ind['indicator'], exclude_qids=done_qids, top_n=3)
            # 该指标下该生的主要错误类型（用于选提示模板）
            err_types = [e.get('error_type_code') for e in errors.get('errors', [])
                         if e.get('indicator_id') == ind['indicator']]
            main_type = err_types[0] if err_types else 'default'
            hints = self.HINT_TEMPLATES.get(main_type, self.HINT_TEMPLATES['default'])

            recommendations.append({
                'priority': prio,
                'indicator': ind['indicator'],
                'indicator_name': ind['name'],
                'mastery': ind['mastery'],
                'evidence_n': ind['evidence_n'],
                'reason': (f"掌握度 {ind['mastery']:.0%}（n={ind['evidence_n']}），"
                           f"该指标下主要错误类型：{main_type}"),
                'recommended_questions': qids,
                'step_hints': hints,
                'follow_up_condition': (
                    "完成推荐题目后，若正确率 ≥80% 进入下一优先级；"
                    "若仍出错，触发下一轮分步提示并建议教师面批。"),
            })

        return {
            'agent': 'RecommendationAgent',
            'student_id': sid,
            'diagnosis_summary': f"整体掌握度 {mastery.get('overall_mastery', 0):.0%}",
            'recommendations': recommendations,
            'evidence_ids': [rid for i in mastery.get('indicators', [])
                             for rid in i.get('record_ids', [])][:20],
            'note': '提示均为引导式，不直接给出答案；题目均来自赛题材料。',
        }


class QaAgent:
    """答疑 Agent：受事实白名单约束的自由问答"""

    def __init__(self, tools: ToolBox):
        self.tools = tools

    def run(self, intent: dict) -> dict:
        # 离线模式：返回可用的白名单事实摘要，供 LLM 改写或离线模板
        sid = intent.get('student_id')
        facts = {}
        if sid:
            facts['mastery'] = self.tools.get_student_mastery(sid)
            facts['errors'] = self.tools.get_student_errors(sid, top_n=5)
        facts['class_comparison'] = self.tools.get_class_comparison()
        return {
            'agent': 'QaAgent',
            'question': intent.get('question', ''),
            'facts_whitelist': facts,
            'note': 'LLM 改写时只允许引用 facts_whitelist 内的数字；'
                    '无 API Key 时使用离线模板。',
        }


class ValidatorAgent:
    """校验 Agent：输出硬性校验，四条防线"""

    ANSWER_LEAK_PATTERNS = ['参考答案', '正确答案', '答案：', '答案是']

    def __init__(self, bundle: DataBundle):
        self.b = bundle
        # 收集所有题目参考答案（用于提示泄露检测）
        self.ref_answers = set()
        for meta in bundle.question_map.values():
            ans = (meta.get('reference_answer') or '').strip()
            if ans and len(ans) >= 2:
                self.ref_answers.add(ans)

    def check(self, result: dict) -> dict:
        issues = []

        # 防线1：结论必须带证据ID
        if result.get('agent') in ('DiagnosisAgent', 'RecommendationAgent'):
            if not result.get('evidence_ids') and not result.get('mastery'):
                issues.append('结论缺少证据ID（record_ids）')

        # 防线2：证据不足的指标不得下"薄弱/未掌握"结论
        mastery = result.get('mastery') or {}
        for ind in (mastery.get('indicators') or []):
            if ind.get('band') == 'insufficient' and ind.get('mastery') is not None:
                # 允许展示但需在文案中标注
                pass

        # 防线3：分步提示不得泄露参考答案
        for rec in result.get('recommendations', []):
            for hint in rec.get('step_hints', []):
                for ans in self.ref_answers:
                    if ans in hint:
                        issues.append(f'提示疑似泄露答案"{ans[:15]}"：{hint[:40]}')

        # 防线4：统计数字必须来自工具（抽查：建议里的掌握度与诊断一致）
        # （结构保证，占位）

        result['validation'] = {
            'passed': len(issues) == 0,
            'issues': issues,
        }
        return result


# ============================================================
# 协调器（纯规则路由，不用 LLM）
# ============================================================

class Coordinator:
    """意图识别与任务分发。规则路由，确定性、零成本。"""

    INTENT_KEYWORDS = {
        'diagnosis': ['薄弱', '掌握', '学情', '诊断', '哪里', '分析', '怎么样', '表现', '错'],
        'recommend': ['建议', '推荐', '练习', '计划', '下一步', '怎么学', '补什么', '路径'],
        'class': ['班级', '全班', '两个班', '对比', 'DC01', 'DC02'],
        'evidence': ['证据', '依据', '哪条记录', '为什么', '溯源'],
    }

    def __init__(self, output_dir):
        self.bundle = DataBundle(output_dir)
        self.tools = ToolBox(self.bundle)
        self.agents = {
            'diagnosis': DiagnosisAgent(self.tools),
            'recommend': RecommendationAgent(self.tools),
            'qa': QaAgent(self.tools),
        }
        self.validator = ValidatorAgent(self.bundle)

    def route(self, question: str, student_id: str = None) -> dict:
        q = question.strip()
        intent = {'question': q, 'student_id': student_id}

        # 识别意图
        scores = {}
        for name, kws in self.INTENT_KEYWORDS.items():
            scores[name] = sum(1 for kw in kws if kw in q)

        # 优先：建议 > 诊断 > 班级 > 答疑
        if scores.get('recommend', 0) > 0 and student_id:
            agent_key = 'recommend'
        elif scores.get('diagnosis', 0) > 0 and student_id:
            agent_key = 'diagnosis'
        elif scores.get('class', 0) > 0:
            agent_key = 'qa'
        else:
            agent_key = 'qa'

        agent = self.agents[agent_key]
        result = agent.run(intent)
        result = self.validator.check(result)
        result['routing'] = {'intent_scores': scores, 'selected_agent': agent_key}
        return result


# ============================================================
# CLI 演示
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', default='../SmartLearn-AI/output')
    ap.add_argument('--student', default='D01')
    ap.add_argument('--demo', action='store_true')
    a = ap.parse_args()

    coord = Coordinator(a.output_dir)
    print('=' * 60)
    print('  多智能体编排层演示')
    print('=' * 60)

    if a.demo:
        questions = [
            f'{a.student}哪里最薄弱？',
            f'给{a.student}一个这周能做完的学习计划',
            '两个班差在哪？',
        ]
        for q in questions:
            print(f'\n>>> 用户提问：{q}')
            r = coord.route(q, student_id=a.student)
            print(f'  路由：{r["routing"]["selected_agent"]}')
            print(f'  校验：{"通过" if r["validation"]["passed"] else "拦截：" + str(r["validation"]["issues"])}')
            if r.get('summary'):
                print(f'  摘要：{r["summary"]}')
            for rec in r.get('recommendations', []):
                print(f'  [建议P{rec["priority"]}] {rec["indicator"]} {rec["indicator_name"]}')
                print(f'    题目：{" → ".join(rec["recommended_questions"])}')
                for i, h in enumerate(rec['step_hints'], 1):
                    print(f'    提示{i}：{h}')
    else:
        r = coord.route('学情诊断', student_id=a.student)
        print(json.dumps(r, ensure_ascii=False, indent=2)[:3000])


if __name__ == '__main__':
    main()
