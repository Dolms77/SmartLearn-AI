# -*- coding: utf-8 -*-
"""DeepSeek 接入层（可选）。

设计要点
--------
* 离线优先：无 Key / 无网络 / 调用失败 → 一律回退到规则结果与模板回答，界面不崩；
* 结果落盘缓存：演示时不实时请求，断网也能复现；
* 输出强校验：错误类型必须落在 C1–C6，关联指标必须属于 9 个指标，否则丢弃；
* 不打印、不回显完整 Key。
"""
from __future__ import annotations

import hashlib
import json
import os

BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-chat"

TYPE_NAME_TO_CODE = {
    "概念误解": "C1", "符号错误": "C2", "计算失误": "C3",
    "步骤遗漏": "C4", "表达不规范": "C5", "级联错误": "C6",
}
VALID_CODES = set(TYPE_NAME_TO_CODE.values())
INDICATORS = ["T01I1", "T01I2", "T01I3", "T02I1", "T02I2", "T02I3", "T03I1", "T03I2", "T03I3"]


# --------------------------------------------------------------------------
# Key 解析
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
    try:  # Streamlit secrets 存在时才用
        import streamlit as st

        if "DEEPSEEK_API_KEY" in st.secrets:
            return str(st.secrets["DEEPSEEK_API_KEY"]).strip()
    except Exception:  # noqa: BLE001 - 非 streamlit 环境或未配置
        pass
    return None


def mask(key: str | None) -> str:
    if not key:
        return "未配置"
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "已配置"


def status(key: str | None) -> dict:
    """不真正发请求，只报告可用性，避免界面启动就产生网络调用。"""
    online = bool(key)
    try:
        import openai  # noqa: F401
        has_sdk = True
    except ImportError:
        has_sdk = False
        online = False
    return {"online": online, "has_sdk": has_sdk, "key": mask(key),
            "reason": "" if online else ("未安装 openai" if not has_sdk else "未配置 API Key")}


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
DIAGNOSE_PROMPT = """你是一位七年级数学教师。请只依据给出的材料分析这名学生的作答错误，不要编造题目或数字。

【题目】{question_text}
【参考答案】{reference_answer}
【参考解析】{reference_solution}
【评分标准】{scoring_points}
【学生答案】{student_answer}
【学生解答过程】{student_process}
【评分点得分】{point_scores}

只输出 JSON，字段如下：
{{
  "error_type": "概念误解/符号错误/计算失误/步骤遗漏/表达不规范/级联错误 之一",
  "error_location": "出错的具体步骤",
  "root_cause": "学生可能的思维误区，1-2 句",
  "related_indicator": "九个观察指标之一：T01I1/T01I2/T01I3/T02I1/T02I2/T02I3/T03I1/T03I2/T03I3",
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

    return OpenAI(api_key=key, base_url=BASE_URL, timeout=40.0, max_retries=1)


def _chat(key: str, prompt: str, temperature: float = 0.3, max_tokens: int = 600,
          retries: int = 3) -> str:
    """带指数退避的调用：429/超时/网络抖动重试，其它错误直接抛出。"""
    import time

    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = _client(key).chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e)
            retryable = any(k in msg for k in ("429", "timed out", "Timeout", "502", "503",
                                               "504", "Connection", "overloaded"))
            if attempt == retries - 1 or not retryable:
                raise
            time.sleep(2 ** attempt)  # 1s, 2s, 4s
    raise last if last else RuntimeError("unknown error")


def _strip_json(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
    if t.endswith("```"):
        t = t.rsplit("```", 1)[0]
    return t.strip().lstrip("json").strip()


def validate_diagnosis(raw: dict) -> dict | None:
    """强校验：类型必须可映射到 C1–C6，指标必须在 9 个之内。"""
    if not isinstance(raw, dict):
        return None
    code = str(raw.get("error_type_code") or "").strip().upper()
    name = str(raw.get("error_type") or "").strip()
    if code not in VALID_CODES:
        code = TYPE_NAME_TO_CODE.get(name, "")
    if not code:
        return None
    ind = str(raw.get("related_indicator") or "").strip()
    if ind not in INDICATORS:
        ind = ""
    return {
        "error_type_code": code,
        "error_type": name or next(k for k, v in TYPE_NAME_TO_CODE.items() if v == code),
        "error_location": str(raw.get("error_location") or "")[:120],
        "root_cause": str(raw.get("root_cause") or "")[:200],
        "related_indicator": ind,
        "remediation_hint": str(raw.get("remediation_hint") or "")[:200],
    }


def diagnose_record(record: dict, key: str, cache_dir: str, use_cache: bool = True) -> dict | None:
    """对单条作答记录做 LLM 诊断。record 需含 question_text 等字段（cleaned_data 已带）。"""
    rid = record.get("record_id", "")
    if use_cache:
        cached = read_cache(cache_dir, "diag", rid)
        if cached:
            return cached
    prompt = DIAGNOSE_PROMPT.format(
        question_text=record.get("question_text", ""),
        reference_answer=record.get("reference_answer", ""),
        reference_solution=record.get("reference_solution", ""),
        scoring_points=record.get("scoring_points_def", ""),
        student_answer=record.get("student_answer", ""),
        student_process=record.get("student_process") or "（无解答过程）",
        point_scores=record.get("scoring_point_scores", ""),
    )
    try:
        payload = validate_diagnosis(json.loads(_strip_json(_chat(key, prompt, 0.2, 500))))
    except json.JSONDecodeError:
        return None
    except Exception as e:  # noqa: BLE001 - 网络/额度/鉴权统一降级
        return {"error": f"{type(e).__name__}: {e}"[:160]}
    if payload:
        payload.update({"record_id": rid, "source": "llm", "model": MODEL})
        write_cache(cache_dir, "diag", rid, payload)
    return payload


def answer_question(question: str, facts: dict, key: str, cache_dir: str) -> str:
    ident = question + json.dumps(facts, ensure_ascii=False, sort_keys=True)
    cached = read_cache(cache_dir, "qa", ident)
    if cached:
        return cached.get("answer", "")
    text = _chat(key, QA_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False, indent=1),
                                       question=question), temperature=0.2, max_tokens=400)
    write_cache(cache_dir, "qa", ident, {"question": question, "answer": text})
    return text


# --------------------------------------------------------------------------
# 离线兜底
# --------------------------------------------------------------------------
def offline_answer(question: str, facts: dict) -> str:
    """没有 Key 时的确定性回答：直接复述事实，绝不编造。"""
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
    lines.append("接入 DeepSeek 后可获得自然语言解读；当前回答全部来自结构化统计。")
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
            {"indicator": w["code"], "n": w["n"], "mastery": w["mastery"],
             "name": w["name"]} for w in student["weak"]
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
