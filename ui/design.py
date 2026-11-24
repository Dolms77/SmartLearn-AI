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
import html as _html
import re as _re


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
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    # 思考过渡层的样式也在这里一次性注入，避免 thinking_overlay 每次切页重复塞 <style>
    st.markdown(THINK_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 页面底色与容器质感（渐变 + 玻璃拟态）
# ---------------------------------------------------------------------------
PAGE_CSS = """
<style>
/* ---------- 全局字体 ---------- */
html, body, .stApp, [class*="css"]{
  font-family:"Microsoft YaHei","PingFang SC","HarmonyOS Sans SC",system-ui,sans-serif;
}
h1,h2,h3{letter-spacing:.3px;color:var(--ink);}

/* ---------- 页面底色：柔和渐变，替代纯白 ---------- */
.stApp{
  background:
    radial-gradient(1100px 620px at 8% -10%, rgba(47,111,237,.10), transparent 60%),
    radial-gradient(900px 520px at 100% 0%, rgba(122,86,255,.10), transparent 55%),
    radial-gradient(800px 520px at 50% 110%, rgba(0,163,163,.08), transparent 60%),
    linear-gradient(180deg,#f8fafe 0%,#f3f6fc 100%);
  background-attachment: fixed;
}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stToolbar"]{right:1rem;}

/* ---------- 侧栏：浅渐变 + 细边框 ---------- */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,rgba(255,255,255,.92),rgba(244,247,255,.92));
  border-right:1px solid rgba(226,232,244,.9);
  backdrop-filter:blur(10px);
}
section[data-testid="stSidebar"] *{color:var(--ink-2);}

/* ---------- 卡片：玻璃质感 ---------- */
.sa-kpi,.sa-concl,.sa-role-card{
  background:rgba(255,255,255,.72);
  backdrop-filter:blur(10px) saturate(120%);
  border:1px solid rgba(255,255,255,.75);
  box-shadow:0 8px 24px rgba(23,43,77,.07), 0 1px 0 rgba(255,255,255,.9) inset;
  transition:transform .18s ease, box-shadow .18s ease;
}
.sa-kpi:hover{transform:translateY(-2px);box-shadow:0 14px 32px rgba(23,43,77,.12);}

/* KPI 顶部一条渐变高光 */
.sa-kpi{position:relative;overflow:hidden;}
.sa-kpi::before{
  content:"";position:absolute;inset:0 0 auto 0;height:3px;
  background:linear-gradient(90deg,var(--brand),#7A56FF 55%,#00A3A3);
  opacity:.85;
}
.sa-kpi.ok::before{background:linear-gradient(90deg,#2E9E5B,#7BD3A0);}
.sa-kpi.warn::before{background:linear-gradient(90deg,#E8A33D,#F6D08A);}
.sa-kpi.bad::before{background:linear-gradient(90deg,#D9534F,#F09B95);}

/* ---------- 结论卡：渐变描边 ---------- */
.sa-concl{
  border:1px solid transparent;
  background:
    linear-gradient(rgba(255,255,255,.86),rgba(255,255,255,.86)) padding-box,
    linear-gradient(135deg,rgba(47,111,237,.55),rgba(122,86,255,.45) 50%,rgba(0,163,163,.45)) border-box;
  box-shadow:0 12px 34px rgba(47,111,237,.10);
}

/* ---------- Tab：胶囊化 ---------- */
div[data-baseweb="tab-list"]{
  gap:6px;background:rgba(255,255,255,.65);padding:5px;border-radius:999px;
  border:1px solid rgba(226,232,244,.9);width:fit-content;
}
button[data-baseweb="tab"]{
  border-radius:999px!important;padding:6px 16px!important;
  font-size:var(--f-s)!important;color:var(--muted)!important;
}
button[data-baseweb="tab"][aria-selected="true"]{
  background:linear-gradient(135deg,var(--brand),#6C63FF)!important;
  color:#fff!important;box-shadow:0 6px 16px rgba(47,111,237,.28);
}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none;}

/* ---------- 主按钮：渐变 ---------- */
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,var(--brand),#6C63FF);
  border:0;color:#fff;box-shadow:0 8px 20px rgba(47,111,237,.28);
}
.stButton>button[kind="primary"]:hover{filter:brightness(1.05);transform:translateY(-1px);}
.stButton>button{border-radius:10px;border-color:rgba(226,232,244,.95);}

/* ---------- 表格/图表容器：图表克制、表格有清晰分层 ---------- */
div[data-testid="stPlotlyChart"]{background:rgba(255,255,255,.55);border-radius:14px;padding:6px;border:1px solid rgba(255,255,255,.7);box-shadow:0 6px 18px rgba(23,43,77,.05);}
div[data-testid="stDataFrame"]{background:rgba(255,255,255,.78);border-radius:12px;overflow:hidden;border:1px solid #dbe5f0;box-shadow:0 6px 18px rgba(23,43,77,.05);}
div[data-testid="stDataFrame"] [role="columnheader"]{background:#eaf1fb!important;color:#243858!important;font-weight:700!important;border-bottom:1px solid #cbd9ea!important;}
div[data-testid="stDataFrame"] [role="gridcell"]{border-bottom:1px solid #edf1f6!important;}
div[data-testid="stDataFrame"] [role="row"]:nth-child(even) [role="gridcell"]{background:rgba(234,241,251,.34)!important;}
div[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"]{background:#e8f2ff!important;}

/* ---------- 滚动条 ---------- */
::-webkit-scrollbar{width:10px;height:10px;}
::-webkit-scrollbar-thumb{background:rgba(47,111,237,.28);border-radius:8px;}
::-webkit-scrollbar-thumb:hover{background:rgba(47,111,237,.45);}

/* ---------- 整卡可点：容器内放一个透明按钮铺满 ----------
   用法：with st.container(key="click-xxx"): 渲染卡片; st.button("...", key="...")
   容器 class 为 st-key-click-xxx，透明按钮盖住整张卡片。 */
div[class*="st-key-click-"]{position:relative;}
div[class*="st-key-click-"] div[data-testid="stButton"]{
  position:absolute;inset:0;z-index:5;opacity:0;margin:0;padding:0;}
div[class*="st-key-click-"] div[data-testid="stButton"] > button{
  width:100%;height:100%;border:0;background:transparent;cursor:pointer;}

/* 悬停/聚焦时整卡给出反馈（:has 兼容 Edge 105+/Chrome 105+） */
div[class*="st-key-click-"]:has(div[data-testid="stButton"] button:hover) .sa-role-card,
div[class*="st-key-click-"]:has(div[data-testid="stButton"] button:hover) .sa-hero{
  transform:translateY(-4px);
}
div[class*="st-key-click-"]:has(div[data-testid="stButton"] button:hover) .sa-role-card{
  border-color:#c7d8fb;box-shadow:0 16px 38px rgba(47,111,237,.18);
}
div[class*="st-key-click-"]:has(div[data-testid="stButton"] button:focus-visible) .sa-role-card{
  outline:2px solid var(--brand);outline-offset:3px;
}
.sa-hero-hint{text-align:center;font-size:12px;color:var(--muted);margin-top:-2px;}
</style>
"""


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
    safe_headline = _html.escape(headline)
    safe_headline = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe_headline)
    m = ""
    if metrics:
        m = '<div class="m">' + "".join(
            f'<div><div class="k">{k}</div><div class="n">{v}</div></div>' for k, v in metrics
        ) + "</div>"
    st.markdown(
        f'<div class="sa-concl"><div class="t">{tag}</div>'
        f'<div class="h">{safe_headline}</div>{m}</div>',
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


# ---------------------------------------------------------------------------
# "AI 思考中" 过渡层：只在切换页面时注入，1 秒后自动淡出
THINK_CSS = """
<style>
/* 默认隐藏（display:none）：只有在"允许动效"的浏览器里才淡入淡出，
   万一动效被禁用或浏览器不执行动画，这一层永远不可见，绝不会挡住点击。 */
.sa-think{display:none;}
.sa-think *{pointer-events:none!important;}
@media (prefers-reduced-motion: no-preference){
  .sa-think{position:fixed;inset:0;z-index:9999;display:flex;align-items:flex-start;
    justify-content:center;padding-top:22vh;pointer-events:none;
    background:rgba(248,250,254,.42);backdrop-filter:blur(1.5px);
    animation:sa-think-out .38s ease .78s forwards;}
  .sa-think-card{animation:sa-think-in .22s ease;}
  .sa-think-bar{position:fixed;display:block;animation:sa-bar .9s cubic-bezier(.4,0,.2,1) forwards;}
}
.sa-think-card{display:flex;align-items:center;gap:12px;
  background:rgba(255,255,255,.95);border:1px solid #e6ebf3;border-radius:16px;
  padding:14px 20px;box-shadow:0 18px 44px rgba(23,43,77,.14);}
.sa-think-card .txt{font-size:14px;color:#31415c;}
.sa-think-card .txt b{color:#2F6FED;font-weight:600;}
/* 顶部进度条：从左扫到右 */
.sa-think-bar{display:none;position:fixed;top:0;left:0;height:3px;z-index:10000;width:100%;
  transform-origin:left center;pointer-events:none;
  background:linear-gradient(90deg,#2F6FED,#7A56FF 50%,#00A3A3);}
@keyframes sa-bar{0%{transform:scaleX(0);opacity:1;}70%{transform:scaleX(.86);opacity:1;}
  100%{transform:scaleX(1);opacity:0;}}
@keyframes sa-think-in{from{opacity:0;transform:translateY(-8px) scale(.98);}
  to{opacity:1;transform:none;}}
@keyframes sa-think-out{to{opacity:0;visibility:hidden;}}
</style>
"""


def thinking_overlay(text: str = "正在组织答案…", hold: float = 1.05) -> None:
    """切页时的一次性"思考"过渡：纯 CSS 自动淡出，不阻塞点击。

    样式（THINK_CSS）已在 inject_tokens() 一次性注入，这里只渲染过渡层本体。
    """
    st.markdown(
        f'<div class="sa-think-bar"></div>'
        f'<div class="sa-think"><div class="sa-think-card">'
        f'{typing_html()}'
        f'<div class="txt"><b>智慧学伴</b> · {text}</div></div></div>',
        unsafe_allow_html=True)


def typing_html() -> str:
    return '<span class="sa-dots"><span></span><span></span><span></span></span>'
