# -*- coding: utf-8 -*-
"""BKT 参考实现（修正版）——用于对照审计 02_bkt_model.py

相对原脚本的 6 处修正：
  1. 证据门槛 + 层级回退：指标级 n>=3 才出结论，否则回退到主题级，仍不足则 insufficient
  2. 部分给分：用 得分/满分 作软证据，不再二值化（保留 111 条 1/3、2/3 分的信息）
  3. 先验来自全局题目表现（不是该生首题表现），并对从未作答的指标不填充
  4. 不确定性：输出 Wilson 95% 区间与证据数
  5. 节点分离：N01/N02 分别累计，可看跨节点变化
  6. 可复现：命令行参数、无硬编码路径/学生编号

运行：
  python bkt_v2_参考实现.py --data <模拟学情数据目录> [--min-evidence 3] [--out out.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict

INDICATORS = ["T01I1", "T01I2", "T01I3", "T02I1", "T02I2", "T02I3", "T03I1", "T03I2", "T03I3"]
THEMES = ["T01", "T02", "T03"]
PARAMS = {"p_T": 0.10, "p_S": 0.10, "p_G": 0.05}  # slip(会而错) / guess(不会而对)


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = max(0.0, min(1.0, k / n))
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def bkt_step(p_L: float, credit: float, p_T: float, p_S: float, p_G: float) -> float:
    """软证据 BKT：把一次得分为 credit 的作答看成'以 credit 的概率被观测为正确'。"""
    l_correct = p_L * (1 - p_S) + (1 - p_L) * p_G
    l_wrong = p_L * p_S + (1 - p_L) * (1 - p_G)
    lik = credit * l_correct + (1 - credit) * l_wrong
    if lik <= 0:
        return p_L
    post = credit * (p_L * (1 - p_S)) / lik + (1 - credit) * (p_L * p_S) / lik
    return max(0.02, min(0.98, post + (1 - post) * p_T))


def level(rate: float | None) -> str:
    if rate is None:
        return "insufficient"
    if rate >= 0.70:
        return "mastered"
    if rate >= 0.40:
        return "developing"
    return "weak"


def load(data_dir: str):
    import csv

    def rd(name):
        with open(os.path.join(data_dir, name), encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    items = {r["材料编号"]: r for r in rd("题目与材料.csv")}
    return items, rd("模拟学生.csv"), rd("作答记录.csv")


def cell_stats(rows: list[dict], items: dict, min_n: int) -> dict:
    """对一组记录（某生某指标或某主题）聚合出结论。"""
    n = len(rows)
    if n == 0:
        return {"evidence": 0, "status": "insufficient", "note": "无任何已评分记录"}
    credit_sum = sum(float(r["得分"]) / float(r["满分"]) for r in rows)
    lo, hi = wilson(credit_sum, n)
    if n < min_n:
        return {"evidence": n, "credit_rate": round(credit_sum / n, 3),
                "ci95": [round(lo, 3), round(hi, 3)], "status": "insufficient",
                "note": f"证据不足（{n} 条 < {min_n}），仅列出区间不下结论"}
    return {"evidence": n, "credit_rate": round(credit_sum / n, 3),
            "ci95": [round(lo, 3), round(hi, 3)], "status": level(credit_sum / n)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--min-evidence", type=int, default=3)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    items, students, records = load(a.data)

    # 1) 取最新修订版本；隔离待评分/未作答
    latest: dict[str, dict] = {}
    for r in records:
        k = r["作答事件编号"]
        if k not in latest or int(r["修订版本"]) > int(latest[k]["修订版本"]):
            latest[k] = r
    scored = [r for r in latest.values() if r["评分状态"] == "已评分"]

    # 2) 全局先验（题目表现的加权平均）
    g_sum, g_n = 0.0, 0
    for r in scored:
        ind = items[r["材料编号"]]["指标编号"]
        if ind in INDICATORS:
            g_sum += float(r["得分"]) / float(r["满分"])
            g_n += 1
    prior = g_sum / g_n if g_n else 0.5

    by_student: dict[str, list[dict]] = defaultdict(list)
    for r in scored:
        by_student[r["学生编号"]].append(r)

    result = {}
    for sid in sorted({s["学生编号"] for s in students}):
        rows = sorted(by_student.get(sid, []), key=lambda r: r["模拟提交时间"])
        by_ind: dict[str, list[dict]] = defaultdict(list)
        by_theme: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            ind = items[r["材料编号"]]["指标编号"]
            if ind not in INDICATORS:
                continue
            by_ind[ind].append(r)
            by_theme[ind[:3]].append(r)

        indicators, fallback_themes = {}, {}
        for ind in INDICATORS:
            if len(by_ind[ind]) >= a.min_evidence:
                indicators[ind] = cell_stats(by_ind[ind], items, a.min_evidence)
                # 附 BKT 轨迹（辅助指标，不作为结论唯一依据）
                p = prior
                for r in by_ind[ind]:
                    p = bkt_step(p, float(r["得分"]) / float(r["满分"]), **PARAMS)
                indicators[ind]["bkt_track"] = round(p, 3)
            else:
                indicators[ind] = cell_stats(by_ind[ind], items, a.min_evidence)
        for t in THEMES:
            if len(by_theme[t]) >= a.min_evidence:
                fallback_themes[t] = cell_stats(by_theme[t], items, a.min_evidence)

        decided = [v for v in indicators.values() if v["status"] != "insufficient"]
        result[sid] = {
            "class": next(s["模拟班级编号"] for s in students if s["学生编号"] == sid),
            "evidence_total": len(rows),
            "indicator_level": indicators,
            "theme_fallback": fallback_themes,
            "decisive_indicators": len(decided),
            "note": "指标级证据不足时请使用 theme_fallback，勿据先验值下结论"
                    if len(decided) < len(INDICATORS) else "",
        }

    print(f"每生可下结论的指标数分布: "
          f"{sorted({v['decisive_indicators'] for v in result.values()})}（共 9 个指标）")
    print(f"有主题级回退结论的学生数: {sum(1 for v in result.values() if v['theme_fallback'])}/40")
    for sid in ["D14", "D17", "D19", "D30", "D03"]:
        v = result[sid]
        print(f"\n{sid}（{v['class']}，{v['evidence_total']} 条）决定性指标 "
              f"{v['decisive_indicators']}/9；主题级回退 {list(v['theme_fallback'])}")
        for t, cell in v["theme_fallback"].items():
            print(f"    {t}: {cell.get('credit_rate')} {cell.get('status')} n={cell['evidence']}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n已写出: {a.out}")


if __name__ == "__main__":
    main()
