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
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
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

QA_PROMPT = """你是"智慧学伴"助教。只允许使用下面【事实】中的信息回答，禁止编造任何数字、题号或结论。
若【事实】不足以回答，就明确说"当前数据不足以回答"。

【事实】
{facts}

【问题】{question}

要求：不超过 150 字；若引用了指标或题目，请写出编号；不要给最终答案。"""


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


def answer_question(question: str, facts: dict, key: str | None, cache_dir: str) -> str:
    ident = question + json.dumps(facts, ensure_ascii=False, sort_keys=True)
    cached = read_cache(cache_dir, "qa", ident)
    if cached:
        return cached.get("answer", "")
    text = _chat(key, QA_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False, indent=1),
                                       question=question), temperature=0.2, max_tokens=500)
    write_cache(cache_dir, "qa", ident, {"question": question, "answer": text})
    return text


# --------------------------------------------------------------------------
# 离线兜底
# --------------------------------------------------------------------------
def offline_answer(question: str, facts: dict) -> str:
    """没有可用模型时的确定性回答：直接复述事实，绝不编造。"""
    s = facts.get("student", {})
    lines = [
        f"【离线模式】关于 {s.get('student_id', '该生')}：总分得分率 "
        f"{s.get('score_rate', '—')}，有效记录 {s.get('records', '—')} 条，"
        f"9 个指标中可下结论 {s.get('decided', 0)} 个。",
    ]
    weak = facts.get("weak_indicators") or []
    if weak:
        lines.append("证据充分的薄弱指标：" + "；".join(
            f"{w['indicator']}（n={w['n']}，掌握度 {w['mastery']:.0%}）" for w in weak[:3]))
    ins = facts.get("insufficient_indicators") or []
    if ins:
        lines.append(f"另有 {len(ins)} 个指标证据不足（如 {', '.join(ins[:3])}），按要求不下结论。")
    lines.append("启动本地模型后会给出更自然的解读；当前回答全部来自结构化统计。")
    return "\n\n".join(lines)


def build_facts(student: dict, stats_student: dict | None, class_rows: dict | None) -> dict:
    """把界面上的数据压成问答允许使用的"事实白名单"。"""
    return {
        "student": {
            "student_id": student["sid"],
            "class": student["cls"],
            "records": student["evidence_total"],
            "decided": student["coverage"]["decided"],
            "answered": student["coverage"]["answered"],
            "score_rate": (stats_student or {}).get("score_rate_percent", "—"),
        },
        "weak_indicators": [
            {"indicator": w["code"], "n": w["n"], "mastery": w["mastery"], "name": w["name"]}
            for w in student["weak"]
        ],
        "developing_indicators": [
            {"indicator": w["code"], "n": w["n"], "mastery": w["mastery"]} for w in student["developing"]
        ],
        "insufficient_indicators": [x["code"] for x in student["insufficient"]],
        "error_types": [
            {"type": d.get("error_type"), "code": d.get("error_type_code"),
             "question": d.get("question_id")}
            for d in student["errors"][:8]
        ],
        "class_theme_rates": class_rows or {},
    }
