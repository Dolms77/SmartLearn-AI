# -*- coding: utf-8 -*-
"""Generate the evidence-backed task 1 knowledge structure from cleaned data."""

import argparse
from collections import Counter
from datetime import datetime
import json
import os


THEMES = ("T01", "T02", "T03")
INDICATORS = tuple(f"{theme}I{index}" for theme in THEMES for index in range(1, 4))
HIGH_EVIDENCE_THRESHOLD = 150
MEDIUM_EVIDENCE_THRESHOLD = 60


def evidence_density(count):
    if count >= HIGH_EVIDENCE_THRESHOLD:
        return "高"
    if count >= MEDIUM_EVIDENCE_THRESHOLD:
        return "中"
    return "低"


def build_task1_structure(data):
    if not isinstance(data, dict):
        raise ValueError("cleaned_data.json 顶层必须是对象")
    knowledge = data.get("knowledge_structure")
    questions = data.get("question_indicator_map")
    records = data.get("records")
    if not isinstance(knowledge, dict):
        raise ValueError("cleaned_data.json 缺少 knowledge_structure")
    if not isinstance(questions, dict):
        raise ValueError("cleaned_data.json 缺少 question_indicator_map")
    if not isinstance(records, list):
        raise ValueError("cleaned_data.json 缺少 records 列表")

    if set(knowledge) != set(THEMES):
        raise ValueError(f"主题应为 {THEMES}，实际为 {tuple(sorted(knowledge))}")

    questions_by_indicator = {code: [] for code in INDICATORS}
    for question_id, question in questions.items():
        if not isinstance(question, dict):
            raise ValueError(f"题目 {question_id} 的映射不是对象")
        code = question.get("indicator")
        if code not in questions_by_indicator:
            raise ValueError(f"题目 {question_id} 的指标无效：{code!r}")
        if question.get("theme") != code[:3]:
            raise ValueError(f"题目 {question_id} 的主题与指标 {code} 不一致")
        questions_by_indicator[code].append((question_id, question))

    evidence_by_indicator = Counter()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"records[{index}] 不是对象")
        code = record.get("indicator_id")
        if code not in INDICATORS:
            raise ValueError(f"records[{index}] 的指标无效：{code!r}")
        evidence_by_indicator[code] += 1

    themes = {}
    density_counts = Counter()
    for theme_id in THEMES:
        source_theme = knowledge[theme_id]
        if not isinstance(source_theme, dict):
            raise ValueError(f"{theme_id} 的知识结构不是对象")
        for field in ("theme_name", "theme_goal", "course_standard", "textbook_pages"):
            if not source_theme.get(field):
                raise ValueError(f"{theme_id} 缺少 {field}")
        source_indicators = source_theme.get("indicators")
        if not isinstance(source_indicators, dict):
            raise ValueError(f"{theme_id} 缺少 indicators")

        expected = {code for code in INDICATORS if code.startswith(theme_id)}
        if set(source_indicators) != expected:
            raise ValueError(f"{theme_id} 指标应为 {tuple(sorted(expected))}")

        theme_indicators = {}
        theme_question_count = 0
        theme_full_score = 0
        theme_evidence_count = 0
        for code in sorted(expected):
            source_indicator = source_indicators[code]
            if not isinstance(source_indicator, dict):
                raise ValueError(f"{code} 的指标定义不是对象")
            for field in ("indicator_name", "course_standard_ref"):
                if not source_indicator.get(field):
                    raise ValueError(f"{code} 缺少 {field}")
            mapped_questions = sorted(questions_by_indicator[code], key=lambda item: item[0])
            if not mapped_questions:
                raise ValueError(f"{code} 没有题目映射")
            question_types = Counter()
            full_score = 0
            for question_id, question in mapped_questions:
                score = question.get("full_score") or 0
                if not isinstance(score, (int, float)):
                    raise ValueError(f"题目 {question_id} 的满分不是数字")
                full_score += score
                question_types[question.get("type") or "未标注"] += 1

            evidence_count = evidence_by_indicator[code]
            density = evidence_density(evidence_count)
            density_counts[density] += 1
            question_count = len(mapped_questions)
            theme_question_count += question_count
            theme_full_score += full_score
            theme_evidence_count += evidence_count
            theme_indicators[code] = {
                "indicator_name": source_indicator.get("indicator_name", ""),
                "course_standard_ref": source_indicator.get("course_standard_ref", ""),
                "course_standard": source_theme.get("course_standard", ""),
                "textbook_pages": source_theme.get("textbook_pages", ""),
                "question_ids": [question_id for question_id, _ in mapped_questions],
                "question_count": question_count,
                "question_type_counts": dict(sorted(question_types.items())),
                "full_score": full_score,
                "evidence_count": evidence_count,
                "evidence_density": density,
            }

        themes[theme_id] = {
            "theme_name": source_theme.get("theme_name", ""),
            "theme_goal": source_theme.get("theme_goal", ""),
            "course_standard": source_theme.get("course_standard", ""),
            "textbook_pages": source_theme.get("textbook_pages", ""),
            "question_count": theme_question_count,
            "full_score": theme_full_score,
            "evidence_count": theme_evidence_count,
            "indicators": theme_indicators,
        }

    return {
        "meta": {
            "schema_version": "1.0",
            "generated_by": "09_task1_knowledge_structure.py",
            "generation_method": "source_data_aggregation",
            "source_file": "cleaned_data.json",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "evidence_density_thresholds": {
                "high": HIGH_EVIDENCE_THRESHOLD,
                "medium": MEDIUM_EVIDENCE_THRESHOLD,
            },
        },
        "summary": {
            "theme_count": len(themes),
            "indicator_count": len(INDICATORS),
            "question_count": len(questions),
            "evidence_count": len(records),
            "evidence_density_counts": dict(sorted(density_counts.items())),
        },
        "themes": themes,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the task 1 knowledge structure.")
    default_output_dir = os.environ.get("SS_OUT") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "output")
    parser.add_argument("--output-dir", default=default_output_dir)
    args = parser.parse_args()

    input_path = os.path.join(args.output_dir, "cleaned_data.json")
    output_path = os.path.join(args.output_dir, "task1_knowledge_structure.json")
    with open(input_path, "r", encoding="utf-8") as source_file:
        data = json.load(source_file)

    result = build_task1_structure(data)
    os.makedirs(args.output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    summary = result["summary"]
    print("任务1知识结构生成完成")
    print(f"  主题：{summary['theme_count']} 个")
    print(f"  指标：{summary['indicator_count']} 个")
    print(f"  题目映射：{summary['question_count']} 道")
    print(f"  作答证据：{summary['evidence_count']} 条")
    print(f"  -> {output_path}")


if __name__ == "__main__":
    main()
