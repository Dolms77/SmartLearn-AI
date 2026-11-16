# -*- coding: utf-8 -*-
"""赛题材料数据概览：表结构、规模、主题覆盖、作答记录质量检查。"""
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 60)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"


def load(name):
    return pd.read_csv(os.path.join(BASE, name))


cq, q, stu, node, rec, fld = (
    load("课程要求.csv"),
    load("题目与材料.csv"),
    load("模拟学生.csv"),
    load("测验节点.csv"),
    load("作答记录.csv"),
    load("字段说明.csv"),
)

print("### 表规模")
for name, df in [("课程要求", cq), ("题目与材料", q), ("模拟学生", stu),
                 ("测验节点", node), ("作答记录", rec), ("字段说明", fld)]:
    print(f"{name}: {df.shape[0]} 行 x {df.shape[1]} 列")

print("\n### 字段说明摘录（作答记录）")
print(fld[fld["数据表"].astype(str).str.contains("作答记录")].to_string(index=False))

print("\n### 材料构成")
print(q["材料类型"].value_counts().to_string())
print(q.groupby(["主题编号", "材料类型"]).size().to_string())

print("\n### 每主题题目数 / 指标覆盖")
qq = q[q["材料类型"] == "题目"]
print(qq.groupby(["主题编号", "题型"]).size().to_string())
print("\n指标缺口（课程要求 9 个指标 vs 题目覆盖）:")
cov = qq.groupby("指标编号").size()
for ind in cq["指标编号"]:
    print(f"  {ind}: {cov.get(ind, 0)} 题", "" if cov.get(ind, 0) else "  <-- 无题")

print("\n### 学生与班级")
print(stu.groupby("模拟班级编号").size().to_string())

print("\n### 测验节点")
for _, x in node.iterrows():
    ids = str(x["可用题目编号"]).split("、")
    print(f"{x['节点编号']} {x['模拟测验日期']} {x['已教及测量主题']} 题数={len(ids)} 说明={x['说明']}")

print("\n### 作答记录概况")
print("评分状态:\n" + rec["评分状态"].value_counts().to_string())
print("\n学生数:", rec["学生编号"].nunique(), " 出现题目数:", rec["材料编号"].nunique(),
      " 节点:", rec["节点编号"].unique().tolist())
print("\n每节点记录数:\n" + rec["节点编号"].value_counts().to_string())
print("\n每主题记录数:\n" + rec["主题编号"].value_counts().to_string())

print("\n### 重复与修订")
g = rec.groupby(["作答事件编号"]).size()
print("作答事件数:", g.size, " 每事件记录数分布:\n" + g.value_counts().to_string())
print("记录编号是否唯一:", rec["记录编号"].is_unique)
dup_full = rec.duplicated(subset=[c for c in rec.columns if c != "记录编号"])
print("除记录编号外完全重复行数:", int(dup_full.sum()))

print("\n### 缺失情况（按列）")
print(rec.isna().sum().to_string())

print("\n### 得分与满分校验")
scored = rec[rec["评分状态"] == "已评分"]
print("已评分记录:", len(scored))
print("得分>满分 的行数:", int((scored["得分"] > scored["满分"]).sum()))
print("得分<0 的行数:", int((scored["得分"] < 0).sum()))
print("得分/满分 与题目表满分不一致行数:",
      int((rec.merge(q[["材料编号", "满分"]], on="材料编号", how="left", suffixes=("", "_题"))
           .pipe(lambda d: d["满分"] != d["满分_题"]).sum())))
print("\n得分分布（已评分）:\n" + scored["得分"].value_counts().sort_index().to_string())
