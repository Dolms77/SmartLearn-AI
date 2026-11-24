# -*- coding: utf-8 -*-
"""教师端评分步骤列表，使用原生 HTML 和 CSS 渲染。"""
from __future__ import annotations

from html import escape
from math import ceil, isfinite


CSS = """
<style>
.sa-review {
  --value-space:3.75rem;
  display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  column-gap:clamp(.5rem,1.4vw,1rem); align-items:center;
  box-sizing:border-box; width:100%; max-width:60rem; margin-inline:auto;
  padding:.4rem .75rem; border:1px solid #e6ebf3;
  border-radius:12px; background:#fff; color:#243247;
}
.sa-review .heading {font-size:.75rem; color:#5b687a; font-weight:600; padding-bottom:.3rem;}
.sa-review .step {min-width:0; padding-block:.3rem; text-align:right;
  overflow-wrap:anywhere; font-size:.9rem; line-height:1.35;}
.sa-review .code {display:block; color:#657386; font-size:.72rem; letter-spacing:.025em;}
.sa-review .track,.sa-review .reference,.sa-review .guide {margin-inline-end:var(--value-space);}
.sa-review .track {min-width:0; position:relative; height:1rem; z-index:1;}
.sa-review .bar {display:block; width:var(--end); height:.4rem; position:absolute; top:50%;
  transform:translateY(-50%); border-radius:999px; background:#557ab2;}
.sa-review .dot {position:absolute; left:0; top:50%; transform:translate(-50%,-50%);
  width:.4rem; height:.4rem; border-radius:50%; background:#9b3640;}
.sa-review .value {position:absolute; left:calc(var(--end) + .4rem); top:50%;
  transform:translateY(-50%); color:#536174; font-size:.8rem;
  font-variant-numeric:tabular-nums; white-space:nowrap;}
.sa-review .zero {color:#9b3640;}
.sa-review .missing {left:0; color:#6b778a; font-size:.75rem;}
.sa-review .reference {position:relative; white-space:nowrap; text-align:left;}
.sa-review .reference-label {position:absolute; transform:translateX(-50%); color:#845223;}
.sa-review .guide {grid-column:2; align-self:stretch; position:relative;
  z-index:2; pointer-events:none;}
.sa-review .guide::before {content:""; position:absolute; left:var(--threshold); top:0; bottom:0;
  border-left:1px dashed #d7aa79;}
@media (max-width:520px) {
  .sa-review {--value-space:3.4rem; padding-inline:.5rem;}
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
    scale = max(.3, min(1.0, ceil(max(valid, default=0) * 10) / 10))
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
        '<div class="heading step">评分步骤</div>',
        reference,
    ]
    for index, row in enumerate(rows, start=2):
        rate = row.get("rate")
        marker = ""
        position = 0
        if not valid_rate(rate):
            # 空值没有图形。0% 是有效观测，单独显示深红圆点和数值。
            value, style = "暂无数据", "missing"
        elif rate == 0:
            value, style, marker = "0%", "zero", '<span class="dot" aria-hidden="true"></span>'
        else:
            value, style = f"{rate:.2%}".rstrip("%").rstrip("0").rstrip(".") + "%", ""
            position = rate / scale
            marker = '<span class="bar" aria-hidden="true"></span>'
        parts.extend((
            f'<div class="step" style="grid-area:{index}/1"><span class="code">{escape(row["id"])}</span>'
            f'{escape(row["description"])}</div>',
            f'<div class="track" style="grid-area:{index}/2;--end:{position:.4%}">'
            f'{marker}<span class="value {style}">{value}</span></div>',
        ))
    if valid:
        parts.append(f'<div class="guide" style="grid-row:2 / span {len(rows)}" aria-hidden="true"></div>')
    parts.append("</div>")
    return "".join(parts)
