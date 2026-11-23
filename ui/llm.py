# -*- coding: utf-8 -*-
"""LLM 接入层：默认走本地 Ollama（deepseek-r1），可切回 DeepSeek API。

设计要点
--------
* 双通道：`SA_LLM_PROVIDER=ollama`（默认，本地）/ `api`（DeepSeek 云）；
* 本地通道用 Ollama 原生 `/api/chat`，**不依赖 openai SDK**，且可关掉思考（think=False）省 6 倍时间；
* 离线优先：模型不可用 / 调用失败 → 一律回退规则结果与模板回答，界面不崩；
* 结果落盘缓存：演示时不实时请求，断网也能复现；
* 输出强校验：错误类型必须落在 C1–C6，关联指标必须属于 9 个指标，否则丢弃；
* 不打印、不回显完整 Key。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# 配置（全部可用环境变量覆盖）
# --------------------------------------------------------------------------
PROVIDER = os.environ.get("SA_LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL_ENV = os.environ.get("SA_OLLAMA_MODEL", "").strip()
PREFERRED_MODELS = ["deepseek-r1:8b", "deepseek-r1:7b", "deepseek-r1", "qwen2.5:7b"]
OLLAMA_THINK = os.environ.get("SA_OLLAMA_THINK", "0") == "1"
OLLAMA_NUM_PREDICT = int(os.environ.get("SA_OLLAMA_NUM_PREDICT", "700"))
OLLAMA_NUM_CTX = int(os.environ.get("SA_OLLAMA_NUM_CTX", "4096"))
OLLAMA_TIMEOUT = float(os.environ.get("SA_OLLAMA_TIMEOUT", "180"))

API_BASE_URL = os.environ.get("SA_API_BASE_URL", "https://api.deepseek.com/v1")
API_MODEL = os.environ.get("SA_API_MODEL", "deepseek-chat")

TYPE_NAME_TO_CODE = {
    "概念误解": "C1", "符号错误": "C2", "计算失误": "C3",
    "步骤遗漏": "C4", "表达不规范": "C5", "级联错误": "C6",
}
VALID_CODES = set(TYPE_NAME_TO_CODE.values())
INDICATORS = ["T01I1", "T01I2", "T01I3", "T02I1", "T02I2", "T02I3", "T03I1", "T03I2", "T03I3"]

_probe: dict = {"at": 0.0, "data": None}


# --------------------------------------------------------------------------
# 本地模型探测（缓存 10 秒，避免每次重绘都请求）
# --------------------------------------------------------------------------
def _http_json(url: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def list_local_models(force: bool = False) -> list[str]:
    now = time.time()
    if not force and _probe["data"] is not None and now - _probe["at"] < 10:
        return _probe["data"]
    try:
        data = _http_json(f"{OLLAMA_HOST}/api/tags", timeout=3.0)
        names = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        names = []
    _probe.update({"at": now, "data": names})
    return names


def pick_model(models: list[str] | None = None) -> str | None:
    """优先用环境变量指定；否则按 PREFERRED_MODELS 顺序找；再否则取任意 deepseek-r1。"""
    models = models if models is not None else list_local_models()
    if OLLAMA_MODEL_ENV:
        return OLLAMA_MODEL_ENV
    for name in PREFERRED_MODELS:
        if name in models:
            return name
        hit = next((m for m in models if m.split(":")[0] == name.split(":")[0]), None)
        if hit:
            return hit
    return models[0] if models else None


# --------------------------------------------------------------------------
# Key 解析（仅 API 模式需要）
# --------------------------------------------------------------------------
def resolve_key(explicit: str | None = None) -> str | None:
    """优先级：显式传入 > 环境变量 > 工程根目录 api.txt > st.secrets。"""
    if explicit and explicit.strip():
        return explicit.strip()
    env = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env:
        return env
    for p in ("api.txt", os.path.join("..", "api.txt")):
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    k = f.read().strip()
                if k.startswith("sk-"):
                    return k
            except OSError:
                pass
    try:
        import streamlit as st

        if "DEEPSEEK_API_KEY" in st.secrets:
            return str(st.secrets["DEEPSEEK_API_KEY"]).strip()
    except Exception:  # noqa: BLE001
        pass
    return None


def mask(key: str | None) -> str:
    if not key:
        return "未配置"
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "已配置"


def status() -> dict:
    """报告可用性。不产生 generation 请求：本地只查 /api/tags，云端只查 Key。"""
    if PROVIDER == "api":
        key = resolve_key()
        try:
            import openai  # noqa: F401
            has_sdk = True
        except ImportError:
            has_sdk = False
        online = bool(key and has_sdk)
        return {
            "online": online, "provider": "api", "model": API_MODEL, "models": [],
            "label": f"DeepSeek API · {API_MODEL}",
            "reason": "" if online else ("未安装 openai" if not has_sdk else "未配置 API Key"),
        }

    models = list_local_models()
    model = pick_model(models)
    if not models:
        reason = f"未连上 Ollama（{OLLAMA_HOST}）"
    elif not model:
        reason = "Ollama 已连接，但本地没有模型"
    else:
        reason = ""
    return {
        "online": bool(model), "provider": "ollama", "model": model or "", "models": models,
        "label": f"本地 · {(model or '无模型')}",
        "reason": reason or ("" if model else "模型不可用"),
    }


def available() -> bool:
    return bool(status()["online"])


# --------------------------------------------------------------------------
# 缓存
# --------------------------------------------------------------------------
def _cache_file(cache_dir: str, kind: str, ident: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    safe = hashlib.md5(ident.encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir, f"{kind}_{safe}.json")


def read_cache(cache_dir: str, kind: str, ident: str):
    p = _cache_file(cache_dir, kind, ident)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        # 旧版本可能把整段思考链缓存了，命中这类脏数据就当作没有
        if kind == "qa" and _looks_like_thought(str(data.get("answer") or "")):
            return None
        return data
    return None


def write_cache(cache_dir: str, kind: str, ident: str, payload) -> None:
    p = _cache_file(cache_dir, kind, ident)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------
# 提示词
# --------------------------------------------------------------------------
DIAGNOSE_PROMPT = """你是一位七年级数学教师。请只依据给出的材料复核这名学生的作答错误，不要编造题目或数字。

