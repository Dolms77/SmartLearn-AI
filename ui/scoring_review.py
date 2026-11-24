# -*- coding: utf-8 -*-
"""教师端评分步骤列表，使用原生 HTML 和 CSS 渲染。"""
from __future__ import annotations

from html import escape
from math import ceil, isfinite


CSS = """
<style>
.sa-review {
  display:grid; grid-template-columns:minmax(0,1.7fr) minmax(3rem,1fr) 4.5rem;
  column-gap:clamp(.35rem,2vw,1.25rem); align-items:center;
  padding:.75rem clamp(.5rem,2vw,1.25rem); border:1px solid #e6ebf3;
  border-radius:12px; background:#fff; color:#243247;
}
.sa-review .heading {font-size:.78rem; color:#5b687a; font-weight:600; padding-bottom:.55rem;}
.sa-review .step,.sa-review .track,.sa-review .value {padding-block:.45rem;}
.sa-review .step {min-width:0; overflow-wrap:anywhere; font-size:.9rem; line-height:1.45;}
.sa-review .code {display:block; color:#657386; font-size:.72rem; letter-spacing:.025em;}
.sa-review .track {min-width:0; display:flex; align-items:center; position:relative; z-index:1;}
.sa-review .bar {height:.4rem; border-radius:999px; background:linear-gradient(90deg,#9caed9,#42649b);}
.sa-review .dot {width:.32rem; height:.32rem; border-radius:50%; background:#9b3640;}
.sa-review .value {text-align:right; font-size:.83rem; font-variant-numeric:tabular-nums;
  font-weight:600; white-space:nowrap;}
.sa-review .zero {color:#9b3640;}
.sa-review .missing {color:#6b778a; font-size:.75rem; font-weight:400;}
.sa-review .reference {position:relative; white-space:nowrap; text-align:left;}
.sa-review .reference-label {position:absolute; transform:translateX(-50%); color:#845223;}
.sa-review .guide {grid-column:2; grid-row:2 / -1; align-self:stretch; position:relative;
  z-index:2; pointer-events:none;}
.sa-review .guide::before {content:""; position:absolute; left:var(--threshold); top:0; bottom:0;
  border-left:1px dashed #d7aa79;}
@media (max-width:520px) {
  .sa-review {grid-template-columns:minmax(0,1.6fr) minmax(2.5rem,1fr) 3.6rem;}
}
</style>
"""


def valid_rate(value: float | None) -> bool:
    """空值单独处理，保留合法的 0%；忽略非数值和超出范围的得分率。"""
    return isinstance(value, (int, float)) and isfinite(value) and 0 <= value <= 1


def review_html(rows: list[dict]) -> str:
    """行字段为 id、description、rate；rate 为 0–1 的比例或 None。"""
    valid = [row["rate"] for row in rows if valid_rate(row.get("rate"))]
    # 缩短评分轨道的有效范围。条宽和基准线共用同一比例尺。
    scale = max(.4, min(1.0, ceil(max(valid, default=0) * 10) / 10))
    threshold = 30 / scale
    reference = (
        '<div class="heading reference" aria-label="30% 复盘基准">'
        '<span class="reference-label" style="left:var(--threshold)">30%</span>&nbsp;</div>'
        if valid else '<div></div>'
    )
    parts = [
        CSS,
        f'<div class="sa-review" style="--threshold:{threshold:.4f}%" '
        f'aria-label="评分步骤得分率，刻度范围 0% 至 {scale:.0%}">',
        '<div class="heading">评分步骤</div>',
        reference,
        '<div class="heading value">得分率</div>',
    ]
    for index, row in enumerate(rows, start=2):
        rate = row.get("rate")
        marker = ""
        if not valid_rate(rate):
            # 空值没有图形。0% 是有效观测，单独显示深红圆点和数值。
            value, style = "暂无数据", "missing"
        elif rate == 0:
            value, style, marker = "0%", "zero", '<span class="dot"></span>'
        else:
            value, style = f"{rate:.2%}".rstrip("%").rstrip("0").rstrip(".") + "%", ""
            marker = f'<span class="bar" style="width:{rate / scale:.4%}"></span>'
        parts.extend((
            f'<div class="step" style="grid-area:{index}/1"><span class="code">{escape(row["id"])}</span>'
            f'{escape(row["description"])}</div>',
            f'<div class="track" style="grid-area:{index}/2" aria-hidden="true">{marker}</div>',
            f'<div class="value {style}" style="grid-area:{index}/3">{value}</div>',
        ))
    if valid:
        parts.append(f'<div class="guide" style="grid-row:2 / span {len(rows)}" aria-hidden="true"></div>')
    parts.append("</div>")
    return "".join(parts)
