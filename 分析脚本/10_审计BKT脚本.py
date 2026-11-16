# -*- coding: utf-8 -*-
"""复现 02_bkt_model.py 的核心逻辑，量化其不足（不改原脚本，仅审计）。"""
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 200)

BASE = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据"
q = pd.read_csv(os.path.join(BASE, "题目与材料.csv"))
stu = pd.read_csv(os.path.join(BASE, "模拟学生.csv"))
rec = pd.read_csv(os.path.join(BASE, "作答记录.csv"))

IND = ["T01I1", "T01I2", "T01I3", "T02I1", "T02I2", "T02I3", "T03I1", "T03I2", "T03I3"]

# ---- 复现脚本的模型 ----
def bkt_update(p_L, is_correct, p_T=0.25, p_S=0.1, p_G=0.2):
    if is_correct:
        num = p_L * (1 - p_S)
        den = p_L * (1 - p_S) + (1 - p_L) * p_G
    else:
        num = p_L * p_S
        den = p_L * p_S + (1 - p_L) * (1 - p_G)
    post = p_L if den == 0 else num / den
    return max(0.01, min(0.99, post + (1 - post) * p_T))


print("### 1. 饱和速度（先验 0.5 / 0.57 时连续答对）")
for prior in (0.5, 0.57):
    p, seq = prior, []
    for _ in range(5):
        p = bkt_update(p, True)
        seq.append(round(p, 4))
    print(f"  先验 {prior}: 1次→{seq[0]}  2次→{seq[1]}  3次→{seq[2]}  5次→{seq[4]}")

print("\n### 2. 部分得分被二值化丢掉多少信息")
eff = rec.sort_values(["作答事件编号", "修订版本"]).drop_duplicates("作答事件编号", keep="last")
s = eff[eff["评分状态"] == "已评分"].merge(
    q[["材料编号", "指标编号", "题型", "材料类型"]], on="材料编号")
s = s[s["材料类型"] == "题目"]
part = s[(s["得分"] > 0) & (s["得分"] < s["满分"])]
print(f"  已评分记录 {len(s)} 条；其中部分得分 {len(part)} 条 "
      f"（{100*len(part)/len(s):.1f}%）会被 is_correct=False 记为'答错'")
print("  按题型:")
print(part.groupby("题型").size().to_string())

print("\n### 3. 零证据单元格会输出什么")
cnt = s.groupby(["学生编号", "指标编号"]).size()
grid = pd.MultiIndex.from_product([sorted(stu["学生编号"]), IND])
cnt = cnt.reindex(grid, fill_value=0)
# 全局得分率（含该生自己的数据 → 轻微泄漏）
g = s.groupby("指标编号").apply(lambda d: d["得分"].sum() / d["满分"].sum(), include_groups=False)
print("  全局得分率(即先验):", {k: round(v, 3) for k, v in g.items()})
zero = cnt[cnt == 0]
print(f"  零证据单元格 {len(zero)} 个，'掌握概率'将输出对应指标先验值 "
      f"（而非 no_data），例: {[(i, round(g[i],3)) for i in IND[:3]]}")

print("\n### 4. 掌握概率与得分率是否只是单调变换（=有没有新信息）")
rows = []
for sid, d in s.groupby("学生编号"):
    models = {i: g.get(i, 0.5) for i in IND}
    for _, r in d.sort_values("模拟提交时间").iterrows():
        i = r["指标编号"]
        models[i] = bkt_update(models[i], r["得分"] == r["满分"])
    rate = d.groupby("指标编号").apply(lambda x: x["得分"].sum() / x["满分"].sum(), include_groups=False)
    for i in IND:
        if i in rate.index:
            rows.append((models[i], rate[i]))
df = pd.DataFrame(rows, columns=["mastery", "rate"])
rho = df["mastery"].rank().corr(df["rate"].rank())  # 秩相关，等价 Spearman
print(f"  学生-指标 配对 {len(df)} 个；掌握概率 vs 得分率 Spearman ρ = {rho:.4f}")
print(f"  掌握概率=0.99 的单元格: {int((df['mastery']>=0.99).sum())}；=0.01: {int((df['mastery']<=0.01).sum())}")

print("\n### 5. 推荐路径是否对所有学生都一样")
for sid in ["D30", "D19", "D01"]:
    d = s[s["学生编号"] == sid]
    models = {i: g.get(i, 0.5) for i in IND}
    for _, r in d.sort_values("模拟提交时间").iterrows():
        models[r["指标编号"]] = bkt_update(models[r["指标编号"]], r["得分"] == r["满分"])
    weak = sorted([i for i in IND if models[i] < 0.4], key=lambda i: models[i])
    dev = [i for i in IND if 0.4 <= models[i] < 0.7]
    path = [i for i in IND if i in weak or i in dev]
    print(f"  {sid}: weak(按概率升序)={weak} -> 路径(固定顺序过滤)={path}")
print("\n  ⇒ 路径只保留固定 LEARNING_PATH 的顺序，'按掌握概率排序'在路径上被覆盖掉了。")