【题目】{question_text}（所属观察指标：{item_indicator}）
【参考答案】{reference_answer}
【参考解析】{reference_solution}
【评分标准】{scoring_points}
【学生答案】{student_answer}
【学生解答过程】{student_process}
【评分点得分】{point_scores}
【规则引擎初判】{rule_hint}

错误类型只能从下面六类中选一个（填中文名）：
C1 概念误解：不理解题意或核心概念
C2 符号错误：负数、去括号、不等号方向等符号处理错误
C3 计算失误：基本运算算错（如 2×4+3 算成 14）
C4 步骤遗漏：跳步、缺少检验或缺少关键步骤
C5 表达不规范：结果格式、单位、结论表述不规范
C6 级联错误：前一步错导致后续步骤全部不得分

请先判断规则引擎的初判是否成立：
- 若成立，输出与初判相同的类型，reason 说明依据；
- 若不成立，输出你判断的类型，reason 说明为什么初判不成立。

只输出 JSON：
{{
  "agree_with_rule": true 或 false,
  "error_type": "六类之一的中文名",
  "error_location": "出错的具体步骤",
  "root_cause": "学生可能的思维误区，1-2 句",
  "reason": "同意或改判的理由，1-2 句",
  "remediation_hint": "补救提示，1-2 句，不直接给出最终答案"
}}"""

QA_PROMPT = """你就是"智慧学伴"，一个陪七年级学生看学情的学伴。用第二人称，口语化，像老师课间跟学生说话。

【事实】（唯一可用的数据，不得编造其他数字）
{facts}

【学生问】{question}

硬性要求：
1. 直接回答。**不要**复述问题，**不要**写"首先/用户问/我需要/根据事实/让我分析"这类过程，**不要**输出思考链。
2. 不超过 4 句、120 字以内；必要时用短横线列 2–3 点。
3. 每个结论后面带依据（指标编号 + 证据条数 n）。
4. 事实里没有的，就说"这个我还看不出来"，不要猜。
5. 不要给出任何题目的答案。

