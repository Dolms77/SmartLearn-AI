# -*- coding: utf-8 -*-
"""
智慧学伴 - 07V2 多智能体协同系统（升级版）
====================================================
相比 V1 的升级：
  1. 多轮对话记忆：支持"他呢""再详细点"等指代消解与上下文延续
  2. Agent 协作链：诊断Agent结果自动流入建议Agent（级联调用，不是各干各的）
  3. 新增讲评稿Agent（LectureAgent）：教师端"下周怎么讲"直接生成结构化讲评稿
  4. 执行轨迹 Trace：每步Agent调用记录成日志，答辩演示"智能体思考过程"的素材
  5. 规则确定数据事实，建议摘要可由本地 Ollama 动态生成
  6. 意图识别升级：复合意图自动级联（"D01哪里薄弱，该练什么"→诊断+建议链）

运行：
  python 07_multi_agent.py --demo
  python 07_multi_agent.py --chat
  python 07_multi_agent.py --demo --no-llm
"""

import json
import os
import re
import argparse
import sys
from collections import defaultdict, Counter
from datetime import datetime

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ui import llm

MIN_EVIDENCE = 3
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

ATTRIBUTION = {
    'C1': "对概念本身的理解还没建立——记住了操作步骤，没有理解为什么这样操作。靠多做题收效慢，需回到直观理解。",
    'C2': "对符号规则处于'知道但不会用'状态——课堂上能复述，独立解题就遗漏。需要在出错的当下被拦住一次。",
    'C3': "思路对但运算准确性不稳定。适合放慢速度、逐步验算，不适合加大题量。",
    'C4': "解题结构不完整——缺检验、缺解释。学生把'解出答案'当终点，还没建立完整作答习惯。",
    'C5': "表达规范问题——单位、格式、结论完整性，最容易通过示范和对照纠正。",
    'C6': "一步卡壳、满盘皆输。最优先的不是学新内容，而是单独攻克卡壳的那一步。",
}


# ============================================================
# 数据层
# ============================================================

class Bundle:
    def __init__(self, output_dir):
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
        self.task3 = load('task3_recommendations.json', {})
        self.records = self.cleaned.get('records', [])
        self.question_map = self.cleaned.get('question_indicator_map', {})
        self.records_by_student = defaultdict(list)
        for r in self.records:
            self.records_by_student[r['student_id']].append(r)
        self.students = {sid for sid in self.profiles}
        self.by_indicator_q = defaultdict(list)
        for qid, m in self.question_map.items():
            if m.get('indicator'):
                self.by_indicator_q[m['indicator']].append(qid)


# ============================================================
# 执行轨迹（答辩演示素材）
# ============================================================

class Trace:
    """记录多Agent协作的每一步，生成可回放的执行日志"""

    def __init__(self):
        self.steps = []

    def log(self, agent, action, detail, output_summary):
        step = {
            'step': len(self.steps) + 1,
            'time': datetime.now().strftime('%H:%M:%S.%f')[:-3],
            'agent': agent, 'action': action,
            'detail': detail, 'output': output_summary,
        }
        self.steps.append(step)

    def render(self):
        """渲染成可读轨迹（供界面/答辩演示）"""
        lines = []
        for s in self.steps:
            lines.append(f"[{s['step']}] {s['agent']} · {s['action']}")
            if s['detail']:
                lines.append(f"     输入：{s['detail'][:60]}")
            lines.append(f"     输出：{s['output'][:60]}")
        return '\n'.join(lines)

    def to_dict(self):
        return {'steps': self.steps}


# ============================================================
# 协调器（多轮对话 + 指代消解 + 复合意图级联）
# ============================================================

