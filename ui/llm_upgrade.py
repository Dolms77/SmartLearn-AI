# -*- coding: utf-8 -*-
"""批量生成 LLM 版错因诊断（增量、可断点续跑）。

只写新文件 `output/error_diagnosis_llm.json`，**不覆盖** A 的 `error_diagnosis.json`。

用法：
    python llm_upgrade.py --output-dir ..\\output --limit 120
    python llm_upgrade.py --api-key sk-xxx --only 解答题
    python llm_upgrade.py --dry-run          # 只统计将调用多少条
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import llm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=os.path.abspath(os.path.join(HERE, "..", "output")))
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--limit", type=int, default=120, help="本次最多调用多少条")
    ap.add_argument("--only", default="解答题", choices=["解答题", "全部"], help="只处理解答题可显著省时省钱")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.0, help="每条之间的间隔秒数（本地模型可设 0）")
    ap.add_argument("--model", default=None, help="指定本地模型名，如 qwen3.5:4b")
    ap.add_argument("--think", action="store_true", help="开启 R1 思考链（更慢，约 6 倍）")
    a = ap.parse_args()

    cleaned = load_json(os.path.join(a.output_dir, "cleaned_data.json"), {})
    records = cleaned.get("records") or []
    rule = load_json(os.path.join(a.output_dir, "error_diagnosis.json"), [])
    rule = rule if isinstance(rule, list) else []

    # 只处理"错误记录"：得分 < 满分；二次过滤题型
    errs = [r for r in records if float(r.get("score") or 0) < float(r.get("full_score") or 0)]
    if a.only == "解答题":
        errs = [r for r in errs if r.get("question_type") == "解答题"]
    # 稳定的处理顺序：先解答题、再低分、再按记录号
    errs.sort(key=lambda r: (float(r.get("score") or 0) / max(float(r.get("full_score") or 1), 1),
                             r.get("record_id", "")))

    if a.model:
        llm.OLLAMA_MODEL_ENV = a.model
    if a.think:
        llm.OLLAMA_THINK = True
    stt = llm.status()
    key = llm.resolve_key(a.api_key) if stt["provider"] == "api" else None
    cache_dir = os.path.join(a.output_dir, "llm_cache")
    out_path = os.path.join(a.output_dir, "error_diagnosis_llm.json")
    result = load_json(out_path, {})
    if not isinstance(result, dict):
        result = {}

    todo = [r for r in errs if r.get("record_id") not in result]
    print(f"错误记录（{a.only}）: {len(errs)} 条；已缓存 {len(errs) - len(todo)} 条；待处理 {len(todo)} 条")
    print(f"规则诊断条数: {len(rule)}；输出文件: {out_path}")
    if a.dry_run:
        for r in todo[:10]:
            print(f"  - {r['record_id']} {r['question_id']} {r['indicator_id']} "
                  f"{r['score']}/{r['full_score']}")
        print(f"（dry-run，未调用模型；当前后端：{stt['label']}）")
        return

    if not stt["online"]:
        print(f"模型不可用：{stt['label']}（{stt['reason']}）")
        print("本地模式请先启动 Ollama 并拉取模型：ollama pull qwen3.5:4b")
        return
    print(f"后端：{stt['label']} | 思考链：{'开' if llm.OLLAMA_THINK else '关'} | 间隔 {a.sleep}s")

    todo = todo[: a.limit]
    ok = fail = 0
    t0 = time.time()
    # 规则引擎初判：作为"复核对象"喂给模型，让分歧可解释
    rule_map = {d.get("record_id"): d for d in rule if d.get("record_id")}
    for i, r in enumerate(todo, 1):
        rd = rule_map.get(r.get("record_id")) or {}
        hint = (f"{rd.get('error_type_code')} {rd.get('error_type')}"
                f"（依据：{rd.get('error_description', '评分点模式')}）") if rd else ""
        got = llm.diagnose_record(r, key, cache_dir, rule_hint=hint)
        if got and "error" not in got:
            result[r["record_id"]] = got
            ok += 1
        else:
            fail += 1
            if got and got.get("error"):
                print(f"  [失败] {r['record_id']}: {got['error']}")
        time.sleep(a.sleep)
        if i % 10 == 0 or i == len(todo):
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"  进度 {i}/{len(todo)}　成功 {ok}　失败 {fail}　"
                  f"耗时 {time.time() - t0:.0f}s")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n完成：共 {len(result)} 条 LLM 诊断已写入 {out_path}")
    print("界面会自动读取该文件，与规则结果并排展示。")


if __name__ == "__main__":
    main()