直接输出答案正文："""

# 模型（尤其是 R1 蒸馏版）会把"我先分析一下问题"整段写进正文，这里做兜底清洗
_COT_MARKERS = ("首先", "用户的问题", "用户问", "用户要求", "我需要", "让我", "分析一下",
                "根据事实", "【事实】", "let me", "First,", "The user")
_ANSWER_MARKERS = ("直接回答", "答案：", "答：", "回答：", "结论：")


# --------------------------------------------------------------------------
# 调用
# --------------------------------------------------------------------------
def _client(key: str):
    from openai import OpenAI

    return OpenAI(api_key=key, base_url=API_BASE_URL, timeout=40.0, max_retries=1)


def _chat_api(key: str, prompt: str, temperature: float, max_tokens: int) -> str:
    resp = _client(key).chat.completions.create(
        model=API_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def _chat_ollama(prompt: str, temperature: float, max_tokens: int) -> str:
    model = pick_model()
    if not model:
        raise RuntimeError("本地没有可用模型（先运行 ollama pull deepseek-r1:8b）")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": OLLAMA_THINK,          # 关闭思考：1.5s vs 9.5s，结构化任务无需长推理
        "options": {
            "temperature": temperature,
            "num_predict": max(max_tokens, OLLAMA_NUM_PREDICT),
            "num_ctx": OLLAMA_NUM_CTX,
        },
    }
    data = _http_json(f"{OLLAMA_HOST}/api/chat", payload, timeout=OLLAMA_TIMEOUT)
    msg = data.get("message") or {}
    text = (msg.get("content") or "").strip()
    if not text and msg.get("thinking"):
        text = str(msg["thinking"]).strip()   # 兜底：万一只回了思考
    return text


def _chat(key: str | None, prompt: str, temperature: float = 0.3, max_tokens: int = 700,
          retries: int = 2) -> str:
    """统一入口：本地优先，失败重试；API 模式沿用 openai SDK。"""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            if PROVIDER == "api":
                if not key:
                    raise RuntimeError("API 模式需要 Key")
                return _chat_api(key, prompt, temperature, max_tokens)
            return _chat_ollama(prompt, temperature, max_tokens)
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt == retries - 1:
                break
            time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError("unknown error")


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
    if t.rstrip().endswith("```"):
        t = t.rsplit("```", 1)[0]
    return t.strip().lstrip("json").strip()


def _extract_json(text: str) -> dict:
    """从模型输出里取出第一个完整 JSON 对象（忽略前后解释或重复输出）。"""
    t = _strip_fences(text)
    start = t.find("{")
    if start == -1:
        raise ValueError("no json object found")
    obj, _ = json.JSONDecoder().raw_decode(t[start:])
    if not isinstance(obj, dict):
        raise ValueError("not a json object")
    return obj


def _code_from_text(text: str) -> str:
    """从模型输出里认出 C1–C6：支持 "C2"、"C2 符号错误"、"符号错误"、"计算错误" 等写法。"""
    s = (text or "").strip()
    m = re.search(r"C\s*([1-6])", s, re.I)
    if m:
        return f"C{m.group(1)}"
    for cn, code in TYPE_NAME_TO_CODE.items():
        if cn in s:
            return code
    for alias, code in (("级联", "C6"), ("连锁", "C6"), ("跳步", "C4"), ("遗漏", "C4"),
                        ("符号", "C2"), ("计算", "C3"), ("运算", "C3"),
                        ("表达", "C5"), ("单位", "C5"), ("规范", "C5"),
                        ("概念", "C1"), ("理解", "C1")):
        if alias in s:
            return code
    return ""


def validate_diagnosis(raw: dict) -> dict | None:
    """强校验：类型必须可映射到 C1–C6，指标必须在 9 个之内。"""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("error_type") or "").strip()
    code = _code_from_text(str(raw.get("error_type_code") or "")) or _code_from_text(name)
    if not code:
        return None
    canonical = next(k for k, v in TYPE_NAME_TO_CODE.items() if v == code)
    ind = str(raw.get("related_indicator") or "").strip()
    if ind not in INDICATORS:
        ind = ""
    return {
        "error_type_code": code,
        "error_type": canonical,
        "error_location": str(raw.get("error_location") or "")[:120],
        "root_cause": str(raw.get("root_cause") or "")[:200],
        "related_indicator": ind,
        "remediation_hint": str(raw.get("remediation_hint") or "")[:200],
    }


def diagnose_record(record: dict, key: str | None, cache_dir: str, use_cache: bool = True,
                    rule_hint: str = "") -> dict | None:
    """复核式诊断：把规则引擎初判交给模型确认或改判。

    rule_hint 形如 "C1 概念误解（依据：P1=0 且后续全为 0）"；为空时退化为无先验的独立诊断。
    """
    rid = record.get("record_id", "")
    item_ind = record.get("indicator_id", "") or ""
    if use_cache:
        cached = read_cache(cache_dir, "diag", rid)
        if cached:
            return cached
    prompt = DIAGNOSE_PROMPT.format(
        question_text=record.get("question_text", ""),
        item_indicator=item_ind,
        reference_answer=record.get("reference_answer", ""),
        reference_solution=record.get("reference_solution", ""),
        scoring_points=record.get("scoring_points_def", ""),
        student_answer=record.get("student_answer", ""),
        student_process=record.get("student_process") or "（无解答过程）",
        point_scores=record.get("scoring_point_scores", ""),
        rule_hint=rule_hint or "（无，请独立判断）",
    )
    try:
        raw = _extract_json(_chat(key, prompt, temperature=0.2, max_tokens=700))
    except (ValueError, json.JSONDecodeError):
        # 再给一次机会：强制"只输出 JSON"
        try:
            raw = _extract_json(_chat(key, prompt + "\n\n注意：只输出 JSON 对象，不要任何解释或代码块。",
                                      temperature=0.1, max_tokens=700))
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"[:160]}
    except Exception as e:  # noqa: BLE001 - 网络/模型不可用统一降级
        return {"error": f"{type(e).__name__}: {e}"[:160]}

    payload = validate_diagnosis(raw)
    if payload:
        # 口径：诊断挂在"某题"上，指标以题目归属为准
        payload["related_indicator"] = item_ind or payload.get("related_indicator") or ""
        payload["reason"] = str(raw.get("reason") or "")[:200]
        agree = raw.get("agree_with_rule")
        payload["agree_with_rule"] = agree if isinstance(agree, bool) else None
        st = status()
        payload.update({"record_id": rid, "source": "llm",
                        "model": st.get("model") or st.get("label")})
        write_cache(cache_dir, "diag", rid, payload)
    return payload


def _looks_like_thought(text: str) -> bool:
    """判断模型是不是把思考过程当答案交上来了。"""
    head = text.strip()[:160]
    if any(m in head for m in _COT_MARKERS):
        return True
    if text.count("用户") >= 2 and len(text) > 200:
        return True
    return len(text) > 500


def _clean_answer(text: str) -> str:
    """去掉思考链、代码围栏与"答："之前的铺垫，只留正文；不合格就返回空串交给模板。"""
    t = _strip_fences(text or "")
    for marker in _ANSWER_MARKERS:
        if marker in t:
            t = t.rsplit(marker, 1)[-1]
    kept = []
    for line in t.splitlines():
        s = line.strip()
        if not s:
            continue
        if any(s.startswith(m) for m in _COT_MARKERS):
            continue
        if s.startswith("【") and "】" in s:      # 复述标题
            continue
        kept.append(s)
    # 最后一行常被截断，若不以句末标点收尾就丢掉
    while kept and not kept[-1].rstrip().endswith(("。", "！", "？", "）", ")", "”", ".", "…")):
        kept.pop()
    out = "\n".join(kept).strip()
    if not out or len(out) < 20 or len(out) > 320:
        return ""
    if out.count("（") != out.count("）") or out.count("**") % 2:
        return ""                                  # 括号/加粗不配对 → 视为残缺
    if _looks_like_thought(out):
        return ""
    return out


def _pct(v) -> str:
    return f"{v:.0%}" if isinstance(v, (int, float)) else "—"


_BAND_CN = {"mastered": "已掌握", "developing": "发展中",
            "weak": "薄弱", "insufficient": "证据不足"}


def _band_cn(band) -> str:
    return _BAND_CN.get(str(band or ""), "")


def _band_clause(item: dict) -> str:
    """把 band 说成一句人话；证据不足时明确说“暂不下结论”。"""
    band = str(item.get("band") or "")
    if band == "insufficient":
        return "该指标证据还不够 3 条，暂不下结论；"
    cn = _band_cn(band)
    return f"判定为{cn}；" if cn else ""


def _teacher_answer(question: str, facts: dict,
                    history: list[dict] | None = None) -> str:
    """教师视角：按意图分派——讲评排序 / 评分点 / 关注名单 / 证据覆盖 / 两班对比 / 指标。"""
    cls = facts.get("class", "这个班")
    n = facts.get("students")
    ov = facts.get("overall")
    qs = facts.get("weakest_questions") or []
    inds = facts.get("weakest_indicators") or []
    sps = facts.get("scoring_points") or []
    risky = facts.get("students_at_risk") or []
    cov = facts.get("coverage") or {}
    cmp_ = facts.get("class_compare") or {}
    q = question or ""

    # ⓪ 追问：第 N 弱的指标
    idx = _ordinal_index(q)
    if idx is not None:
        if len(inds) > idx:
            x = inds[idx]
            return (f"排在第 {idx + 1} 位的是{x['indicator']}（{_pct(x['rate'])}）。"
                    f"和第一位相比，差距主要在支撑它的题目上；建议按这个指标再准备一组变式题。")
        if len(qs) > idx:
            x = qs[idx]
            return (f"排在第 {idx + 1} 位的题目是 {x['question']}（得分率 {_pct(x['rate'])}，"
                    f"{x['n']} 人作答）。")

    # ① 追问：把刚才提到的内容讲细
    if any(k in q for k in _FOLLOWUP_HINTS):
        last = ""
        for msg in reversed(history or []):
            if msg.get("role") == "assistant":
                last = str(msg.get("content") or "")
                break
        for x in inds:
            if x["indicator"] in last:
                return (f"刚才提到的 {x['indicator']} 是 {cls} 本周最弱的指标之一，"
                        f"得分率 {_pct(x['rate'])}，样本 {x['n']} 条。"
                        f"建议先看它在评分点上的分布，再决定讲哪一步。")
        for s in sps:
            if s["评分点"] in last:
                return (f"刚才提到的 {s['评分点']} 来自 {s['题号']}，"
                        f"全班 {s['正确/总数']} 做对，题干是「{s['题干']}」。"
                        f"讲评时先让学生复述这一步的推理，再给一道同型变式。")

    # ② 评分点：讲评“哪一步”
    if any(k in q for k in ("评分点", "扣分", "丢分", "哪一步", "步骤")):
        if not sps:
            return f"{cls} 暂时没有可用的评分点统计，可以先用题目级结论。"
        body = "、".join(f"{s['评分点']}（{s['正确/总数']}）" for s in sps[:3])
        return (f"全班最集中的失分点在 {body}。"
                f"讲评时只讲这三步：先让学生写出自己的步骤，再对照评分点看丢在哪一步，"
                f"最后当堂做一道同类型变式。")

    # ③ 关注名单
    if any(k in q for k in ("关注", "学生", "谁", "名单")):
        if not risky:
            return f"{cls} 目前没有“证据不足”或掌握度明显偏低的学生。"
        names = "；".join(f"{r['student']}（{r['reason']}，{r['decided']}/9 可判定）"
                          for r in risky[:4])
        return (f"需要单独关注的有 {len(risky)} 人：{names}。"
                f"建议先给“证据不足”的学生补 3 道同指标题，再谈掌握度。")

    # ④ 证据覆盖
    if any(k in q for k in ("覆盖", "证据", "格子", "够不够", "准不准", "可信")):
        decided, stud, rate = cov.get("decided"), cov.get("students"), cov.get("rate")
        if decided and stud:
            return (f"{cls} 共 {stud} 名学生、{stud * 9} 个「学生×指标」格子，"
                    f"其中 {decided} 个达到 3 条证据门槛（{_pct(rate)}）；"
                    f"其余格子证据不足，我不下结论。")
        return f"{cls} 暂无可用的覆盖统计。"

    # ⑤ 两班对比
    if any(k in q for k in ("两个班", "对比", "比较", "差在哪", "哪边")):
        diffs = []
        for t in ("T01", "T02", "T03"):
            vals = {c: cmp_[c].get(t) for c in cmp_ if cmp_.get(c, {}).get(t) is not None}
            if len(vals) == 2:
                (c1, v1), (c2, v2) = list(vals.items())
                diffs.append((abs(v1 - v2), t, c1, v1, c2, v2))
        if diffs:
            diffs.sort(reverse=True)
            _, t, c1, v1, c2, v2 = diffs[0]
            higher = c1 if v1 >= v2 else c2
            return (f"两班差异最大的是 {t}：{c1} {_pct(v1)}、{c2} {_pct(v2)}，"
                    f"相差 {abs(v1 - v2) * 100:.0f} 个百分点（{higher} 更高）。"
                    f"建议按这个主题分层布置作业。")
        return f"{cls} 暂无可比的两班数据。"

    # ⑥ 讲评排序
    if any(k in q for k in ("讲", "上课", "安排", "备课")):
        parts = []
        if qs:
            parts.append("先讲 " + "、".join(
                f"{x['question']}（得分率 {_pct(x['rate'])}，{x['n']} 人作答）" for x in qs[:3]))
        if inds:
            parts.append("再补指标 " + "、".join(
                f"{x['indicator']}（{_pct(x['rate'])}）" for x in inds[:2]))
        if not parts:
            return f"{cls} 暂时没有足够数据支持讲评排序。"
        return ("建议这样排：" + "；".join(parts) +
                "。每题先让学生说思路，再对照评分点讲丢分的那一步，最后当堂做一道同类型变式。")

    # ⑦ 指标级
    if any(k in q for k in ("指标", "最弱", "薄弱", "哪块", "哪个知识点")):
        if not inds:
            return f"{cls} 目前没有证据充分的共性薄弱指标。"
        return (f"{cls} 最弱的指标是 " + "、".join(
            f"{x['indicator']}（{_pct(x['rate'])}）" for x in inds[:3]) +
            "。建议按指标分组补练，证据不足的学生单独做补充观察。")

    head = f"{cls}：{n} 名学生" + (f"，班级得分率 {_pct(ov)}" if ov is not None else "")
    extra = f"最薄弱的题是 {qs[0]['question']}（{_pct(qs[0]['rate'])}）。" if qs else ""
    return head + "。" + extra + "可以问我「下周该讲哪几道题」「哪个评分点全班都错」或「哪些学生要单独关注」。"


_ORDINALS = (("第二", 1), ("第三", 2), ("第四", 3), ("第2", 1), ("第3", 2), ("第4", 3))
_FOLLOWUP_HINTS = ("再详细", "展开", "具体一点", "具体点", "多说", "刚才", "上面", "那个指标", "这一个")


def _ordinal_index(q: str) -> int | None:
    for key, idx in _ORDINALS:
        if key in q:
            return idx
    return None


def _last_topic(history: list[dict] | None, facts: dict) -> dict | None:
    """从最近一条助手回答里找出刚才在讲哪个指标（按中文名匹配）。"""
    if not history:
        return None
    last = ""
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            last = str(msg.get("content") or "")
            break
    if not last:
        return None
    pool = ((facts.get("weak_indicators") or []) + (facts.get("developing_indicators") or [])
            + (facts.get("insufficient_indicators") or []))
    hits = [x for x in pool if (x.get("name") or "") and x["name"] in last]
    if hits:
        return max(hits, key=lambda x: len(x["name"]))
    return None


def _answer_from_facts(question: str, facts: dict,
                       history: list[dict] | None = None) -> str:
    """确定性兜底回答：模型输出不可用时，用事实拼一段人话。

    history：最近几轮问答，用于处理“那第二薄弱呢”“再详细点”这类追问。
    """
    if "class" in facts and "student" not in facts:      # 教师视角的班级事实
        return _teacher_answer(question, facts, history)
    s = facts.get("student", {})
    sid = s.get("student_id", "该生")
    weak = facts.get("weak_indicators") or []
    ins = facts.get("insufficient_indicators") or []
    errs = facts.get("error_types") or []
    q = question or ""

    # ⓪ 追问：按序数取第 N 个薄弱/发展中指标
    idx = _ordinal_index(q)
    if idx is not None:
        pool = weak + (facts.get("developing_indicators") or []) + ins
        if len(pool) > idx:
            w = pool[idx]
            return (f"排在第 {idx + 1} 位的是{w.get('name') or w['indicator']}，"
                    f"掌握度 {w.get('mastery', 0):.0%}、证据 {w.get('n', 0)} 条。"
                    f"{_band_clause(w)}"
                    f"要不要我把它前面的那道也一起排进这周的计划？")

    # ① 追问：把刚才提到的那个指标讲细一点
    if any(k in q for k in _FOLLOWUP_HINTS):
        topic = _last_topic(history, facts)
        if topic:
            return (f"刚才说的是{topic.get('name') or topic['indicator']}："
                    f"掌握度 {topic.get('mastery', 0):.0%}，有 {topic.get('n', 0)} 条作答证据，"
                    f"{_band_clause(topic)}"
                    f"想深入的话，打开「我的学情」看这个指标的题目明细，能看到每题丢在哪个评分点。")

    if any(k in q for k in ("证据不足", "不足", "看不出", "哪些结论", "不确定")):
        if not ins:
            return f"{sid} 的 9 个指标目前都有至少 3 条证据，没有「证据不足」的结论。"
        items = "；".join(f"{i.get('name') or i['indicator']}（只有 {i['n']} 条）"
                         for i in ins[:4])
        return (f"{sid} 现在有 {len(ins)} 个指标证据不够 3 条，我先不下结论：{items}。"
                f"这些地方需要再做几道题补证据，才能判断是真不会还是只是没做到。")

    if any(k in q for k in ("薄弱", "最弱", "拖后腿", "哪里差", "掌握")):
        if not weak:
            return f"{sid} 目前没有证据充分又明显薄弱的指标，可以先按课内节奏走。"
        top = weak[0]
        more = "；".join(f"{w.get('name') or w['indicator']}（{w.get('mastery', 0):.0%}，证据 {w['n']} 条）"
                        for w in weak[1:3])
        return (f"最该先补的是 {top.get('name') or top['indicator']}，"
                f"掌握度 {top.get('mastery', 0):.0%}、证据 {top['n']} 条。"
                + (f"其次是 {more}。" if more else "")
                + "这些数字都来自你的实际作答，点开「我的学情」能看到具体是哪几道题。")

    if any(k in q for k in ("错", "粗心", "错因", "类型")):
        summary = facts.get("error_summary") or {}
        by_type = summary.get("by_type") or {}
        if not by_type:
            return f"{sid} 暂时没有可归因的错误记录。"
        top3 = sorted(by_type.items(), key=lambda kv: -kv[1])[:3]
        top = "、".join(f"{k} {v} 处" for k, v in top3)
        return (f"{sid} 的错误主要是：{top}。可以打开「我的学情」按指标看是哪几道题、"
                f"具体丢在哪个评分点上。")

    if any(k in q for k in ("计划", "建议", "下一步", "练什么", "怎么学", "安排")):
        if not weak:
            return f"{sid} 目前没有证据充分的薄弱点，建议保持每周一次综合练习，重点练「不等式与不等式组」的应用题。"
        steps = "；".join(f"第{i}步补「{w.get('name') or w['indicator']}」"
                         for i, w in enumerate(weak[:3], 1))
        return (f"给你一个三步计划：{steps}。每个指标先做 2 道没做过的同类题，"
                f"做完对照评分点自查；连续 2 次满分再进入下一个。")

    if weak:
        return (f"{sid}：{s.get('records','—')} 条记录，9 个指标里 {s.get('decided', 0)} 个可下结论。"
                f"最薄弱的是 {weak[0].get('name') or weak[0]['indicator']}"
                f"（{weak[0].get('mastery', 0):.0%}，证据 {weak[0]['n']} 条），"
                f"另有 {len(ins)} 个指标证据不足。")
    return (f"{sid}：{s.get('records','—')} 条记录，9 个指标里 {s.get('decided', 0)} 个可下结论，"
            f"{len(ins)} 个证据不足。可以问我「哪里最薄弱」或「哪些结论证据不足」。")


REWRITE_PROMPT_STUDENT = """你是"智慧学伴"，正在跟一位七年级学生说话：用第二人称"你"，语气亲切、短句，不啰嗦。
学生看到的是自己的数据，可以直接说"你哪块薄弱""你该练哪几题"。

