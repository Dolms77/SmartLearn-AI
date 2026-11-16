# -*- coding: utf-8 -*-
"""
智慧学伴 - 模块2：BKT知识追踪模型
================================
职责：对每个学生在9个观察指标上的掌握概率进行动态建模

原理：贝叶斯知识追踪（Bayesian Knowledge Tracing）
  - 每个知识点有一个"掌握概率"，初始值基于该指标的全局得分率
  - 每次答题后，根据对错更新掌握概率
  - 答对了→掌握概率上升；答错了→掌握概率下降
  - 同时考虑"学习效应"：每次练习都可能学会新东西

输入：cleaned_data.json + statistics.json（由模块1生成）
输出：
  - mastery_matrix.json    40学生×9指标的掌握概率矩阵
  - student_profiles.json  每学生的知识追踪画像（含推荐依据）

运行方式：
  python 02_bkt_model.py

注意：这个模块不调任何API，纯数学计算，秒出结果。
"""

import json
import os
from collections import defaultdict

# ============================================================
# 配置区
# ============================================================

OUTPUT_DIR = os.environ.get("SS_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
# 9个观察指标
INDICATORS = [
    'T01I1', 'T01I2', 'T01I3',
    'T02I1', 'T02I2', 'T02I3',
    'T03I1', 'T03I2', 'T03I3'
]

# 指标名称映射（用于输出可读性）
INDICATOR_NAMES = {
    'T01I1': '表示数量关系并代入求值',
    'T01I2': '识别同类项、去括号并化简',
    'T01I3': '用整式解释具体问题',
    'T02I1': '运用等式性质解一元一次方程',
    'T02I2': '用消元法解二元一次方程组',
    'T02I3': '列方程或方程组解决实际问题',
    'T03I1': '运用不等式性质求解',
    'T03I2': '求两个不等式解集的交集',
    'T03I3': '根据实际限制列不等式'
}

# 学习路径依赖（指标之间的先修关系，用于推荐排序）
LEARNING_PATH = [
    'T01I1', 'T01I2', 'T01I3',  # 代数式：基础→进阶→应用
    'T02I1', 'T02I2', 'T02I3',  # 方程：基础→进阶→应用
    'T03I1', 'T03I2', 'T03I3'   # 不等式：基础→进阶→应用
]


# ============================================================
# BKT模型核心
# ============================================================

class SimpleBKT:
    """
    简化版贝叶斯知识追踪模型

    四个参数：
      P(L0): 初始掌握概率（先验，基于全局得分率设定）
      P(T):  学习转移概率（每次练习后学会的概率）
      P(S):  猜对概率（不会但碰巧答对）
      P(G):  失误概率（会但粗心答错）
    """

    def __init__(self, indicator_id, initial_mastery, p_T=0.25, p_S=0.1, p_G=0.2):
        self.indicator_id = indicator_id
        self.indicator_name = INDICATOR_NAMES.get(indicator_id, '')
        self.p_L0 = initial_mastery   # 初始掌握概率
        self.p_T = p_T                 # 学习转移概率
        self.p_S = p_S                 # 猜对概率（slip）
        self.p_G = p_G                 # 失误概率（guess）
        self.current_mastery = initial_mastery
        self.history = [initial_mastery]  # 记录掌握概率的变化过程
        self.answer_count = 0
        self.correct_count = 0

    def update(self, is_correct):
        """
        根据一次作答结果更新掌握概率

        核心公式（贝叶斯更新）：
          答对后: P(L|correct) = P(L)×(1-P(S)) / [P(L)×(1-P(S)) + (1-P(L))×P(G)]
          答错后: P(L|wrong)   = P(L)×P(S) / [P(L)×P(S) + (1-P(L))×(1-P(G))]
          学习效应: P(L_new) = P(L|answer) + (1-P(L|answer))×P(T)
        """
        p_L = self.current_mastery

        if is_correct:
            # 答对了：掌握概率上升
            numerator = p_L * (1 - self.p_S)
            denominator = p_L * (1 - self.p_S) + (1 - p_L) * self.p_G
        else:
            # 答错了：掌握概率下降
            numerator = p_L * self.p_S
            denominator = p_L * self.p_S + (1 - p_L) * (1 - self.p_G)

        if denominator == 0:
            posterior = p_L  # 避免除零
        else:
            posterior = numerator / denominator

        # 考虑学习效应：即使这次答错了，也可能通过练习学会了
        self.current_mastery = posterior + (1 - posterior) * self.p_T

        # 确保概率在[0, 1]范围内
        self.current_mastery = max(0.01, min(0.99, self.current_mastery))

        # 记录历史
        self.history.append(self.current_mastery)
        self.answer_count += 1
        if is_correct:
            self.correct_count += 1

        return self.current_mastery

    def needs_practice(self, threshold=0.7):
        """判断是否需要继续练习"""
        return self.current_mastery < threshold

    def get_status(self):
        """获取当前状态摘要"""
        if self.answer_count == 0:
            status = 'no_data'  # 无数据
        elif self.current_mastery >= 0.7:
            status = 'mastered'  # 已掌握
        elif self.current_mastery >= 0.4:
            status = 'developing'  # 发展中
        else:
            status = 'weak'  # 薄弱
        return status

    def to_dict(self):
        return {
            'indicator_id': self.indicator_id,
            'indicator_name': self.indicator_name,
            'initial_mastery': round(self.p_L0, 4),
            'current_mastery': round(self.current_mastery, 4),
            'answer_count': self.answer_count,
            'correct_count': self.correct_count,
            'accuracy': round(self.correct_count / self.answer_count, 4) if self.answer_count > 0 else None,
            'mastery_history': [round(h, 4) for h in self.history],
            'status': self.get_status(),
            'needs_practice': self.needs_practice()
        }


# ============================================================
# 为每个学生构建知识追踪模型
# ============================================================

def build_student_bkt(student_id, records, indicator_stats):
    """
    为单个学生构建9个指标的BKT模型

    参数:
      student_id: 学生编号
      records: 该学生的所有已评分记录（已按时间排序）
      indicator_stats: 各指标的全局得分率（用于初始化先验）
    """
    # 为9个指标分别创建BKT模型
    # 初始掌握概率 = 该指标的全局得分率（用数据驱动先验，而非拍脑袋）
    models = {}
    for ind in INDICATORS:
        global_rate = indicator_stats.get(ind, {}).get('score_rate', 0.5)
        models[ind] = SimpleBKT(
            indicator_id=ind,
            initial_mastery=global_rate,  # 用全局得分率作为先验
            p_T=0.25,   # 每次练习有25%概率学会
            p_S=0.1,    # 猜对概率10%
            p_G=0.2     # 失误概率20%
        )

    # 按时间顺序更新（records已经按submit_time排序）
    for r in records:
        if r['student_id'] != student_id:
            continue
        ind = r.get('indicator_id', '')
        if ind in models:
            models[ind].update(r['is_correct'])

    return models


def build_all_students_bkt(data_model, stats):
    """
    为所有40个学生构建BKT模型
    """
    print("=" * 50)
    print("模块2：BKT知识追踪模型")
    print("=" * 50)

    # 获取全局指标得分率（用于初始化先验）
    indicator_stats = stats.get('by_indicator', {})

    # 按学生分组记录
    student_records = defaultdict(list)
    for r in data_model['records']:
        student_records[r['student_id']].append(r)

    # 为每个学生建模
    mastery_matrix = {}  # 学生ID → {指标ID → 掌握概率}
    student_profiles = {}  # 学生ID → 完整画像

    print(f"\n  开始为 {len(student_records)} 名学生构建知识追踪模型...")

    for sid in sorted(student_records.keys()):
        s_records = student_records[sid]
        models = build_student_bkt(sid, s_records, indicator_stats)

        # 构建掌握概率矩阵
        mastery_matrix[sid] = {
            ind: round(models[ind].current_mastery, 4)
            for ind in INDICATORS
        }

        # 构建完整学生画像
        weak_indicators = []
        developing_indicators = []
        mastered_indicators = []
        no_data_indicators = []

        for ind in INDICATORS:
            model = models[ind]
            if model.get_status() == 'weak':
                weak_indicators.append(model.to_dict())
            elif model.get_status() == 'developing':
                developing_indicators.append(model.to_dict())
            elif model.get_status() == 'mastered':
                mastered_indicators.append(model.to_dict())
            else:
                no_data_indicators.append(model.to_dict())

        # 按掌握概率从低到高排序薄弱指标
        weak_indicators.sort(key=lambda x: x['current_mastery'])

        # 计算整体掌握水平
        all_mastery = [models[ind].current_mastery for ind in INDICATORS]
        avg_mastery = sum(all_mastery) / len(all_mastery) if all_mastery else 0

        # 推荐学习路径（按学习依赖顺序排列薄弱指标）
        weak_indicator_ids = [w['indicator_id'] for w in weak_indicators]
        recommended_path = [
            ind for ind in LEARNING_PATH
            if ind in weak_indicator_ids or ind in [d['indicator_id'] for d in developing_indicators]
        ]

        student_profiles[sid] = {
            'student_id': sid,
            'class_id': data_model['students'].get(sid, {}).get('模拟班级编号', ''),
            'overall_mastery': round(avg_mastery, 4),
            'overall_status': 'high' if avg_mastery >= 0.7 else ('medium' if avg_mastery >= 0.4 else 'low'),
            'weak_indicators': weak_indicators,
            'developing_indicators': developing_indicators,
            'mastered_indicators': mastered_indicators,
            'no_data_indicators': no_data_indicators,
            'recommended_learning_path': recommended_path,
            'indicator_details': {ind: models[ind].to_dict() for ind in INDICATORS}
        }

        # 打印进度（每10个学生打一次）
        if int(sid[1:]) % 10 == 0 or sid == 'D40':
            print(f"    已完成: {sid} (整体掌握度: {avg_mastery:.1%})")

    return mastery_matrix, student_profiles


# ============================================================
# 输出结果
# ============================================================

def save_results(mastery_matrix, student_profiles):
    """保存结果文件"""
    print("\n  输出结果文件:")

    # mastery_matrix.json（紧凑的掌握概率矩阵，供可视化使用）
    matrix_path = os.path.join(OUTPUT_DIR, 'mastery_matrix.json')
    with open(matrix_path, 'w', encoding='utf-8') as f:
        json.dump(mastery_matrix, f, ensure_ascii=False, indent=2)
    print(f"    -> {matrix_path}")

    # student_profiles.json（完整的知识追踪画像，供推荐引擎使用）
    profiles_path = os.path.join(OUTPUT_DIR, 'student_profiles.json')
    with open(profiles_path, 'w', encoding='utf-8') as f:
        json.dump(student_profiles, f, ensure_ascii=False, indent=2)
    print(f"    -> {profiles_path}")

    # 输出一份人类可读的摘要
    summary_path = os.path.join(OUTPUT_DIR, 'bkt_summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("智慧学伴 - BKT知识追踪摘要\n")
        f.write("=" * 60 + "\n\n")

        f.write("学生掌握概率矩阵（按整体掌握度排序）:\n")
        f.write("-" * 60 + "\n")
        f.write(f"{'学生':>6} {'班级':>6} {'整体':>6}")
        for ind in INDICATORS:
            f.write(f" {ind:>8}")
        f.write("  状态\n")
        f.write("-" * 60 + "\n")

        sorted_sids = sorted(student_profiles.keys(),
                            key=lambda x: student_profiles[x]['overall_mastery'])
        for sid in sorted_sids:
            p = student_profiles[sid]
            f.write(f"{sid:>6} {p['class_id']:>6} {p['overall_mastery']:>5.1%}")
            for ind in INDICATORS:
                m = p['indicator_details'][ind]['current_mastery']
                f.write(f" {m:>7.1%}")
            f.write(f"  [{p['overall_status']}]\n")

        f.write("\n\n薄弱指标统计（掌握概率<0.4）:\n")
        f.write("-" * 60 + "\n")
        weak_counter = defaultdict(int)
        for sid, p in student_profiles.items():
            for w in p['weak_indicators']:
                weak_counter[w['indicator_id']] += 1
        for ind in INDICATORS:
            count = weak_counter.get(ind, 0)
            bar = '█' * count
            f.write(f"  {ind} ({INDICATOR_NAMES[ind]:>20s}): {count:>2}人 {bar}\n")

    print(f"    -> {summary_path}")


# ============================================================
# 主函数
# ============================================================

def main():
    # 加载模块1的输出
    cleaned_path = os.path.join(OUTPUT_DIR, 'cleaned_data.json')
    stats_path = os.path.join(OUTPUT_DIR, 'statistics.json')

    print("\n加载模块1的输出数据...")
    with open(cleaned_path, 'r', encoding='utf-8') as f:
        data_model = json.load(f)
    with open(stats_path, 'r', encoding='utf-8') as f:
        stats = json.load(f)
    print(f"  加载完成: {data_model['meta']['total_records']} 条记录, "
          f"{data_model['meta']['total_students']} 名学生")

    # 构建BKT模型
    mastery_matrix, student_profiles = build_all_students_bkt(data_model, stats)

    # 保存结果
    save_results(mastery_matrix, student_profiles)

    # 打印几个典型案例
    print("\n" + "=" * 50)
    print("典型案例预览:")
    print("=" * 50)

    for sid in ['D14', 'D01', 'D03']:
        if sid in student_profiles:
            p = student_profiles[sid]
            print(f"\n  {sid} ({p['class_id']}) 整体掌握度: {p['overall_mastery']:.1%} [{p['overall_status']}]")
            if p['weak_indicators']:
                print(f"    薄弱指标:")
                for w in p['weak_indicators'][:3]:
                    print(f"      {w['indicator_id']} ({w['indicator_name']}): "
                          f"掌握概率 {w['current_mastery']:.1%}, "
                          f"答题 {w['answer_count']} 次, "
                          f"正确 {w['correct_count']} 次")
            if p['recommended_learning_path']:
                print(f"    推荐学习路径: {' → '.join(p['recommended_learning_path'])}")

    print("\n" + "=" * 60)
    print("  模块2 完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
