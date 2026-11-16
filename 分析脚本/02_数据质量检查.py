# -*- coding: utf-8 -*-
"""作答记录质量问题定位：异常得分、待评分/未作答、修订重复、评分点与总分一致性、覆盖缺口。"""
import os
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 240)
pd.set_option("display.max_colwidth", 80)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"
load = lambda n: pd.read_csv(os.path.join(BASE, n))
q, stu, rec = load("题目与材料.csv"), load("模拟学生.csv"), load("作答记录.csv")

print("### 1. 得分越界 / 异常值")
bad = rec[(rec["得分"] > rec["满分"])]
print(bad.to_string(index=False))

print("\n### 2. 待评分 / 未作答记录")
print(rec[rec["评分状态"] != "已评分"].to_string(index=False))

print("\n### 3. 同一作答事件的修订版本")
multi = rec[rec["作答事件编号"].duplicated(keep=False)].sort_values(["作答事件编号", "修订版本"])
print(multi[["记录编号", "学生编号", "材料编号", "节点编号", "作答事件编号", "修订版本",
             "模拟提交时间", "评分状态", "得分", "满分"]].to_string(index=False))

print("\n### 4. 评分点得分之和 vs 总分")
def parse_points(s):
    if pd.isna(s):
        return None
    pairs = re.findall(r"(Q\d+P\d)=(\d+)", str(s))
    return sum(int(v) for _, v in pairs) if pairs else None

scored = rec[rec["评分状态"] == "已评分"].copy()
scored["评分点和"] = scored["评分点得分"].apply(parse_points)
sub = scored[scored["评分点和"].notna()]
mismatch = sub[sub["评分点和"] != sub["得分"]]
print(f"有评分点记录的已评分行: {len(sub)}；和≠总分: {len(mismatch)}")
if len(mismatch):
    print(mismatch[["记录编号", "学生编号", "材料编号", "得分", "满分", "评分点和", "评分点得分"]].to_string(index=False))

print("\n### 5. 评分点编号与题目表是否对应")
pmap = dict(zip(q["材料编号"], q["评分点"].astype(str)))
bad_pt = []
for _, r in sub.iterrows():
    ids = set(re.findall(r"(Q\d+P\d)", str(r["评分点得分"])))
    exp = set(re.findall(r"(Q\d+P\d)", pmap.get(r["材料编号"], "")))
    if ids != exp:
        bad_pt.append((r["记录编号"], r["材料编号"], sorted(ids), sorted(exp)))
print("评分点编号不符行数:", len(bad_pt))
for x in bad_pt[:10]:
    print("  ", x)

print("\n### 6. 每生每节点的记录数（覆盖缺口）")
piv = rec.pivot_table(index="学生编号", columns="节点编号", values="记录编号", aggfunc="count", fill_value=0)
piv["合计"] = piv.sum(axis=1)
print(piv.T.to_string())
print("\n节点应有题数: N01=27, N02=45")

print("\n### 7. 每生每主题 已作答(有记录)题目数 vs 该主题题数")
cnt = rec.groupby(["学生编号", "主题编号"]).size().unstack(fill_value=0)
print(cnt.describe().to_string())

print("\n### 8. 学生×题目 覆盖率")
print("学生数x题目数 =", 40 * 54, " 实际记录(去修订重)= ", rec["作答事件编号"].nunique())
print("未作答状态记录数:", int((rec["评分状态"] == "未作答").sum()))
print("空白作答(学生最终作答为空)但状态已评分:", int(((rec["评分状态"] == "已评分") & (rec["学生最终作答"].isna())).sum()))
