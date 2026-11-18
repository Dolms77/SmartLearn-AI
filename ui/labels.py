# -*- coding: utf-8 -*-
"""代号 → 中文名称：页面上不该出现 T01I3 / T02 这类内部编号。

统一入口：
    labels.humanize(text, output_dir)   # 把文本里的编号换成名称
    labels.ind_name(code, name, output_dir)
    labels.theme_name(code, output_dir)
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

_IND_RE = re.compile(r"T0\dI\d")
_THEME_RE = re.compile(r"T0\d(?!I)")
# 「T01I3（用整式解释具体问题）」→ 只留名称
_IND_PAREN_RE = re.compile(r"(T0\dI\d)\s*[（(]([^）)]{2,40})[）)]")
_BAND_RE = re.compile(r"「(薄弱|发展中|已掌握|证据不足)」")
_RATE_RE = re.compile(r"掌握度\s*(\d+)%")


@lru_cache(maxsize=8)
def name_maps(output_dir: str) -> tuple[dict, dict]:
    """(指标编号→名称, 主题编号→名称)。文件缺失时返回空映射。"""
    ind: dict[str, str] = {}
    theme: dict[str, str] = {}
    path = os.path.join(output_dir or "", "task1_knowledge_structure.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return ind, theme
    for tcode, t in (data.get("themes") or {}).items():
        theme[tcode] = t.get("theme_name") or tcode
        for icode, i in (t.get("indicators") or {}).items():
            if i.get("indicator_name"):
                ind[icode] = i["indicator_name"]
    return ind, theme


def humanize(text: str, output_dir: str | None = None,
             maps: tuple[dict, dict] | None = None) -> str:
    """把文本里的指标/主题编号替换成名称，并清理多余空格。"""
    if not text:
        return text
    ind, theme = maps if maps is not None else name_maps(output_dir or "")
    s = str(text)
    s = _IND_PAREN_RE.sub(lambda m: m.group(2), s)
    s = _IND_RE.sub(lambda m: ind.get(m.group(0), m.group(0)), s)
    s = _THEME_RE.sub(lambda m: theme.get(m.group(0), m.group(0)), s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    for a, b in ((" ，", "，"), (" 。", "。"), (" 、", "、"), (" ：", "：")):
        s = s.replace(a, b)
    return s


def ind_name(code: str, name: str = "", output_dir: str | None = None) -> str:
    """知识点展示名：优先中文名，其次编号。"""
    if name:
        return name
    return name_maps(output_dir or "")[0].get(code, code) if code else code


def theme_name(code: str, output_dir: str | None = None) -> str:
    return name_maps(output_dir or "")[1].get(code, code) if code else code


def parse_band(reason: str) -> str:
    m = _BAND_RE.search(reason or "")
    return m.group(1) if m else ""


def parse_rate(reason: str) -> str:
    m = _RATE_RE.search(reason or "")
    return f"掌握度 {m.group(1)}%" if m else ""
