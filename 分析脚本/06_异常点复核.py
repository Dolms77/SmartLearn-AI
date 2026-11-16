# -*- coding: utf-8 -*-
"""异常点复核：Q038 越界记录、主题编号不一致、答案-评分矛盾（含等价格式归一）。"""
import os
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 90)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"
load = lambda n: pd.read_csv(os.path.join(BASE, n))
q, rec, node = load("题目与材料.csv"), load("作答记录.csv"), load("测验节点.csv")

print("### Q038 本体")
print(q[q["材料编号"] == "Q038"].T.to_string())

print("\n### Q038 在 N01 的记录")
x = rec[(rec["材料编号"] == "Q038")].merge(q[["材料编号", "主题编号", "题型"]], on="材料编号", suffixes=("", "_题"))
print(x[["记录编号", "学生编号", "节点编号", "主题编号", "主题编号_题", "评分状态", "得分", "满分", "学生最终作答"]].to_string(index=False))

print("\n### 主题编号不一致的记录")
m = rec.merge(q[["材料编号", "主题编号", "题型", "参考答案"]], on="材料编号", how="left", suffixes=("", "_题"))
mm = m[m["主题编号"] != m["主题编号_题"]]
print(mm[["记录编号", "学生编号", "材料编号", "节点编号", "主题编号", "主题编号_题", "评分状态", "得分"]].to_string(index=False))


def norm(s):
    t = str(s) if pd.notna(s) else ""
    t = re.sub(r"[\s，,。；;]", "", t)
    t = re.sub(r"^(x|y|a|n)=", "", t)
    return t


fill = m[(m["题型"] == "填空题") & (m["评分状态"] == "已评分")].copy()
fill["一致"] = [norm(a) == norm(b) for a, b in zip(fill["学生最终作答"], fill["参考答案"])]
print("\n### 归一后 填空题 答案与得分矛盾")
c1 = fill[(fill["一致"]) & (fill["得分"] == 0)]
c2 = fill[(~fill["一致"]) & (fill["得分"] == fill["满分"])]
print("一致却0分:", len(c1), " 不一致却满分:", len(c2))
for df, tag in [(c1, "一致却0分"), (c2, "不一致却满分")]:
    if len(df):
        print(f"\n— {tag} —")
        print(df[["记录编号", "学生编号", "材料编号", "学生最终作答", "参考答案", "得分"]].to_string(index=False))

print("\n### N01 中 2026-06-17 提交的记录")
r = rec[(rec["节点编号"] == "N01") & (rec["模拟提交时间"].str.startswith("2026-06-17"))]
print(r.to_string(index=False))
print("\n该作答事件的全部版本:")
print(rec[rec["作答事件编号"].isin(r["作答事件编号"])].sort_values(["作答事件编号", "修订版本"]).to_string(index=False))

print("\n### 选择题 3 题作答与得分")
ch = m[m["题型"] == "选择题"]
print(ch.groupby(["材料编号", "学生最终作答"])["得分"].agg(["size", "mean"]).to_string())
