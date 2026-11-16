# -*- coding: utf-8 -*-
"""
智慧学伴 - 模块3：错因诊断引擎
================================
职责：对学生每条错误记录进行错因诊断，输出结构化诊断结果

两层架构：
  第一层（规则引擎）：基于评分点得分模式自动分类错误类型，不调API，秒出全部结果
  第二层（LLM诊断）：对解答题调用DeepSeek做语义级深度分析，需要API Key

6种错误类型：
  C1 概念误解  - 不理解题意或核心概念
  C2 符号错误  - 负数运算符号出错（如不等号方向不变）
  C3 计算失误  - 基本运算出错（如2×4+3=14）
  C4 步骤遗漏  - 跳步或缺少关键步骤（如缺少检验）
  C5 表达不规范 - 结果格式不对或缺少单位
  C6 级联错误  - 前一步错误导致后续全错

输入：cleaned_data.json（由模块1生成）
输出：
  - error_diagnosis.json     全部错误记录的诊断结果（规则层+LLM层）
  - error_pattern_summary.json  错误模式汇总统计

运行方式：
  # 仅运行规则层（不需要API Key，秒出结果）
  python 03_error_diagnosis.py --rule-only

  # 运行全部（包括LLM深度诊断，需要API Key）
  python 03_error_diagnosis.py --api-key YOUR_DEEPSEEK_API_KEY
"""

import json
import os
import sys
import re
from collections import defaultdict, Counter

# ============================================================
# 配置区
# ============================================================