下面【事实结论】已经核实过，**数字和结论一个字都不能改**，你只负责把语气改得更像人话。
不要输出思考过程，不要解释你在做什么，不要复述问题；也不要用「根据已核实」「根据分析」这类空话开头，直接说结论（不超过 3 句）；
不要推测原因，只陈述事实与建议；不要把「证据条数」说成「错题数」或「做题数」；
不要编造【事实结论】里没有的细分信息（例如每条证据分别对应哪个评分点、错误的具体环节）。
如果【上文】里已经讲过某个指标，直接用"刚才提到的…"衔接，不要重复寒暄。

【上文】{context}

【事实结论】{draft}

【学生问】{question}

直接给回答："""

REWRITE_PROMPT_TEACHER = """你是"智慧学伴"的教师端助手，正在向一位中学数学老师口头汇报班级学情。
用第三人称称呼班级（"这个班""您班上"），**不要用"你"去指代学生或老师本人**；
语气专业、克制，像教研组内的简短沟通，不超过 3 句。

下面【事实结论】已经核实过，**数字和结论一个字都不能改**，你只负责把语气改得更自然。
不要输出思考过程，不要解释你在做什么，不要复述问题；也不要用「根据已核实」「根据分析」这类空话开头，直接说结论。
不要编造学生姓名或班级里不存在的信息，只能用【事实结论】里的数字；
涉及两个班对比时，必须保留班级编号（如 DC01、DC02），不要用「这个班」「您班上」代指，避免指代混乱；
不要推测原因（如「因为学生粗心」「思路错误」），只陈述事实与建议。
如果【上文】里已经点名某个指标或评分点，用"刚才提到的…"衔接，不要重复开场。