class Coordinator:
    """
    升级点：
    - 会话记忆：记住当前学生/最近话题
    - 指代消解："他呢"→继承上一个学生；"详细点"→重发上一个意图
    - 复合意图：一句话含诊断+建议需求时，自动级联两个Agent
    """

    INTENT_RULES = [
        ('lecture', ['讲评', '下周怎么讲', '课堂', '给全班', '讲什么课']),
        ('recommend', ['建议', '推荐', '练习', '计划', '怎么学', '补什么', '练什么', '路径', '安排']),
        ('diagnosis', ['薄弱', '掌握', '学情', '诊断', '哪里', '分析', '表现', '错', '怎么样', '怎么']),
        ('evidence', ['证据', '依据', '哪条记录', '为什么', '溯源', '详细']),
        ('class', ['班级', '全班', '两个班', '对比', 'DC01', 'DC02', '差在哪']),
    ]
    STUDENT_RE = re.compile(r'D\d{2}')
    DETAIL_RE = re.compile(r'详细|具体|再说说|展开')

    def __init__(self, bundle: Bundle, use_llm=True):
        self.b = bundle
        self.agents = {
            'diagnosis': DiagnosisAgent(bundle),
            'recommend': RecommendationAgent(bundle, use_llm=use_llm),
            'lecture': LectureAgent(bundle),
            'class': ClassAgent(bundle),
        }
        self.validator = ValidatorAgent(bundle)
        # 会话记忆
        self.memory = {'current_student': None, 'last_intent': None,
                      'last_answer': None}
        self.trace = Trace()

    # ---------- 意图识别 ----------
    def parse(self, question: str) -> dict:
        intents = []
        for name, kws in self.INTENT_RULES:
            if any(kw in question for kw in kws):
                intents.append(name)
        # 复合意图：诊断+建议共存 → 级联
        if 'recommend' in intents and 'diagnosis' in intents:
            intents = ['diagnosis', 'recommend']  # 按级联顺序
        # 学生识别（校验存在性）
        m = self.STUDENT_RE.search(question)
        sid = None
        if m:
            cand = m.group(0)
            if cand in self.b.students:
                sid = cand
        # 指代消解：无新学生ID但上下文提到学生时，继承上一学生
        if sid is None and (not m) and ('他' in question or '她' in question
                                        or '这个学生' in question or '该生' in question):
            sid = self.memory.get('current_student')
        detail = bool(self.DETAIL_RE.search(question))
        if not intents:
            intents = ['diagnosis'] if sid else ['class']
        return {'question': question, 'intents': intents,
                'student_id': sid, 'detail': detail}

    # ---------- 调度执行 ----------
    def run(self, question: str) -> dict:
        self.trace = Trace()
        intent = self.parse(question)
        self.trace.log('Coordinator', '意图识别',
                       question,
                       f"意图={intent['intents']} 学生={intent['student_id']} 复合级联={len(intent['intents'])>1}")

        if intent['student_id']:
            if intent['student_id'] not in self.b.students:
                return {'error': f"未找到学生 {intent['student_id']}"}
            self.memory['current_student'] = intent['student_id']

        results, chain_context = [], {}
        for i, agent_key in enumerate(intent['intents']):
            agent = self.agents.get(agent_key) or self.agents['diagnosis']
            # 协作链：上一Agent的输出注入下一Agent
            if i > 0:
                chain_context['prev_result'] = results[-1]
            r = agent.run(intent, chain_context, self.trace)
            r = self.validator.check(r, self.trace)
            results.append(r)

        self.memory['last_intent'] = intent['intents']
        self.memory['last_answer'] = results
        return {
            'question': question, 'routing': intent, 'results': results,
            'trace': self.trace.to_dict(), 'trace_text': self.trace.render(),
        }


# ============================================================
# 专职 Agent（含协作链接口）
# ============================================================

class DiagnosisAgent:
    """诊断Agent：掌握度+错因+跨节点，输出带证据链"""

    def __init__(self, bundle: Bundle):
        self.b = bundle

    def run(self, intent, chain_ctx, trace):
        sid = intent['student_id']
        trace.log('DiagnosisAgent', '调取学生画像', f'{sid}',
                  '加载掌握度矩阵与错因记录')
        p = self.b.profiles.get(sid, {})
        details = p.get('indicator_details', {})
        sid_errors = [e for e in self.b.error_diag if e.get('student_id') == sid]

        indicators = []
        for ind, d in details.items():
            n = d.get('answer_count', 0)
            indicators.append({
                'indicator': ind, 'name': d.get('indicator_name', ''),
                'mastery': d.get('current_mastery'), 'n': n,
                'band': 'insufficient' if n < MIN_EVIDENCE else d.get('status'),
            })

        # 跨节点变化
        changes = [c for c in self.b.stats.get('cross_node_changes', [])
                   if c.get('student_id') == sid]
        persistent = [c for c in changes if c['change_type'] == 'persistent_error']
        improved = [c for c in changes if c['change_type'] == 'improved']

        # 摘要（教师口吻）
        weak = [i for i in indicators if i['band'] in ('weak', 'developing')
                and i['mastery'] is not None]
        weak.sort(key=lambda x: x['mastery'])
        insuf = [i['indicator'] for i in indicators if i['band'] == 'insufficient']
        parts = []
        if p.get('overall_mastery') is not None:
            parts.append(f"整体掌握度 {p['overall_mastery']:.0%}（仅计证据充分指标）。")
        if weak:
            parts.append(f"最需要关注的是 {weak[0]['indicator']}"
                         f"（{weak[0]['name']}），掌握度 {weak[0]['mastery']:.0%}，"
                         f"已有 {weak[0]['n']} 条作答证据。")
        if persistent:
            parts.append(f"发现顽固错误：{'、'.join(c['question_id'] for c in persistent)}，"
                         "两次同答案同错，建议面谈追问。")
        if improved:
            parts.append(f"进步信号：{'、'.join(c['question_id'] for c in improved)}。")
        if insuf:
            parts.append(f"{len(insuf)} 个指标证据不足不下结论，建议补充观察。")

        result = {
            'agent': 'DiagnosisAgent', 'student_id': sid,
            'summary': ''.join(parts), 'indicators': indicators,
            'error_count': len(sid_errors),
            'persistent_errors': persistent, 'improved': improved,
        }
        trace.log('DiagnosisAgent', '诊断完成', f'{sid}',
                  result['summary'][:50])
        return result


