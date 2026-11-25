# -*- coding: utf-8 -*-
"""视觉层：智能体形象、动画、聊天气泡。优先用 ui/assets 的角色图，缺失时回退内联 SVG。"""
from __future__ import annotations

import base64
import os
from functools import lru_cache

import streamlit as st

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
CHARACTER_FILE = "character.jpg"
ICON_FILE = "icon.jpg"

CSS = """
<style>
@keyframes sa-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
@keyframes sa-pulse { 0% { opacity:.55; transform: scale(.92); } 70% { opacity:0; transform: scale(1.35); } 100% { opacity:0; } }
@keyframes sa-glow  { 0%,100% { filter: drop-shadow(0 6px 18px rgba(47,111,237,.35)); } 50% { filter: drop-shadow(0 10px 30px rgba(122,86,255,.55)); } }
@keyframes sa-fadein { from { opacity:0; transform: translateY(10px); } to { opacity:1; transform: translateY(0); } }
@keyframes sa-blink { 0%,92%,100% { transform: scaleY(1); } 96% { transform: scaleY(.1); } }
@keyframes sa-dot { 0%,60%,100% { transform: translateY(0); opacity:.4; } 30% { transform: translateY(-4px); opacity:1; } }

.sa-hero { display:flex; flex-direction:column; align-items:center; gap:6px; padding:14px 0 4px; animation: sa-fadein .6s ease both; }
.sa-avatar-wrap { position:relative; width:160px; height:160px; display:flex; align-items:center; justify-content:center; }
.sa-avatar { width:132px; height:132px; animation: sa-float 4.2s ease-in-out infinite, sa-glow 4.2s ease-in-out infinite; }
img.sa-avatar { border-radius:26px; background:#fff; object-fit:cover;
  box-shadow:0 10px 26px rgba(23,43,77,.16); }
.sa-avatar .sa-eye { animation: sa-blink 5.5s infinite; transform-origin: center; }
.sa-ring { position:absolute; width:150px; height:150px; border-radius:50%; border:2px solid rgba(47,111,237,.45); animation: sa-pulse 2.6s ease-out infinite; }
.sa-ring.d2 { animation-delay: 1.3s; }
.sa-name { font-size:22px; font-weight:700; color:#16233a; letter-spacing:.5px; }
.sa-sub  { font-size:13px; color:#6b7787; }

.sa-bubble { position:relative; max-width:560px; background:#fff; border:1px solid #e5ebf5; border-radius:16px;
  padding:14px 18px; margin:14px auto 6px; box-shadow:0 10px 30px rgba(23,43,77,.08); font-size:14.5px; line-height:1.8;
  animation: sa-fadein .7s .1s ease both; }
.sa-bubble:after { content:''; position:absolute; top:-8px; left:50%; margin-left:-8px; width:16px; height:16px;
  background:#fff; border-left:1px solid #e5ebf5; border-top:1px solid #e5ebf5; transform:rotate(45deg); }

.sa-role-card { border:1px solid #e5ebf5; border-radius:18px; padding:22px; background:#fff; text-align:center;
  box-shadow:0 6px 20px rgba(23,43,77,.06); transition: all .18s ease; }
.sa-role-card:hover { transform: translateY(-3px); box-shadow:0 14px 32px rgba(23,43,77,.12); border-color:#c7d8fb; }
.sa-role-ico { font-size:40px; line-height:1; }
.sa-role-title { font-size:18px; font-weight:700; margin-top:8px; color:#16233a; }
.sa-role-desc { font-size:13px; color:#6b7787; margin-top:6px; line-height:1.7; }

.sa-brand { display:flex; align-items:center; gap:10px; padding:2px 0 10px; }
.sa-brand .sa-avatar { width:46px; height:46px; border-radius:12px; animation: sa-float 5s ease-in-out infinite; }
.sa-brand-compact { gap:6px; padding-bottom:0; }
.sa-brand-compact .sa-avatar { width:30px; height:30px; flex:none; border-radius:8px; }
.sa-brand-compact .sa-brand-t { font-size:14px; white-space:nowrap; }
.sa-brand-t { font-weight:700; font-size:16px; color:#16233a; line-height:1.2; }
.sa-brand-s { font-size:11.5px; color:#7c8798; }

.sa-chat-row { animation: sa-fadein .35s ease both; }
.sa-dots span { display:inline-block; width:6px; height:6px; margin:0 2px; border-radius:50%; background:#8aa4d6;
  animation: sa-dot 1.2s infinite; }
.sa-dots span:nth-child(2) { animation-delay:.15s; }
.sa-dots span:nth-child(3) { animation-delay:.3s; }

.sa-strip { display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 2px; }
.sa-chip { font-size:12.5px; padding:5px 12px; border-radius:999px; background:#eef3fe; color:#2F6FED; border:1px solid #dbe7fd; }

.sa-fade { animation: sa-fadein .5s ease both; }
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 素材（ui/assets/character.jpg、icon.jpg）
# --------------------------------------------------------------------------
@lru_cache(maxsize=4)
def _data_uri(filename: str) -> str:
    p = os.path.join(ASSET_DIR, filename)
    if not os.path.exists(p):
        return ""
    with open(p, "rb") as f:
        data = f.read()
    # 素材可保留旧文件名，按实际编码声明 MIME。
    mime = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def asset_path(filename: str) -> str | None:
    p = os.path.join(ASSET_DIR, filename)
    return p if os.path.exists(p) else None


def character_path() -> str | None:
    """给 st.chat_message(avatar=...) 用的文件路径。"""
    return asset_path(CHARACTER_FILE)


def icon_path() -> str | None:
    """给 st.set_page_config(page_icon=...) 用的文件路径。"""
    return asset_path(ICON_FILE)


@lru_cache(maxsize=8)
def _thumb_uri(filename: str, size: int) -> str:
    """小尺寸头像：用 Pillow 压到几十 KB，避免每次 rerun 塞 110KB base64。"""
    p = os.path.join(ASSET_DIR, filename)
    if not os.path.exists(p):
        return ""
    try:
        import io as _io

        from PIL import Image

        with Image.open(p) as source:
            transparent = "A" in source.getbands() or "transparency" in source.info
            im = source.convert("RGBA" if transparent else "RGB")
        im.thumbnail((size * 2, size * 2))       # 2x 便于高分屏
        buf = _io.BytesIO()
        if transparent:
            im.save(buf, format="PNG", optimize=True)
        else:
            im.save(buf, format="JPEG", quality=84, optimize=True)
        mime = "image/png" if transparent else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001 - 没装 Pillow 就退回原图
        return _data_uri(filename)


def avatar_img(size: int = 132, cls: str = "sa-avatar") -> str:
    """角色图（内联 base64，免静态服务）；素材缺失时自动回退 SVG。"""
    uri = _thumb_uri(CHARACTER_FILE, max(size, 32))
    if not uri:
        return avatar_svg(size, cls)
    return (f'<img class="{cls}" width="{size}" height="{size}" src="{uri}" '
            f'alt="智慧学伴" style="width:{size}px;height:{size}px;"/>')


def avatar_svg(size: int = 132, cls: str = "sa-avatar") -> str:
    """内联 SVG 智能体形象：渐变圆角头 + 天线 + 眨眼 + 微笑。"""
    return f"""
