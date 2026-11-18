# -*- coding: utf-8 -*-
"""设计 token、KPI 卡、证据徽标、结论卡、统一图表主题（P0 体验改造）。

用法：
    theme.inject()                      # 已注入，含 token
    theme.kpi_row([("掌握度","54%","4/9 指标可判定")])
    theme.evidence_badge(3)             # ● 证据 3 条
    theme.conclusion_card("标题", "一句话结论", [("掌握度","29%"),("证据","3 条")])
    charts.apply_theme(fig)             # 所有图表自动套用（_layout 已调用）
"""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# 设计 token（CSS 变量）
# ---------------------------------------------------------------------------
TOKENS_CSS = """
<style>
:root{
  --ink:#16233a; --ink-2:#31415c; --muted:#6b7787; --line:#e6ebf3; --bg:#f7f9fc;
  --brand:#2F6FED; --brand-weak:#eef3fe; --ok:#2E9E5B; --warn:#E8A33D; --bad:#D9534F;
  --f-xs:12px; --f-s:14px; --f-m:16px; --f-l:20px; --f-xl:28px;
  --r-s:8px; --r-m:12px; --r-l:16px;
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:24px;
  --sh-1:0 2px 8px rgba(23,43,77,.06); --sh-2:0 10px 24px rgba(23,43,77,.10);
}
/* ---------- 身份条 ---------- */
.sa-idbar{display:flex;align-items:center;gap:14px;padding:10px 0 14px;
  border-bottom:1px solid var(--line);margin-bottom:var(--sp-4);}
.sa-idbar .who{font-size:var(--f-l);font-weight:700;color:var(--ink);line-height:1.2;}
.sa-idbar .sub{font-size:var(--f-xs);color:var(--muted);margin-top:2px;}
.sa-idbar .spacer{flex:1;}
/* ---------- KPI 卡 ---------- */
.sa-kpis{display:flex;gap:12px;flex-wrap:wrap;margin:2px 0 18px;}
.sa-kpi{flex:1;min-width:140px;background:#fff;border:1px solid var(--line);border-radius:var(--r-m);
  padding:14px 16px;box-shadow:var(--sh-1);}
.sa-kpi .v{font-size:var(--f-xl);font-weight:700;color:var(--ink);line-height:1.1;}
.sa-kpi .l{font-size:var(--f-xs);color:var(--muted);margin-top:6px;}
.sa-kpi .s{font-size:var(--f-xs);color:var(--brand);margin-top:4px;}
.sa-kpi.warn .v{color:var(--warn);} .sa-kpi.bad .v{color:var(--bad);} .sa-kpi.ok .v{color:var(--ok);}
/* ---------- 结论卡 ---------- */
.sa-concl{background:linear-gradient(135deg,#f4f8ff,#ffffff);border:1px solid #dbe7fd;
  border-radius:var(--r-l);padding:20px 22px;box-shadow:var(--sh-2);margin-bottom:18px;}
.sa-concl .t{font-size:var(--f-xs);color:var(--brand);letter-spacing:1px;margin-bottom:8px;}
.sa-concl .h{font-size:var(--f-l);font-weight:700;color:var(--ink);line-height:1.5;}
.sa-concl .m{display:flex;gap:22px;margin-top:14px;flex-wrap:wrap;}
.sa-concl .m .k{font-size:var(--f-xs);color:var(--muted);}
.sa-concl .m .n{font-size:var(--f-l);font-weight:700;color:var(--ink);}
/* ---------- 证据徽标 ---------- */
.sa-ev{display:inline-flex;align-items:center;gap:6px;font-size:var(--f-xs);
  padding:2px 9px;border-radius:999px;border:1px solid var(--line);background:#fff;color:var(--ink-2);}
.sa-ev .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);}
.sa-ev.weak{background:#fff8ee;border-color:#f6dfb8;} .sa-ev.weak .dot{background:var(--warn);}
.sa-ev.none{background:#f3f5f9;color:var(--muted);} .sa-ev.none .dot{background:#c3cad6;}
.sa-ev.bad{background:#fff3f2;border-color:#f5c9c4;} .sa-ev.bad .dot{background:var(--bad);}
/* ---------- 空状态 ---------- */
.sa-empty{text-align:center;padding:36px 16px;color:var(--muted);}
.sa-empty .ico{font-size:34px;opacity:.75;}
.sa-empty .h{font-size:var(--f-m);color:var(--ink-2);margin-top:10px;font-weight:600;}
.sa-empty .d{font-size:var(--f-xs);margin-top:6px;}
/* ---------- Tab 区 ---------- */
div[data-baseweb="tab-list"]{gap:6px;}
button[data-baseweb="tab"]{font-size:var(--f-s);}
</style>
"""


def inject_tokens() -> None:
    st.markdown(TOKENS_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 组件
# ---------------------------------------------------------------------------
def kpi_row(items: list[tuple[str, str, str | None]],
            tones: list[str] | None = None) -> None:
    """items: [(标签, 数值, 补充说明)]，tones: 可选 'ok'/'warn'/'bad'。"""
    tones = tones or [""] * len(items)
    cells = []
    for (label, value, sub), tone in zip(items, tones):
        s = f'<div class="s">{sub}</div>' if sub else ""
        cells.append(f'<div class="sa-kpi {tone}"><div class="v">{value}</div>'
                     f'<div class="l">{label}</div>{s}</div>')
    st.markdown(f'<div class="sa-kpis">{"".join(cells)}</div>', unsafe_allow_html=True)


def evidence_badge(n: int, threshold: int = 3, weak: bool = False) -> str:
    """证据量徽标：够门槛=绿点，不足=灰点，薄弱但证据足=橙点。"""
    if n < threshold:
        return f'<span class="sa-ev none"><span class="dot"></span>证据 {n} 条 · 不足 {threshold} 条</span>'
    cls = "weak" if weak else ""
    return f'<span class="sa-ev {cls}"><span class="dot"></span>证据 {n} 条</span>'


def conclusion_card(tag: str, headline: str,
                    metrics: list[tuple[str, str]] | None = None) -> None:
    """核心结论卡：一句话 + 至多 2 个数字。"""
    m = ""
    if metrics:
        m = '<div class="m">' + "".join(
            f'<div><div class="k">{k}</div><div class="n">{v}</div></div>' for k, v in metrics
        ) + "</div>"
    st.markdown(
        f'<div class="sa-concl"><div class="t">{tag}</div>'
        f'<div class="h">{headline}</div>{m}</div>',
        unsafe_allow_html=True)


def empty_state(icon: str, title: str, desc: str = "") -> None:
    st.markdown(
        f'<div class="sa-empty"><div class="ico">{icon}</div>'
        f'<div class="h">{title}</div><div class="d">{desc}</div></div>',
        unsafe_allow_html=True)


def identity_bar(avatar_html: str, name: str, sub: str) -> None:
    st.markdown(
        f'<div class="sa-idbar">{avatar_html}'
        f'<div><div class="who">{name}</div><div class="sub">{sub}</div></div>'
        f'</div>', unsafe_allow_html=True)