class RecommendationAgent:
    """建议Agent：支持两个入口——task3成果优先，无成果时现场生成；
    接收诊断Agent的级联上下文（协作链）"""

    def __init__(self, bundle: Bundle, use_llm=True):
        self.b = bundle
        self.use_llm = use_llm

    def run(self, intent, chain_ctx, trace):
        sid = intent['student_id']
        trace.log('RecommendationAgent', '加载建议', f'{sid}（task3优先）',
                  '读取task3_recommendations.json')

        # 入口1：正式成果文件（教育话语版）
        cases = self.b.task3.get('cases', {}) if self.b.task3 else {}
        allstu = self.b.task3.get('all_students', {}) if self.b.task3 else {}
        rec = cases.get(sid) or allstu.get(sid)

        # 协作链：若有诊断上下文，把诊断摘要并入
        prev = chain_ctx.get('prev_result') or {}
        if prev.get('agent') == 'DiagnosisAgent':
            trace.log('Coordinator', 'Agent协作链', '诊断结果→建议Agent',
                      f"注入摘要：{prev['summary'][:40]}")

        if rec:
            rec = dict(rec)
            rec['agent'] = 'RecommendationAgent'
            rec['source'] = 'task3_recommendations.json（教育话语版）'
            if prev.get('summary'):
                rec['diagnosis_link'] = prev['summary']
            self._generate_summary(rec, intent, trace)
            trace.log('RecommendationAgent', '建议输出', f'{sid}',
                      f"命中正式成果，{len(rec.get('recommendations', []))} 条建议")
            return rec

        # 入口2：现场生成（轻量版）
        trace.log('RecommendationAgent', '无正式成果，现场生成', f'{sid}', '走轻量路径')
        p = self.b.profiles.get(sid, {})
        details = p.get('indicator_details', {})
        done = {r['question_id'] for r in self.b.records_by_student.get(sid, [])}
        targets = [{'indicator': ind, 'name': d.get('indicator_name', ''),
                    'mastery': d.get('current_mastery'), 'n': d.get('answer_count', 0)}
                   for ind, d in details.items()
                   if d.get('status') in ('weak', 'developing')
                   and d.get('answer_count', 0) >= MIN_EVIDENCE]
        targets.sort(key=lambda x: x['mastery'])
        recs = []
        for i, t in enumerate(targets[:3], 1):
            cand = [q for q in self.b.by_indicator_q.get(t['indicator'], [])
                    if q not in done]
            if not cand:  # 该指标题已做完，则允许重做原错题（验证迁移）
                cand = self.b.by_indicator_q.get(t['indicator'], [])[:3]
                reason_extra = '（该指标题目已做过，安排重做原题验证迁移）'
            else:
                reason_extra = ''
                cand = cand[:3]
            recs.append({
                'priority': i, 'indicator': t['indicator'],
                'indicator_name': t['name'],
                'reason': f"掌握度 {t['mastery']:.0%}（n={t['n']}）{reason_extra}",
                'recommended_questions': cand,
                'step_hints': ["人工审校后补充分步提示（当前为现场轻量版）"],
                'follow_up_condition': "正确率≥80%进入下一优先级",
            })
        result = {
            'agent': 'RecommendationAgent', 'student_id': sid,
            'source': '现场轻量生成（建议运行08V2生成正式话语版）',
            'diagnosis_summary': f"整体掌握度 {p.get('overall_mastery', 0):.0%}",
            'recommendations': recs,
        }
        self._generate_summary(result, intent, trace)
        return result

    def _generate_summary(self, result, intent, trace):
        if not self.use_llm or not result.get('recommendations'):
            return
        if result.get('narrative_model'):
            trace.log('RecommendationAgent', '复用本地模型建议', '',
                      str(result['narrative_model']))
            return

        original = str(result.get('diagnosis_summary') or '').strip()
        if not original:
            return
        facts = {
            'question': intent.get('question', ''),
            'rule_summary': original,
            'recommendations': [
                {
                    'indicator_name': rec.get('indicator_name', ''),
                    'reason': rec.get('reason', ''),
                    'step_hints': rec.get('step_hints', [])[:2],
                }
                for rec in result.get('recommendations', [])[:3]
            ],
        }
        facts_text = json.dumps(facts, ensure_ascii=False)
        prompt = (
            "你是七年级数学教师。请根据给定的规则结论和建议，针对教师的问题写一段简短的"
            "教学建议摘要，最多 100 个汉字。不得增加输入中没有的事实、数字、题号、指标编号或答案；"
            "不要重复列举原始字段。只输出摘要正文。\n事实："
            + facts_text
        )
        try:
            summary = llm.generate_local_text(
                prompt, temperature=0.3, max_tokens=220).strip().strip('"')
            if not summary or len(summary) > 400:
                raise ValueError('模型摘要为空或过长')
            allowed_numbers = set(re.findall(r'\d+(?:\.\d+)?', facts_text))
            generated_numbers = set(re.findall(r'\d+(?:\.\d+)?', summary))
            if not generated_numbers.issubset(allowed_numbers):
                raise ValueError('模型摘要包含输入中没有的数字')
            token = r'\b(?:D\d{2}|T\d{2}I\d|Q\d+[A-Za-z]?)\b'
            allowed_ids = set(re.findall(token, facts_text))
            generated_ids = set(re.findall(token, summary))
            if not generated_ids.issubset(allowed_ids):
                raise ValueError('模型摘要包含输入中没有的学生、指标或题目编号')
            for meta in self.b.question_map.values():
                answer = (meta.get('reference_answer') or '').strip()
                if len(answer) >= 2 and answer in summary:
                    raise ValueError('模型摘要命中参考答案')
            result['rule_diagnosis_summary'] = original
            result['diagnosis_summary'] = summary
            result['narrative_model'] = llm.pick_model()
            trace.log('RecommendationAgent', '本地模型生成建议摘要', '',
                      str(result['narrative_model']))
        except Exception as exc:
            trace.log('RecommendationAgent', '本地模型不可用，保留规则摘要',
                      type(exc).__name__, str(exc)[:160])


