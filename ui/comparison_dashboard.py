# -*- coding: utf-8 -*-
"""Streamlit 桥接层，将现有班级统计传给离线 React 组件。"""
from pathlib import Path

import streamlit.components.v1 as components


TOPICS = {"T01": "代数式", "T02": "方程", "T03": "不等式"}
dashboard_component = components.declare_component(
    "class_comparison", path=str(Path(__file__).with_name("class_comparison") / "dist"),
)


def comparison_data(class_rates: dict, indicators: dict, questions: dict, names: dict) -> dict:
    low_questions = sorted(
        ((qid, row) for qid, row in questions.items()
         if row.get("n", 0) >= 5 and row.get("rate") is not None),
        key=lambda pair: pair[1]["rate"],
    )[:10]
    return {
        "topics": list(TOPICS.values()),
        "classes": [{"id": cls, "rates": [row.get(topic) for topic in TOPICS]}
                    for cls, row in class_rates.items()],
        "indicators": [
            {"id": code, "label": names.get(code, code), "rate": row["rate"], "count": row["n"]}
            for code, row in indicators.items() if row.get("rate") is not None
        ],
        "questions": [
            {"id": qid, "label": row.get("text", ""), "rate": row["rate"], "count": row["n"]}
            for qid, row in low_questions
        ],
    }


def render_comparison(cls: str, class_rates: dict, indicators: dict, questions: dict, names: dict) -> None:
    dashboard_component(dashboard=comparison_data(class_rates, indicators, questions, names),
                        key=f"class_comparison_{cls}")
