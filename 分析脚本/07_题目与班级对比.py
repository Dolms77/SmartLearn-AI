# -*- coding: utf-8 -*-
"""题目层面与班级对比：共性薄弱题、班级差异题、典型案例候选画像。"""
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 240)
pd.set_option("display.max_colwidth", 55)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"
load = lambda n: pd.read_csv(os.path.join(BASE, n))
q, stu, rec = load("题目与材料.csv"), load("模拟学生.csv"), load("作答记录.csv")

eff = rec.sort_values(["作答事件编号", "修订版本"]).drop_duplicates("作答事件编号", keep="last")
v = eff[eff["评分状态"] == "已评分"].copy()
v = v.merge(q[["材料编号", "题型", "指标编号", "题干或内容"]], on="材料编号")
v = v.merge(stu, on="学生编号")
v["得分率"] = v["得分"] / v["满分"]

print("### 题目层面（题次≥6）")
it = v.groupby(["材料编号", "主题编号", "题型", "指标编号"]).agg(
    题次=("得分", "size"), 得分率=("得分率", "mean")).round(3)
it = it[it["题次"] >= 6].sort_values("得分率")
print("\n-- 最薄弱 10 题 --")
print(it.head(10).to_string())
print("\n-- 最扎实 6 题 --")
print(it.tail(6).to_string())

print("\n### 班级差异（题次≥5/班）")
per = v.pivot_table(index="材料编号", columns="模拟班级编号", values="得分率", aggfunc="mean")
cnt = v.pivot_table(index="材料编号", columns="模拟班级编号", values="得分", aggfunc="size")
per = per[(cnt >= 5).all(axis=1)]
per["差值DC01-DC02"] = (per["DC01"] - per["DC02"]).round(3)
per = per.round(3)
print("\n-- DC01 明显更好 --")
print(per.sort_values("差值DC01-DC02", ascending=False).head(5).to_string())
print("\n-- DC02 明显更好 --")
print(per.sort_values("差值DC01-DC02").head(5).to_string())

print("\n### 候选案例画像")
for sid, tag in [("D14", "表现较好"), ("D19", "部分得分+T03无记录"),
                 ("D30", "低分但3分题拿2分"), ("D17", "记录严重不足"),
                 ("D16", "含异常评分")]:
    d = v[v["学生编号"] == sid]
    print(f"\n--- {sid}（{tag}）班级={d['模拟班级编号'].iloc[0] if len(d) else '—'} "
          f"题次={len(d)} 得分率={d['得分率'].mean():.2f} ---")
    print(d[["节点编号", "材料编号", "题型", "指标编号", "得分", "满分", "得分率"]]
          .sort_values(["节点编号", "材料编号"]).to_string(index=False))

print("\n### 每个学生学习卡主题覆盖（T01/T02/T03 有记录题数）")
cov = eff.groupby(["学生编号", "主题编号"]).size().unstack(fill_value=0)
print("T03 记录为 0 的学生数:", int((cov.get("T03", 0) == 0).sum()), "/ 40")
print("T02 记录为 0 的学生数:", int((cov.get("T02", 0) == 0).sum()), "/ 40")
print("单主题记录 ≤2 的人数:\n" + (cov <= 2).sum().to_string())