class LectureAgent:
    """讲评稿Agent（教师端新增）：一键生成下周讲评建议"""

    def __init__(self, bundle: Bundle):
        self.b = bundle

    def run(self, intent, chain_ctx, trace):
        trace.log('LectureAgent', '汇总班级数据', 'DC01+DC02',
                  '统计+错因+评分点')
        stats = self.b.stats
        esum = self.b.error_summary

        # 最薄弱评分点（含样本量，防以偏概全）
        points = sorted(stats.get('by_scoring_point', {}).items(),
                        key=lambda kv: kv[1].get('score_rate', 1))
        must_teach = []
        for pid, info in points[:5]:
            n = info.get('total', 0)
            rate = info.get('score_rate', 1)
            note = (f"{rate*100:.0f}%（n={n}）" +
                    ("，样本较小仅作参考" if n < 10 else ""))
            must_teach.append({'point': pid, 'rate_note': note})

        # 两班差异
        by_ct = stats.get('by_class_theme', {})
        gaps = []
        for t in ['T01', 'T02', 'T03']:
            r1 = by_ct.get(f'DC01-{t}', {}).get('score_rate')
            r2 = by_ct.get(f'DC02-{t}', {}).get('score_rate')
            if r1 is not None and r2 is not None and abs(r1 - r2) >= 0.05:
                gaps.append({'theme': t, 'gap': f"{abs(r1-r2)*100:.1f}pt",
                             'weaker': 'DC02' if r1 > r2 else 'DC01'})

        # 高频错误类型
        by_type = esum.get('by_error_type', {})

        lecture = {
            'agent': 'LectureAgent',
            'title': '下周讲评建议（自动生成草稿，供教师修改）',
            'must_teach': must_teach[:3],
            'class_gaps': gaps,
            'error_focus': {k: v.get('count') for k, v in list(by_type.items())[:3]},
            'teaching_suggestion': (
                "建议用15分钟集中攻克最薄弱评分点对应的知识点（而非整套讲题）；"
                "对级联错误多的班级，示范'卡点暂停'解题习惯；"
                "两班差异大的主题建议分层布置作业。"),
            'warning': "以上基于作答样本生成，小样本项已标注，请教师结合课堂实际调整。",
        }
        trace.log('LectureAgent', '讲评稿生成', '全班',
                  f"必讲{len(must_teach[:3])}个评分点，班差{len(gaps)}项")
        return lecture