<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="sa-g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#3B82F6"/><stop offset="55%" stop-color="#6366F1"/><stop offset="100%" stop-color="#8B5CF6"/>
    </linearGradient>
    <linearGradient id="sa-g2" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#EAF1FF"/><stop offset="100%" stop-color="#CFE0FF"/>
    </linearGradient>
  </defs>
  <circle cx="60" cy="62" r="52" fill="url(#sa-g)" opacity="0.10"/>
  <line x1="60" y1="22" x2="60" y2="36" stroke="url(#sa-g)" stroke-width="4" stroke-linecap="round"/>
  <circle cx="60" cy="18" r="6" fill="url(#sa-g)"/>
  <rect x="24" y="36" width="72" height="60" rx="20" fill="url(#sa-g)"/>
  <rect x="33" y="46" width="54" height="34" rx="12" fill="url(#sa-g2)" opacity="0.95"/>
  <circle class="sa-eye" cx="49" cy="62" r="4.6" fill="#1E3A8A"/>
  <circle class="sa-eye" cx="71" cy="62" r="4.6" fill="#1E3A8A"/>
  <path d="M50 72 q10 7 20 0" stroke="#1E3A8A" stroke-width="3" fill="none" stroke-linecap="round"/>
  <rect x="52" y="88" width="16" height="10" rx="4" fill="url(#sa-g)"/>
</svg>"""


def hero(name: str = "智慧学伴", sub: str = "个人学情与班级讲评") -> None:
    st.markdown(
        f"""<div class="sa-hero">
              <div class="sa-avatar-wrap">
                 <div class="sa-ring"></div><div class="sa-ring d2"></div>
                 {avatar_img(132)}
              </div>
              <div class="sa-name">{name}</div>
              <div class="sa-sub">{sub}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def bubble(text: str) -> None:
    st.markdown(f'<div class="sa-bubble">{text}</div>', unsafe_allow_html=True)


def role_card(icon: str, title: str, desc: str) -> None:
    st.markdown(
        f"""<div class="sa-role-card">
              <div class="sa-role-ico">{icon}</div>
              <div class="sa-role-title">{title}</div>
              <div class="sa-role-desc">{desc}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def brand(title: str = "智慧学伴", sub: str = "智能体已就绪", *, compact: bool = False) -> None:
    style = "sa-brand sa-brand-compact" if compact else "sa-brand"
    st.markdown(
        f"""<div class="{style}">
              {avatar_img(30 if compact else 46)}
              <div><div class="sa-brand-t">{title}</div><div class="sa-brand-s">{sub}</div></div>
            </div>""",
        unsafe_allow_html=True,
    )


def chips(items: list[str]) -> None:
    if not items:
        return
    html = "".join(f'<span class="sa-chip">{x}</span>' for x in items)
    st.markdown(f'<div class="sa-strip">{html}</div>', unsafe_allow_html=True)


def typing() -> str:
    return '<span class="sa-dots"><span></span><span></span><span></span></span>'
