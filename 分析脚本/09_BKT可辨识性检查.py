# -*- coding: utf-8 -*-
"""评估 BKT 在本数据上的可辨识性：学生×指标 证据分布。"""
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 200)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"
load = lambda n: pd.read_csv(os.path.join(BASE, n))
q, stu, rec = load("题目与材料.csv"), load("模拟学生.csv"), load("作答记录.csv")

eff = rec.sort_values(["作答事件编号", "修订版本"]).drop_duplicates("作答事件编号", keep="last")
s = eff[eff["评分状态"] == "已评分"].merge(q[["材料编号", "指标编号"]], on="材料编号")

idx = pd.MultiIndex.from_product([sorted(stu["学生编号"]), sorted(q["指标编号"].dropna().unique())])
cnt = s.groupby(["学生编号", "指标编号"]).size().reindex(idx, fill_value=0)

print("学生×指标 单元格总数:", len(cnt))
print("证据数分布:\n" + cnt.value_counts().sort_index().to_string())
print("\n0 条证据的单元格: %d (%.1f%%)" % ((cnt == 0).sum(), 100 * (cnt == 0).mean()))
print("≤2 条证据的单元格: %d (%.1f%%)" % ((cnt <= 2).sum(), 100 * (cnt <= 2).mean()))
print("\nD01 各指标证据数:")
print(cnt.loc["D01"].to_string())
print("\n每生平均覆盖指标数: %.1f / 9" % (cnt.groupby(level=0).apply(lambda x: (x > 0).sum()).mean()))

print("\n### 若用 BKT 先验 0.5 输出，'掌握概率' 与证据量对照（示例 5 名学生）")
for sid in ["D01", "D14", "D17", "D19", "D30"]:
    row = cnt.loc[sid]
    print(f"  {sid}: 有证据指标 {(row>0).sum()}/9, 证据总数 {row.sum()}, 最多 {row.max()} 条")