class ClassAgent:
    """班级对比Agent"""

    def __init__(self, bundle: Bundle):
        self.b = bundle

    def run(self, intent, chain_ctx, trace):
        trace.log('ClassAgent', '班级对比', 'DC01 vs DC02', '统计对比')
        by_ct = self.b.stats.get('by_class_theme', {})
        comp = {}
        for key, v in by_ct.items():
            cls, theme = key.split('-')
            comp.setdefault(cls, {})[theme] = {
                'rate': v.get('score_rate'), 'n': v.get('count')}
        return {'agent': 'ClassAgent', 'comparison': comp}


class ValidatorAgent:
    """校验Agent：四道防线"""

    def __init__(self, bundle):
        self.ref_answers = {(m.get('reference_answer') or '').strip()
                            for m in bundle.question_map.values()}
        self.ref_answers = {x for x in self.ref_answers if len(x) >= 2}

    def check(self, result, trace):
        issues = []
        if result.get('narrative_model') and result.get('rule_diagnosis_summary'):
            summary = result.get('diagnosis_summary') or ''
            if any(answer in summary for answer in self.ref_answers):
                result['diagnosis_summary'] = result['rule_diagnosis_summary']
                result.pop('narrative_model', None)
                issues.append('模型摘要命中参考答案，已恢复规则摘要')
        for rec in result.get('recommendations', []):
            for i, h in enumerate(rec.get('step_hints', [])):
                for ans in self.ref_answers:
                    if ans in h:
                        issues.append(f'提示泄露答案"{ans[:10]}"，已拦截')
                        rec['step_hints'][i] = "（已拦截：提示不得包含答案）请独立思考。"
        for ind in (result.get('indicators') or []):
            if ind.get('band') == 'insufficient' and ind.get('mastery') is not None:
                ind['_note'] = '证据不足，仅展示不作结论'
        result['validation'] = {'passed': len(issues) == 0, 'issues': issues}
        trace.log('ValidatorAgent', '输出校验', '四道防线',
                  '通过' if not issues else f'拦截{len(issues)}项')
        return result


# ============================================================
# CLI：演示 / 交互对话
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    default_output_dir = os.environ.get('SS_OUT') or os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'output'))
    ap.add_argument('--output-dir', default=default_output_dir)
    ap.add_argument('--demo', action='store_true')
    ap.add_argument('--chat', action='store_true')
    ap.add_argument('--no-llm', action='store_true',
                    help='禁用建议Agent的本地 Ollama 动态摘要')
    a = ap.parse_args()

    coord = Coordinator(Bundle(a.output_dir), use_llm=not a.no_llm)

    if a.demo:
        print('=' * 62)
        print('  多智能体协同系统 V2 演示')
        print('=' * 62)
        demos = [
            'D01哪里最薄弱？',                                  # 诊断
            '给D01安排一个学习计划',                            # 建议（级联）
            'D01哪里薄弱，顺便说说该练什么',                     # 复合意图级联
            '他呢？',                                           # 指代消解
            '下周这个班该怎么讲？',                              # 讲评稿
        ]
        for q in demos:
            print(f'\n{"-"*60}\n用户：{q}')
            r = coord.run(q)
            for res in r['results']:
                print(f'   [{res.get("agent")}]')
                if res.get('summary'):
                    print(f'   {res["summary"]}')
                for rec in res.get('recommendations', [])[:1]:
                    print(f'   建议P{rec["priority"]} {rec["indicator"]}: '
                          f'题{rec.get("recommended_questions", [])}')
                if res.get('teaching_suggestion'):
                    print(f'   {res["teaching_suggestion"]}')
            print(f'\n   —— Agent执行轨迹 ——')
            print('   ' + r['trace_text'].replace('\n', '\n   '))

    elif a.chat:
        print('=' * 62)
        print('  交互对话模式（输入 q 退出）')
        print('=' * 62)
        while True:
            q = input('\n你：').strip()
            if q.lower() in ('q', 'quit', 'exit'):
                break
            r = coord.run(q)
            for res in r['results']:
                print(f'\n[{res.get("agent")}]')
                if res.get('summary'):
                    print(res['summary'])
                for rec in res.get('recommendations', []):
                    print(f'  优先级{rec["priority"]} {rec["indicator"]}: '
                          f'{"、".join(rec.get("recommended_questions", []))}')
            print('\n   [轨迹]', r['trace_text'].replace('\n', ' | ')[:200])
    else:
        print('使用 --demo 或 --chat 运行')


if __name__ == '__main__':
    main()
