# -*- coding: utf-8 -*-
"""作答内容与评分一致性核查 + 节点口径核查。"""
import os
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 240)
pd.set_option("display.max_colwidth", 70)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"
load = lambda n: pd.read_csv(os.path.join(BASE, n))
q, rec, node = load("题目与材料.csv"), load("作答记录.csv"), load("测验节点.csv")

print("### 1. 节点可用题目口径核查")
for _, n in node.iterrows():
    ids = set(str(n["可用题目编号"]).split("、"))
    got = set(rec[rec["节点编号"] == n["节点编号"]]["材料编号"])
    print(f"{n['节点编号']}: 声明{len(ids)}题, 实际出现{len(got)}题, 越界出现: {sorted(got - ids)}")

print("\n### 2. 作答记录主题编号 vs 题目表主题编号")
m = rec.merge(q[["材料编号", "主题编号", "题型", "参考答案"]], on="材料编号", how="left", suffixes=("", "_题"))
print("不一致行数:", int((m["主题编号"] != m["主题编号_题"]).sum()))
print("关联不到题目的记录:", int(m["主题编号_题"].isna().sum()))

print("\n### 3. 填空题：答案与参考答案一致但得0 / 不一致却得满分")
fill = m[(m["题型"] == "填空题") & (m["评分状态"] == "已评分")].copy()
norm = lambda s: re.sub(r"[\s，,。；;的元人个名分]", "", str(s)) if pd.notna(s) else ""
fill["答案一致"] = [norm(a) == norm(b) for a, b in zip(fill["学生最终作答"], fill["参考答案"])]
print("答案表面一致却0分:", int(((fill["答案一致"]) & (fill["得分"] == 0)).sum()))
print("答案表面不一致却满分:", int(((~fill["答案一致"]) & (fill["得分"] == fill["满分"])).sum()))
print("\n— 一致却0分样例 —")
print(fill[(fill["答案一致"]) & (fill["得分"] == 0)][["记录编号", "学生编号", "材料编号", "学生最终作答", "参考答案", "得分"]].head(15).to_string(index=False))
print("\n— 不一致却满分样例 —")
print(fill[(~fill["答案一致"]) & (fill["得分"] == fill["满分"])][["记录编号", "学生编号", "材料编号", "学生最终作答", "参考答案", "得分"]].head(15).to_string(index=False))

print("\n### 4. 解答题：步骤数与评分点数量")
sol = m[(m["题型"] == "解答题") & (m["评分状态"] == "已评分")].copy()
sol["步骤数"] = sol["解答过程"].fillna("").apply(lambda s: len(re.findall(r"^\s*\d+[.、]", str(s), flags=re.M)))
print(sol.groupby("步骤数").agg(题次=("记录编号", "size"), 平均得分=("得分", "mean")).round(2).to_string())

print("\n### 5. 得分点缺失但给满分的记录")
pm = sol["评分点得分"].fillna("")
print("解答题已评分但无评分点记录:", int((pm == "").sum()))

print("\n### 6. 提交时间与节点日期逻辑")
rec["提交日"] = pd.to_datetime(rec["模拟提交时间"], format="mixed", utc=True).dt.tz_convert("Asia/Shanghai").dt.date
nd = dict(zip(node["节点编号"], pd.to_datetime(node["模拟测验日期"]).dt.date))
bad_time = rec[rec.apply(lambda r: (r["提交日"] < nd[r["节点编号"]]), axis=1)]
print("提交时间早于测验日期:", len(bad_time))
if len(bad_time):
    print(bad_time[["记录编号", "节点编号", "模拟提交时间"]].head(10).to_string(index=False))
print("\n各节点提交日期分布:")
print(rec.groupby(["节点编号", "提交日"]).size().to_string())
