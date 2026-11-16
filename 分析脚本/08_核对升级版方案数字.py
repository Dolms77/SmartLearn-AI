# -*- coding: utf-8 -*-
"""核对《智慧学伴技术方案（升级版）》中引用的事实与数字。"""
import os
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 240)
pd.set_option("display.max_colwidth", 60)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"
load = lambda n: pd.read_csv(os.path.join(BASE, n))
q, stu, rec = load("题目与材料.csv"), load("模拟学生.csv"), load("作答记录.csv")

print("### A. 总量口径")
scored_all = rec[rec["评分状态"] == "已评分"]
print("原始行 806 / 已评分 %d / 待评分 %d / 未作答 %d" % (
    len(scored_all), (rec["评分状态"] == "待评分").sum(), (rec["评分状态"] == "未作答").sum()))
print("原始行口径 总分得分率 = %.4f%%" % (100 * scored_all["得分"].sum() / scored_all["满分"].sum()))

eff = rec.sort_values(["作答事件编号", "修订版本"]).drop_duplicates("作答事件编号", keep="last")
s2 = eff[eff["评分状态"] == "已评分"]
print("去修订口径 已评分 %d / 待评分 %d / 未作答 %d" % (
    len(s2), (eff["评分状态"] == "待评分").sum(), (eff["评分状态"] == "未作答").sum()))
print("去修订口径 总分得分率 = %.4f%%" % (100 * s2["得分"].sum() / s2["满分"].sum()))

print("\n### B. 方案中提到的具体数字")
checks = []


def rate(df):
    return 100 * df["得分"].sum() / df["满分"].sum()


checks.append(("D01 得分率(方案称 48.65%)", rate(s2[s2["学生编号"] == "D01"])))
for c in ["DC01", "DC02"]:
    ids = stu[stu["模拟班级编号"] == c]["学生编号"]
    checks.append((f"{c} 得分率", rate(s2[s2["学生编号"].isin(ids)])))
for c in ["DC01", "DC02"]:
    ids = stu[stu["模拟班级编号"] == c]["学生编号"]
    for t in ["T01", "T02", "T03"]:
        checks.append((f"{c}/{t} 得分率", rate(s2[(s2["学生编号"].isin(ids)) & (s2["主题编号"] == t)])))
for qid, claim in [("Q041", "方案称 72.7%"), ("Q001", "68.2%"), ("Q013", "72.2%"),
                   ("Q043", "方案称 P2 0%"), ("Q014", "方案称 P3 18.2%"), ("Q018", "方案称 P3 14%"),
                   ("Q002", "D01 算成14")]:
    d = s2[s2["材料编号"] == qid]
    checks.append((f"{qid} 得分率(题) n={len(d)} {claim}", rate(d) if len(d) else float("nan")))
for name, v in checks:
    print(f"  {name}: {v:.2f}%")

print("\n### C. 评分点级得分率（核对 Q043P2 / Q014P3 / Q018P3）")


def pts(s):
    return {k: int(v) for k, v in re.findall(r"(Q\d+P\d)=(\d+)", str(s))}


rows = []
for _, r in s2.iterrows():
    for k, v in pts(r["评分点得分"]).items():
        rows.append((r["材料编号"], k, v))
pdf = pd.DataFrame(rows, columns=["材料编号", "评分点", "得分"])
for key in ["Q043P2", "Q014P3", "Q018P3", "Q015P2", "Q043P3"]:
    d = pdf[pdf["评分点"] == key]
    if len(d):
        print(f"  {key}: n={len(d)} 得分率={100*d['得分'].mean():.1f}%  满分人数={int(d['得分'].sum())}")

print("\n### D. 方案中的个案论断")
d01 = s2[s2["学生编号"] == "D01"]
print("D01 Q002 作答与得分:")
print(d01[d01["材料编号"] == "Q002"][["记录编号", "节点编号", "学生最终作答", "得分", "满分"]].to_string(index=False))
print("\nD02 Q011 全部记录:")
print(rec[(rec["学生编号"] == "D02") & (rec["材料编号"] == "Q011")][
    ["记录编号", "节点编号", "修订版本", "学生最终作答", "解答过程", "得分", "评分点得分"]].to_string(index=False))
print("\nQ011 题干/答案:")
print(q[q["材料编号"] == "Q011"][["题干或内容", "参考答案", "评分点"]].to_string(index=False))

print("\n### E. 方案中 T03 指标-题号映射核对")
t3 = q[(q["主题编号"] == "T03") & (q["材料类型"] == "题目")][["材料编号", "指标编号", "题型"]]
print(t3.groupby("指标编号")["材料编号"].apply(lambda x: "、".join(x)).to_string())