OUTPUT_DIR = os.environ.get("SS_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
# DeepSeek API配置（运行LLM层时需要）
DEEPSEEK_API_KEY = ""  # 在这里填你的API Key，或通过命令行参数传入
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

# 错误类型定义
ERROR_TYPES = {
    'C1': {'name': '概念误解', 'description': '不理解题意或核心概念，如将"连续整数n-1,n,n+1"写成"n-1,n,n+2"'},
    'C2': {'name': '符号错误', 'description': '负数运算符号出错，如除以负数时不等号方向不变'},
    'C3': {'name': '计算失误', 'description': '基本运算出错，如2×4+3算成14'},
    'C4': {'name': '步骤遗漏', 'description': '跳步或缺少关键步骤，如解答题缺少检验步骤'},
    'C5': {'name': '表达不规范', 'description': '结果格式不对或缺少单位'},
    'C6': {'name': '级联错误', 'description': '前一步错误导致后续步骤全部不得分'}
}


# ============================================================
# 第一层：规则引擎（不需要API）
# ============================================================

def parse_scoring_points(scoring_point_str):
    """
    解析评分点得分字符串，返回 {评分点ID: 得分} 字典
    示例输入: "Q043P1=1；Q043P2=0；Q043P3=0"
    输出: {'Q043P1': 1, 'Q043P2': 0, 'Q043P3': 0}
    """
    if not scoring_point_str:
        return {}
    points = {}
    for part in scoring_point_str.split('；'):
        part = part.strip()
        if '=' in part:
            pid, score = part.split('=')
            try:
                points[pid.strip()] = int(score.strip())
            except ValueError:
                continue
    return points


def classify_by_rules(record, scoring_points_def):
    """
    基于评分点得分模式，用规则判断错误类型

    规则逻辑：
    1. 填空题/选择题答错 → 看具体题目特征判断
    2. 解答题：
       - 全部评分点不得分 → 可能是概念误解或完全不会
       - 前面得分后面不得分 → 可能是级联错误
       - 最后一个评分点不得分 → 可能是步骤遗漏或表达不规范
       - 中间某个评分点不得分但前后得分 → 局部错误
    """

    question_type = record.get('question_type', '')
    score = record.get('score', 0)
    full_score = record.get('full_score', 0)
    point_scores = parse_scoring_points(record.get('scoring_point_scores', ''))
    student_answer = record.get('student_answer', '')

    diagnosis = {
        'record_id': record.get('record_id'),
        'student_id': record.get('student_id'),
        'question_id': record.get('question_id'),
        'indicator_id': record.get('indicator_id'),
        'question_type': question_type,
        'score': score,
        'full_score': full_score,
        'student_answer': student_answer,
        'error_type': None,
        'error_type_code': None,
        'error_description': '',
        'diagnosis_source': 'rule',
        'confidence': 'medium'  # 规则层置信度为medium，LLM层为high
    }

    # 如果全对，不算错误
    if score == full_score:
        diagnosis['error_type'] = '无错误'
        diagnosis['error_type_code'] = 'OK'
        return diagnosis

    # --- 填空题/选择题的错误诊断 ---
    if question_type in ['填空题', '选择题']:
        # 根据指标判断可能的错误类型
        indicator = record.get('indicator_id', '')
        ref_answer = record.get('reference_answer', '')

        # T03I1相关题目答错 → 很可能是符号错误（不等号方向）
        if indicator == 'T03I1' and ref_answer and student_answer:
            ref_dir = None
            stu_dir = None
            for d in ['>', '<', '>=', '<=']:
                if d in ref_answer:
                    ref_dir = d
                if d in student_answer:
                    stu_dir = d
            if ref_dir and stu_dir and ref_dir != stu_dir:
                diagnosis['error_type'] = ERROR_TYPES['C2']['name']
                diagnosis['error_type_code'] = 'C2'
                diagnosis['error_description'] = f'不等号方向错误：参考答案为{ref_answer}，学生答案为{student_answer}，方向相反'
                return diagnosis

        # 代数式计算类 → 可能是计算失误
        if indicator in ['T01I1', 'T01I2']:
            diagnosis['error_type'] = ERROR_TYPES['C3']['name']
            diagnosis['error_type_code'] = 'C3'
            diagnosis['error_description'] = f'代数式运算结果错误：学生答案为{student_answer}，参考答案为{ref_answer}'
            return diagnosis

        # 默认分类
        diagnosis['error_type'] = ERROR_TYPES['C1']['name']
        diagnosis['error_type_code'] = 'C1'
        diagnosis['error_description'] = f'答案错误：学生答案为{student_answer}，参考答案为{ref_answer}'
        return diagnosis

    # --- 解答题的错误诊断 ---
    if question_type == '解答题':
        if not point_scores:
            diagnosis['error_type'] = ERROR_TYPES['C1']['name']
            diagnosis['error_type_code'] = 'C1'
            diagnosis['error_description'] = '无评分点数据，无法细分'
            return diagnosis

        # 将评分点按编号排序
        sorted_points = sorted(point_scores.items())
        scores_list = [s for _, s in sorted_points]
        total_points = len(scores_list)

        if total_points == 0:
            diagnosis['error_type'] = '未知'
            diagnosis['error_type_code'] = 'UNKNOWN'
            return diagnosis

        # 情况1：全部不得分
        if all(s == 0 for s in scores_list):
            diagnosis['error_type'] = ERROR_TYPES['C1']['name']
            diagnosis['error_type_code'] = 'C1'
            diagnosis['error_description'] = '所有评分点均不得分，可能完全不理解题目或核心概念'
            return diagnosis

        # 情况2：只有第一个评分点得分，后面全错（级联错误）
        if scores_list[0] == 1 and all(s == 0 for s in scores_list[1:]):
            diagnosis['error_type'] = ERROR_TYPES['C6']['name']
            diagnosis['error_type_code'] = 'C6'
            # 尝试更精确地判断级联的源头
            first_wrong_idx = next((i for i, s in enumerate(scores_list) if s == 0), -1)
            point_names = scoring_points_def.split('\n') if scoring_points_def else []
            if first_wrong_idx < len(point_names):
                diagnosis['error_description'] = f'第{first_wrong_idx+1}步正确但第{first_wrong_idx+2}步出错，导致后续步骤全部不得分（级联错误）'
            else:
                diagnosis['error_description'] = '前半部分正确，中间出错导致后续全错（级联错误）'
            return diagnosis

        # 情况3：前面得分，最后一个评分点不得分（步骤遗漏或表达不规范）
        if all(s == 1 for s in scores_list[:-1]) and scores_list[-1] == 0:
            # 判断是步骤遗漏还是表达不规范
            last_point_name = ''
            point_names = scoring_points_def.split('\n') if scoring_points_def else []
            if point_names:
                last_point_name = point_names[-1].strip()

            if any(kw in last_point_name for kw in ['单位', '结果', '写出', '表示']):
                diagnosis['error_type'] = ERROR_TYPES['C5']['name']
                diagnosis['error_type_code'] = 'C5'
                diagnosis['error_description'] = f'前面步骤正确，但最后一步表达不规范：{last_point_name}'
            elif any(kw in last_point_name for kw in ['检验', '核对', '核验', '验证']):
                diagnosis['error_type'] = ERROR_TYPES['C4']['name']
                diagnosis['error_type_code'] = 'C4'
                diagnosis['error_description'] = f'前面步骤正确，但缺少检验/核验步骤：{last_point_name}'
            else:
                diagnosis['error_type'] = ERROR_TYPES['C4']['name']
                diagnosis['error_type_code'] = 'C4'
                diagnosis['error_description'] = f'前面步骤正确，但最后一步未完成：{last_point_name}'
            return diagnosis

        # 情况4：中间有某个评分点不得分，但前后都有得分
        wrong_indices = [i for i, s in enumerate(scores_list) if s == 0]
        correct_indices = [i for i, s in enumerate(scores_list) if s == 1]

        if wrong_indices and correct_indices:
            # 中间步骤出错
            point_names = scoring_points_def.split('\n') if scoring_points_def else []
            wrong_details = []
            for idx in wrong_indices:
                if idx < len(point_names):
                    wrong_details.append(point_names[idx].strip())

            # 判断错误类型
            wrong_text = ' '.join(wrong_details)
            if any(kw in wrong_text for kw in ['方向', '反向', '变号', '负数']):
                diagnosis['error_type'] = ERROR_TYPES['C2']['name']
                diagnosis['error_type_code'] = 'C2'
            elif any(kw in wrong_text for kw in ['合并', '化简', '计算', '求出']):
                diagnosis['error_type'] = ERROR_TYPES['C3']['name']
                diagnosis['error_type_code'] = 'C3'
            else:
                diagnosis['error_type'] = ERROR_TYPES['C1']['name']
                diagnosis['error_type_code'] = 'C1'

            diagnosis['error_description'] = f'部分步骤正确，出错环节：{"; ".join(wrong_details)}'
            return diagnosis

    # 兜底
    diagnosis['error_type'] = '其他'
    diagnosis['error_type_code'] = 'OTHER'
    diagnosis['error_description'] = '无法自动分类，建议人工查看'
    return diagnosis


# ============================================================
# 第二层：LLM深度诊断（需要DeepSeek API）
# ============================================================

ERROR_DIAGNOSIS_PROMPT = """你是一位经验丰富的七年级数学教师，请分析以下学生的作答错误：

【题目】{question_text}
【参考答案】{reference_answer}
【参考解析】{reference_solution}
【评分标准】{scoring_points}

【学生答案】{student_answer}
【学生解答过程】{student_process}
【评分点得分】{point_scores}

请输出结构化诊断（JSON格式），包含以下字段：
{{
  "error_type": "错误类型，从以下选项中选择：概念误解/符号错误/计算失误/步骤遗漏/表达不规范/级联错误",
  "error_location": "错误出现在哪一步（具体描述）",
  "root_cause": "学生可能的思维误区（1-2句话）",
  "related_indicator": "该错误反映哪个观察指标的薄弱",
  "remediation_hint": "补救建议（1-2句话，不直接给答案）"
}}

请确保JSON格式正确，不要输出其他内容。"""


def diagnose_with_llm(record, api_key):
    """调用DeepSeek API对单条记录进行LLM深度诊断"""
    try:
        from openai import OpenAI
    except ImportError:
        print("  [警告] 未安装openai库，请运行: pip install openai")
        return None

    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    prompt = ERROR_DIAGNOSIS_PROMPT.format(
        question_text=record.get('question_text', ''),
        reference_answer=record.get('reference_answer', ''),
        reference_solution=record.get('reference_solution', ''),
        scoring_points=record.get('scoring_points_def', ''),
        student_answer=record.get('student_answer', ''),
        student_process=record.get('student_process', '无解答过程'),
        point_scores=record.get('scoring_point_scores', '')
    )

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        result_text = response.choices[0].message.content.strip()

        # 尝试解析JSON
        # 去除可能的markdown代码块标记
        result_text = re.sub(r'^```json\s*', '', result_text)
        result_text = re.sub(r'\s*```$', '', result_text)

        result = json.loads(result_text)
        result['diagnosis_source'] = 'llm'
        result['confidence'] = 'high'
        return result

    except json.JSONDecodeError:
        return {
            'error_type': '解析失败',
            'raw_response': result_text,
            'diagnosis_source': 'llm',
            'confidence': 'low'
        }
    except Exception as e:
        print(f"  [API错误] {e}")
        return None


# ============================================================
# 主流程
# ============================================================

def run_diagnosis(data_model, api_key=None, rule_only=False):
    """
    运行错因诊断

    参数:
      data_model: cleaned_data.json的内容
      api_key: DeepSeek API Key（None则只运行规则层）
      rule_only: True则只运行规则层
    """
    print("=" * 50)
    print("模块3：错因诊断引擎")
    print("=" * 50)

    records = data_model['records']
    question_map = data_model['question_indicator_map']

    # 筛选错误记录（得分<满分）
    error_records = [r for r in records if r['score'] < r['full_score']]
    print(f"\n  总记录数: {len(records)}")
    print(f"  错误记录数: {len(error_records)}")

    # ===== 第一层：规则引擎 =====
    print(f"\n  第一层：规则引擎诊断中...")
    diagnoses = []
    for r in error_records:
        qid = r.get('question_id', '')
        q_info = question_map.get(qid, {})
        scoring_points_def = q_info.get('scoring_points', '')

        diagnosis = classify_by_rules(r, scoring_points_def)
        diagnoses.append(diagnosis)

    # 统计错误类型分布
    type_counter = Counter(d['error_type_code'] for d in diagnoses)
    print(f"  规则引擎完成，错误类型分布:")
    for code, count in type_counter.most_common():
        type_name = ERROR_TYPES.get(code, {}).get('name', code)
        print(f"    {code} ({type_name}): {count} 条")

    # ===== 第二层：LLM深度诊断（可选） =====
    if not rule_only and api_key:
        print(f"\n  第二层：LLM深度诊断中（仅对解答题）...")
        # 只对有解答过程的解答题做LLM诊断
        llm_targets = [
            (i, r) for i, r in enumerate(error_records)
            if r.get('question_type') == '解答题'
               and r.get('student_process')
               and r.get('student_process').strip()
        ]
        print(f"  待LLM诊断的解答题记录: {len(llm_targets)} 条")

        for idx, (i, r) in enumerate(llm_targets):
            print(f"    [{idx+1}/{len(llm_targets)}] 诊断 {r['record_id']} "
                  f"({r['student_id']}-{r['question_id']})...", end=' ')

            llm_result = diagnose_with_llm(r, api_key)
            if llm_result:
                # 合并LLM结果到诊断中
                diagnoses[i].update({
                    'llm_error_type': llm_result.get('error_type'),
                    'llm_error_location': llm_result.get('error_location'),
                    'llm_root_cause': llm_result.get('root_cause'),
                    'llm_related_indicator': llm_result.get('related_indicator'),
                    'llm_remediation_hint': llm_result.get('remediation_hint'),
                    'llm_confidence': llm_result.get('confidence')
                })
                print(f"完成: {llm_result.get('error_type', '?')}")
            else:
                print("失败，保留规则层结果")

            # 简单限速，避免API过载
            import time
            time.sleep(0.5)
    elif not rule_only and not api_key:
        print(f"\n  [提示] 未提供API Key，跳过LLM诊断层")
        print(f"  如需运行LLM诊断: python 03_error_diagnosis.py --api-key YOUR_KEY")

    return diagnoses


def build_error_pattern_summary(diagnoses, data_model):
    """
    构建错误模式汇总统计
    """
    print(f"\n  构建错误模式汇总...")

    summary = {
        'total_errors': len(diagnoses),
        'by_error_type': {},
        'by_indicator': {},
        'by_question': {},
        'critical_findings': []
    }

    # 按错误类型统计
    type_counter = Counter(d['error_type_code'] for d in diagnoses)
    for code, count in type_counter.most_common():
        type_name = ERROR_TYPES.get(code, {}).get('name', code)
        summary['by_error_type'][code] = {
            'name': type_name,
            'count': count,
            'percentage': round(count / len(diagnoses) * 100, 1)
        }

    # 按指标统计错误
    indicator_errors = defaultdict(lambda: {'total': 0, 'by_type': Counter()})
    for d in diagnoses:
        ind = d.get('indicator_id', '')
        if ind:
            indicator_errors[ind]['total'] += 1
            indicator_errors[ind]['by_type'][d['error_type_code']] += 1

    for ind, info in indicator_errors.items():
        summary['by_indicator'][ind] = {
            'total_errors': info['total'],
            'type_distribution': dict(info['by_type'].most_common())
        }

    # 按题目统计错误
    question_errors = defaultdict(lambda: {'total': 0, 'error_students': []})
    for d in diagnoses:
        qid = d.get('question_id', '')
        if qid:
            question_errors[qid]['total'] += 1
            question_errors[qid]['error_students'].append(d.get('student_id'))

    # 找高频错题
    high_freq_errors = sorted(question_errors.items(), key=lambda x: x[1]['total'], reverse=True)
    for qid, info in high_freq_errors[:10]:
        summary['by_question'][qid] = {
            'error_count': info['total'],
            'error_rate': round(info['total'] / 40 * 100, 1),  # 粗略估计
            'error_students': info['error_students']
        }

    # 关键发现
    # 发现1: 0%得分率的评分点
    stats_path = os.path.join(OUTPUT_DIR, 'statistics.json')
    if os.path.exists(stats_path):
        with open(stats_path, 'r', encoding='utf-8') as f:
            stats = json.load(f)
        for pid, pinfo in stats.get('by_scoring_point', {}).items():
            if pinfo.get('score_rate', 1) == 0:
                summary['critical_findings'].append({
                    'type': 'zero_score_rate',
                    'point_id': pid,
                    'description': f'{pid} 得分率为0%（{pinfo["total"]}人全错），属于全班共性难点',
                    'severity': 'critical'
                })

    # 发现2: 顽固性错误（跨节点同一题答案相同且都错）
    for change in stats.get('cross_node_changes', []) if os.path.exists(stats_path) else []:
        if change['change_type'] == 'persistent_error':
            summary['critical_findings'].append({
                'type': 'persistent_error',
                'student_id': change['student_id'],
                'question_id': change['question_id'],
                'description': f'{change["student_id"]}在{change["question_id"]}上两次答题答案相同且都错（顽固性错误）',
                'severity': 'high'
            })

    # 发现3: 级联错误
    cascade_count = type_counter.get('C6', 0)
    if cascade_count > 0:
        summary['critical_findings'].append({
            'type': 'cascade_pattern',
            'description': f'发现{cascade_count}条级联错误：前一步出错导致后续步骤全部不得分',
            'severity': 'medium',
            'implication': '教学中应重点攻克关键步骤，避免级联失分'
        })

    return summary


# ============================================================
# 主函数
# ============================================================

def main():
    # 解析命令行参数
    rule_only = '--rule-only' in sys.argv
    api_key = None
    if '--api-key' in sys.argv:
        idx = sys.argv.index('--api-key')
        if idx + 1 < len(sys.argv):
            api_key = sys.argv[idx + 1]
    elif DEEPSEEK_API_KEY:
        api_key = DEEPSEEK_API_KEY

    # 加载数据
    cleaned_path = os.path.join(OUTPUT_DIR, 'cleaned_data.json')
    print(f"\n加载模块1的输出数据...")
    with open(cleaned_path, 'r', encoding='utf-8') as f:
        data_model = json.load(f)
    print(f"  加载完成: {data_model['meta']['total_records']} 条记录")

    # 运行诊断
    diagnoses = run_diagnosis(data_model, api_key=api_key, rule_only=rule_only)

    # 构建错误模式汇总
    error_summary = build_error_pattern_summary(diagnoses, data_model)

    # 输出文件
    print(f"\n  输出结果文件:")

    diagnosis_path = os.path.join(OUTPUT_DIR, 'error_diagnosis.json')
    with open(diagnosis_path, 'w', encoding='utf-8') as f:
        json.dump(diagnoses, f, ensure_ascii=False, indent=2)
    print(f"    -> {diagnosis_path}")

    summary_path = os.path.join(OUTPUT_DIR, 'error_pattern_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(error_summary, f, ensure_ascii=False, indent=2)
    print(f"    -> {summary_path}")

    # 人类可读摘要
    txt_path = os.path.join(OUTPUT_DIR, 'error_diagnosis_summary.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("智慧学伴 - 错因诊断摘要\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"错误记录总数: {len(diagnoses)}\n\n")

        f.write("错误类型分布:\n")
        for code, info in error_summary['by_error_type'].items():
            f.write(f"  {code} ({info['name']}): {info['count']}条 ({info['percentage']}%)\n")

        f.write("\n高频错题TOP10:\n")
        for qid, info in list(error_summary['by_question'].items())[:10]:
            f.write(f"  {qid}: {info['error_count']}人答错\n")

        f.write("\n关键发现:\n")
        for finding in error_summary['critical_findings']:
            f.write(f"  [{finding['severity']}] {finding['description']}\n")

        f.write("\n各指标错误类型分布:\n")
        for ind, info in error_summary['by_indicator'].items():
            f.write(f"  {ind} (共{info['total_errors']}条错误):\n")
            for etype, count in info['type_distribution'].items():
                type_name = ERROR_TYPES.get(etype, {}).get('name', etype)
                f.write(f"    {etype} ({type_name}): {count}条\n")

    print(f"    -> {txt_path}")

    # 打印关键发现
    print("\n" + "=" * 50)
    print("关键发现:")
    print("=" * 50)
    for finding in error_summary['critical_findings']:
        print(f"  [{finding['severity']}] {finding['description']}")

    print("\n" + "=" * 60)
    print("  模块3 完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
