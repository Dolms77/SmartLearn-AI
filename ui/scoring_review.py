# -*- coding: utf-8 -*-
"""教师端评分步骤列表的渲染入口与得分校验。"""
from __future__ import annotations

from math import isfinite

from comparison_dashboard import dashboard_component


def valid_rate(value: float | None) -> bool:
    """空值单独处理，保留合法的 0%；忽略非数值和超出范围的得分率。"""
    return isinstance(value, (int, float)) and isfinite(value) and 0 <= value <= 1


def render_scoring_review(rows: list[dict], *, key: str) -> None:
    dashboard_component(scoringRows=rows, key=key)