【上文】{context}

【事实结论】{draft}

【教师问】{question}

直接给回答："""

# 兼容旧引用：默认学生版
REWRITE_PROMPT = REWRITE_PROMPT_STUDENT


def _rewrite_prompt(role: str) -> str:
    """按角色取改写提示词：学生=第二人称，教师=第三人称讲评口吻。"""
    return REWRITE_PROMPT_TEACHER if str(role).lower().startswith("teacher") else REWRITE_PROMPT_STUDENT


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text or ""))


_PLACEHOLDER_RE = re.compile(r"[\[\]【】]|占位|待补充|XX|具体丢分步骤")


def _has_placeholder(text: str) -> bool:
    """模型偶尔会吐出 [具体丢分步骤] 这类占位符，一律判为不合格。"""
    return bool(_PLACEHOLDER_RE.search(text or ""))


def _context_block(history: list[dict] | None) -> str:
    """把最近两轮问答压成提示词里的【上文】。只保留文字，不做任何推理。"""
    if not history:
        return "（这是第一轮，没有上文）"
    lines = []
    for msg in history[-4:]:
        role = "用户" if msg.get("role") == "user" else "助手"
        text = re.sub(r"\s+", " ", str(msg.get("content") or ""))[:120]
        if text:
            lines.append(f"{role}：{text}")
    return "\n".join(lines) if lines else "（这是第一轮，没有上文）"


def _safe_rewrite(draft: str, question: str, key: str | None, role: str = "student",
                  context: str = "") -> str:
    """让模型改写 draft；改坏了（新增数字 / 编造指标 / 带思考链）就退回 draft。"""
    try:
        raw = _chat(key, _rewrite_prompt(role).format(
            draft=draft, question=question, context=context or "（这是第一轮，没有上文）"),
            temperature=0.3, max_tokens=300)
        text = _clean_answer(raw)
    except Exception:  # noqa: BLE001
        return ""
    if not text:
        return ""
    allowed_nums = _numbers(draft) | {"3", "9"}      # 3=门槛、9=指标总数
    if _numbers(text) - allowed_nums:
        return ""                                    # 冒出 draft 里没有的数字 → 拒
    codes = set(re.findall(r"T0[123]I[123]", text))
    if codes - set(re.findall(r"T0[123]I[123]", draft)):
        return ""                                    # 编造指标编号 → 拒
    if _has_placeholder(text):
        return ""                                    # 出现占位符 → 拒
    if re.search(r"T0[123]I[123][^。；]{0,6}道题", text):
        return ""                                    # 把指标说成题目 → 拒（教师端常见）
    for word in ("因为", "导致", "由于", "部分学生"):
        if word in text and word not in draft:
            return ""                                # 草稿里没有的因果/范围 → 视为推测，拒
    cls_draft = set(re.findall(r"DC\d{2}", draft))
    if len(cls_draft) >= 2 and not cls_draft <= set(re.findall(r"DC\d{2}", text)):
        return ""                                    # 两班对比丢了班级编号 → 指代会混乱，拒
    if "评分点" in text and "评分点" not in draft:
        return ""                                    # 草稿没有评分点明细，模型编不出来 → 拒
    return text


def answer_question(question: str, facts: dict, key: str | None, cache_dir: str,
                    role: str = "student", history: list[dict] | None = None) -> str:
    """先由事实生成"不会错"的草稿，再让模型改写口吻；改写不达标就用草稿。

    role: student / teacher —— 决定改写提示词与缓存分桶（两种口吻互不串用）。
    history: 最近几轮问答，用于指代消解（“那第二薄弱呢”“再详细点”）与提示词的【上文】。
    """
    context = _context_block(history)
    hist_key = hashlib.md5(context.encode("utf-8")).hexdigest()[:8] if history else "0"
    ident = (f"{role}|{hist_key}|" + question
             + json.dumps(facts, ensure_ascii=False, sort_keys=True))
    cached = read_cache(cache_dir, "qa", ident)
    if cached:
        return cached.get("answer", "")

    draft = _answer_from_facts(question, facts, history)
    # 指代类追问（“那第二薄弱呢”“再详细点”）草稿已经足够自然，且模型改写容易编细节 → 不交给模型
    is_followup = _ordinal_index(question) is not None or any(
        k in question for k in _FOLLOWUP_HINTS)
    text = draft if is_followup else (
        _safe_rewrite(draft, question, key, role=role, context=context) or draft)
    source = "model" if text != draft else "template"
    write_cache(cache_dir, "qa", ident,
                {"question": question, "role": role, "answer": text,
                 "source": source, "draft": draft})
    return text


# --------------------------------------------------------------------------
# 离线兜底
# --------------------------------------------------------------------------
def offline_answer(question: str, facts: dict,
                   history: list[dict] | None = None) -> str:
    """没有可用模型时的确定性回答：直接复述事实，绝不编造。"""
    body = _answer_from_facts(question, facts, history)
    return f"{body}\n\n（离线模式：以上内容全部来自结构化统计，未经模型改写。）"


def build_facts(student: dict, stats_student: dict | None, class_rows: dict | None) -> dict:
    """把界面上的数据压成问答允许使用的"事实白名单"（尽量给全，免得模型瞎猜）。"""
    ins = [{"indicator": x["code"], "name": x["name"], "n": x["n"]}
           for x in student["insufficient"]]
    errs = student["errors"]
    by_type: dict[str, int] = {}
    for e in errs:
        k = e.get("error_type") or "未分类"
        by_type[k] = by_type.get(k, 0) + 1
    return {
        "student": {
            "student_id": student["sid"],
            "class": student["cls"],
            "records": student["evidence_total"],
            "decided": student["coverage"]["decided"],
            "answered": student["coverage"]["answered"],
            "total_indicators": 9,
            "score_rate": (stats_student or {}).get("score_rate_percent", "—"),
            "threshold": 3,
        },
        "weak_indicators": [
            {"indicator": w["code"], "n": w["n"], "mastery": w["mastery"],
             "name": w["name"], "band": w.get("band", "weak")}
            for w in student["weak"]
        ],
        "developing_indicators": [
            {"indicator": w["code"], "n": w["n"], "mastery": w["mastery"],
             "name": w["name"], "band": w.get("band", "developing")}
            for w in student["developing"]
        ],
        "insufficient_indicators": [{**i, "band": "insufficient"} for i in ins],
        "error_summary": {"total": len(errs), "by_type": by_type},
        "error_types": [
            {"type": d.get("error_type"), "code": d.get("error_type_code"),
             "question": d.get("question_id")}
            for d in errs[:8]
        ],
        "class_theme_rates": class_rows or {},
    }
