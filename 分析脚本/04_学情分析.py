# -*- coding: utf-8 -*-
"""学情分析：班级/个体/指标层面表现、典型案例候选、记录不足识别。"""
import os
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 240)
pd.set_option("display.max_colwidth", 70)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"
load = lambda n: pd.read_csv(os.path.join(BASE, n))
q, stu, rec, node, cq = load("题目与材料.csv"), load("模拟学生.csv"), load("作答记录.csv"), load("测验节点.csv"), load("课程要求.csv")

print("### 材料清单（非题目材料）")
mats = q[q["材料类型"] != "题目"]
for _, r in mats.iterrows():
    print(f"[{r['材料编号']}] {r['材料类型']} | {r['主题编号']} | 来源={r['来源或资料文件']}")
    print(f"    内容: {str(r['题干或内容'])[:160]}")

print("\n### 题目来源统计")
print(q["来源或资料文件"].value_counts().to_string())

# 只保留最新修订版本作为有效记录
rec = rec.sort_values(["作答事件编号", "修订版本"])
eff = rec.drop_duplicates("作答事件编号", keep="last").copy()
print(f"\n有效作答事件（按最新修订）: {len(eff)}，其中待评分 {int((eff['评分状态']=='待评分').sum())}，"
      f"未作答 {int((eff['评分状态']=='未作答').sum())}")

valid = eff[eff["评分状态"] == "已评分"].copy()
valid = valid.merge(q[["材料编号", "题型", "指标编号", "材料类型"]], on="材料编号", how="left")
valid = valid.merge(stu, on="学生编号", how="left")
valid["得分率"] = valid["得分"] / valid["满分"]

print("\n### 全样本得分率（已评分，按题型）")
print(valid.groupby("题型").agg(题次=("得分", "size"), 均分=("得分", "mean"),
                             满分均=("满分", "mean"), 得分率=("得分率", "mean")).round(3).to_string())

print("\n### 按主题")
print(valid.groupby("主题编号").agg(题次=("得分", "size"), 得分率=("得分率", "mean"),
                                 满分率=("得分率", lambda s: (s == 1).mean())).round(3).to_string())

print("\n### 按指标（观察指标）")
ind = valid.groupby("指标编号").agg(题次=("得分", "size"), 得分率=("得分率", "mean"),
                                 满分率=("得分率", lambda s: (s == 1).mean()),
                                 零分率=("得分率", lambda s: (s == 0).mean())).round(3)
ind = ind.join(cq.set_index("指标编号")["观察指标"])
print(ind.to_string())

print("\n### 按班级 × 主题（得分率）")
print(valid.pivot_table(index="模拟班级编号", columns="主题编号", values="得分率", aggfunc="mean").round(3).to_string())
print("\n按班级 × 题型")
print(valid.pivot_table(index="模拟班级编号", columns="题型", values="得分率", aggfunc="mean").round(3).to_string())
print("\n班级作答量/覆盖率")
tot = valid.groupby("模拟班级编号").agg(有效记录=("记录编号", "size"), 学生数=("学生编号", "nunique"))
print(tot.to_string())

print("\n### 学生层面汇总（按得分率排序）")
st = valid.groupby(["学生编号"]).agg(
    题次=("得分", "size"), 得分率=("得分率", "mean"),
    满分题=("得分率", lambda s: int((s == 1).sum())),
    零分题=("得分率", lambda s: int((s == 0).sum())),
).join(stu.set_index("学生编号")).sort_values("得分率", ascending=False)
print(st.round(3).to_string())

print("\n### 解答题（3分题）部分得分者")
part = valid[(valid["题型"] == "解答题") & (valid["得分"] > 0) & (valid["得分"] < valid["满分"])]
print(part[["记录编号", "学生编号", "模拟班级编号", "材料编号", "节点编号", "得分", "评分点得分"]].to_string(index=False))
print("\n解答题零分记录数:", int(((valid["题型"] == "解答题") & (valid["得分"] == 0)).sum()))

print("\n### 记录不足候选（N02 缺失或主题覆盖 <2 题）")
cov = eff.groupby("学生编号").apply(
    lambda d: pd.Series({
        "N01": int((d["节点编号"] == "N01").sum()),
        "N02": int((d["节点编号"] == "N02").sum()),
        "T01": int((d["主题编号"] == "T01").sum()),
        "T02": int((d["主题编号"] == "T02").sum()),
        "T03": int((d["主题编号"] == "T03").sum()),
    }), include_groups=False)
print(cov.sort_values(["N02", "T03"]).head(12).to_string())
