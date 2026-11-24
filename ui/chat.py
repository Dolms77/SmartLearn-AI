# -*- coding: utf-8 -*-
"""智能对话窗口：像通用 AI 助手一样的气泡对话，答案受"事实白名单"约束。"""
from __future__ import annotations

import re
import agent_bridge as AB

import streamlit as st

import adapter as A
import insights as I
import labels
import llm
import theme

STUDENT_GREET = (
    "你好，我是你的学伴。我已经读完你**全部 {n} 条**作答记录，"
    "能定位到具体题号和评分点。\n\n"
    "我只在证据足够时下结论——所以你可能会听到我说「这个还看不出」，"
    "那不是敷衍，是数据真的不够。"
)

TEACHER_GREET = (
    "你好，我是 {cls} 的班级助手。我已汇总 **{n} 名学生 / {m} 条**作答记录，"
    "可以按主题、指标、评分点三个粒度给你讲评建议。\n\n"
    "未达到 3 条证据的「学生×指标」格子不判定薄弱；缺证据与学不会不是一回事。"
)

STUDENT_CHIPS = ["我哪一块最薄弱？", "哪些结论其实证据不足？", "我错得最多的是什么类型？",
                 "给我一个这周能做完的计划"]
TEACHER_CHIPS = ["这个班最该讲哪几道题？", "哪个评分点全班都错？", "两个班差在哪？",
                 "哪些学生需要单独关注？"]


def _key(role: str, ident: str) -> str:
    return f"chat_{role}_{ident}"


def history(role: str, ident: str) -> list[dict]:
    return st.session_state.setdefault(_key(role, ident), [])


def _teacher_facts(bundle: dict, cls: str) -> dict:
    """教师端事实白名单：全部按“本班”口径，含评分点、学生名单与证据覆盖。"""
    cv = A.class_view(bundle, cls)
    row = cv["class_theme"].get(cls, {})
    qrates = I.class_question_rates(bundle, cls)
    irates = I.class_indicator_rates(bundle, cls)
    cov = I.class_mastery_summary(bundle).get(cls, {})

    weak_q = sorted(qrates.items(), key=lambda kv: kv[1]["rate"])[:5]
    weak_i = sorted(((c, v) for c, v in irates.items() if v["rate"] is not None),
                    key=lambda kv: kv[1]["rate"])[:5]
    return {
        "class": cls,
        "students": row.get("students"),
        "overall": row.get("overall"),
        "theme_rates": {t: row.get(t) for t in ("T01", "T02", "T03")},
        "weakest_indicators": [{"indicator": c, "name": A.INDICATOR_NAMES.get(c, c), "rate": v["rate"], "n": v["n"]} for c, v in weak_i],
        "weakest_questions": [{"question": k, "rate": v["rate"], "n": v["n"],
                               "text": v.get("text", "")} for k, v in weak_q],
        "scoring_points": I.class_scoring_points(bundle, cls, limit=8),
        "students_at_risk": I.students_at_risk(bundle, cls, limit=None),
        "coverage": {"decided": cov.get("decided"), "students": cov.get("students"),
                     "rate": cov.get("decided_rate")},
        "class_compare": {c: cv["class_theme"].get(c, {}) for c in cv["classes"]},
        "note": "全部为班级口径；证据不足（n<3）的指标不得下结论。",
    }


def _answer(question: str, role: str, ident: str, bundle: dict, key: str | None, cache_dir: str,
            history: list[dict] | None = None) -> str:
    if role == "student":
        stt = (bundle.get("statistics") or {}).get("by_student", {}).get(ident, {})
        v = A.student_view(bundle, ident)
        facts = llm.build_facts(v, stt, A.class_view(bundle)["class_theme"])
    else:
        facts = _teacher_facts(bundle, ident)

    trace = []
    evidence = []
    if role == 'student':
        denied = any(k in question for k in ('全班', '这个班', '两个班', '同学名单')) or re.search(r'D\d{2}', question.replace(ident, ''))
        if not denied:
            # 新建协调器，不复用 cache_resource 内的跨用户会话记忆。
            mod = AB._load_module()
            coord = mod.Coordinator(mod.Bundle(bundle.get('output_dir') or AB.DEFAULT_OUTPUT))
            wants_plan = any(k in question for k in ('计划', '建议', '练什么', '怎么学', '安排', '下一步'))
            intents = ['diagnosis'] + (['recommend'] if wants_plan else []) + ['evidence']
            coord.parse = lambda _: {'question': question, 'student_id': ident, 'intents': intents, 'detail': True}
            try:
                result = coord.run(question)
                trace = (result.get('trace') or {}).get('steps') or []
                valid_inds = {x['indicator'] for x in facts['weak_indicators'] + facts['developing_indicators'] if x['n'] >= 3}
                known_questions = set((bundle.get('questions') or {}).keys())
                # Bundle.question_map 是正式题号白名单。
                known_questions |= set(coord.b.question_map)
                for item in result.get('results', []):
                    if item.get('agent') == 'RecommendationAgent':
                        facts['collaboration_recommendations'] = _validated_recommendations(item.get('recommendations', []), valid_inds, coord.b.question_map)
                    if item.get('agent') == 'EvidenceAgent':
                        evidence = item.get('evidence_ids') or []
            except Exception as exc:
                trace = [{'agent': 'Coordinator', 'action': '协同失败，退回事实模板', 'detail': type(exc).__name__}]
        else:
            trace = [{'agent': '角色边界', 'action': '拒绝跨学生或班级数据', 'detail': '不执行多智能体读取'}]
    else:
        # 教师入口当前是班级规则流水线，不伪称多个独立大模型。
        trace = [{'agent': '班级统计模块', 'action': '本班事实聚合', 'detail': f"{ident}：题目、评分点、指标、证据覆盖"},
                 {'agent': '教师意图模块', 'action': '按问题与上文选择事实', 'detail': llm._rank_topic(question, history)},
                 {'agent': '证据边界模块', 'action': '检查统计范围', 'detail': '本班统计；明确提问两班时才比较'}]

    meta = {'trace': trace, 'evidence': evidence[:6], 'source': 'template', 'cached': False}
    practice = _practice_answer(question, ident, bundle) if role == 'student' and not denied else None
    if practice:
        meta['trace'].append({'agent': '分步练习模块', 'action': '维护当前题目与步骤', 'detail': '只使用项目题干和评分点，不自动判分、不写回BKT'})
        st.session_state[f'meta_{role}_{ident}'] = meta
        return practice
    try:
        if key or (llm.PROVIDER == 'ollama' and llm.available()):
            answer, model_meta = llm.answer_question(question, facts, key, cache_dir, role=role, history=history, return_meta=True)
            meta.update(model_meta)
        else:
            answer = llm.offline_answer(question, facts, history)
    except Exception as exc:
        answer = llm.offline_answer(question, facts, history)
        meta['fallback'] = type(exc).__name__
    st.session_state[f'meta_{role}_{ident}'] = meta
    return answer


def _validated_recommendations(items: list, valid_inds: set, qmap: dict) -> list:
    rows = []
    for item in items:
        ind = item.get('indicator')
        qids = item.get('recommended_questions') or []
        if ind not in valid_inds or not qids or any(q not in qmap or qmap[q].get('indicator') != ind for q in qids):
            continue
        # 旧成果里的通用错因话术可能与该题不匹配，主聊天改用真实评分点。
        definitions = qmap[qids[0]].get('scoring_point_definitions') or {}
        first = next(iter(definitions.values()), {})
        hints = [f"{qids[0]}：先检查“{first['description']}”这一步。"] if first.get('description') else []
        rows.append({**item, 'step_hints': hints})
    return rows


def _practice_answer(question: str, ident: str, bundle: dict) -> str | None:
    """基于真实评分点的分步辅导。用户新答案不冒充已有评分证据。"""
    state_key = f'practice_student_{ident}'
    active = st.session_state.get(state_key)
    if '结束练习' in question:
        st.session_state.pop(state_key, None)
        return '已结束这道练习。新输入的过程不会写入历史学情或更新掌握度。'
    starting = any(k in question for k in ('开始练习', '带我做', '出一道题'))
    follow = active and any(k in question for k in ('提示', '下一步', '我的答案', '我算出', '我的过程', '核对答案'))
    if not starting and not follow:
        return None
    own = bundle.get('records_by_student', {}).get(ident, [])
    if starting:
        qmatch = re.search(r'Q\d{3}', question)
        candidates = [r for r in own if r.get('question_text') and r.get('scoring_point_details')]
        if qmatch:
            candidates = [r for r in candidates if r.get('question_id') == qmatch.group()]
            if not candidates:
                item = (bundle.get('question_map') or {}).get(qmatch.group(), {})
                points = item.get('scoring_point_definitions') or {}
                if item.get('question_text') and points:
                    candidates = [{'question_id': qmatch.group(), 'question_text': item['question_text'],
                                   'scoring_point_details': list(points.values()),
                                   'reference_answer': item.get('reference_answer'), 'reference_solution': item.get('reference_solution')}]
        else:
            wrong = [r for r in candidates if not r.get('is_correct')]
            candidates = wrong or candidates
        if not candidates:
            return '当前范围没有带完整题干与评分点的这道题，不能编造题目。可以选你作答记录中带评分点的解答题。'
        active = {'record': candidates[0], 'step': 0, 'submissions': []}
        st.session_state[state_key] = active
        r = active['record']
        point = r['scoring_point_details'][0].get('description', '写出第一步思路')
        return f"一起重做 {r['question_id']}：{r['question_text']}\n\n先完成第一步：{point}。\n请用“我的过程：……”回复；需要帮助可以说“提示”或“下一步”。这是原题复练，不是新题或自动批改。"
    r = active['record']
    points = r['scoring_point_details']
    if any(k in question for k in ('我的答案', '我算出', '我的过程')):
        active['submissions'].append(question)
        point = points[active['step']].get('description', '')
        return f"收到你的作答。先对照当前评分点“{point}”检查这一步，并说明理由。\n我已保留本次过程，但没有自动判分；继续说“下一步”，或“核对答案”查看题库中的标准解法。"
    if '核对答案' in question:
        return f"{r['question_id']} 的题库参考答案：{r.get('reference_answer', '暂无')}。\n参考过程：{r.get('reference_solution', '暂无')}\n请对照自己的步骤复查。新答案尚未评分，不会据此更新掌握度。"
    if '下一步' in question:
        if active['step'] + 1 >= len(points):
            return '这道题的评分点已走完。可以说“核对答案”自查，或“结束练习”。完成辅导不等于已经答对。'
        active['step'] += 1
    point = points[active['step']].get('description', '')
    return f"{r['question_id']} · 当前任务：{point}。\n先写出这一步的表达式或推理依据，不必急着报最终答案。"


def _render_meta(meta: dict) -> None:
    if not meta:
        return
    label = '模型改写（缓存）' if meta.get('source') == 'model' and meta.get('cached') else '模型改写' if meta.get('source') == 'model' else '规则回答（未使用模型改写）'
    st.caption('本轮来源：' + label)
    AB.render_trace_cards(meta.get('trace', []), evidence=meta.get('evidence'),
                          title='本轮协同路径', expanded=False)
    if meta.get('fallback'):
        st.warning('表达层调用异常，已降级：' + meta['fallback'])


def render(bundle: dict, role: str, ident: str, key: str | None, cache_dir: str) -> None:
    hist = history(role, ident)
    n = sum(1 for r in bundle['records'] if r.get('class_id') == ident)
    st.info('能力边界：作答证据 → 学情诊断 → 练习/讲评建议 → 追问解释。模型负责表达改写；不支持任意新答案自动判分。')

    if not hist:
        if role == "student":
            v = A.student_view(bundle, ident)
            hist.append({"role": "assistant", "content": STUDENT_GREET.format(n=v["evidence_total"])})
            hist.append({"role": "assistant", "content":
                         f"先说结论：你 9 个指标里 **{v['coverage']['decided']} 个**有足够证据，"
                         f"{len(v['insufficient'])} 个还不够。想知道哪一个最拖后腿，点下面的问题就行。"})
        else:
            row = A.class_view(bundle, ident)["class_theme"].get(ident, {})
            hist.append({"role": "assistant",
                         "content": TEACHER_GREET.format(cls=ident, n=row.get("students", 0), m=n)})

    for m in hist:
        with st.chat_message(m["role"], avatar="🧑‍🎓" if m["role"] == "user" else theme.character_path()):
            st.markdown(labels.humanize(m["content"], bundle.get("output_dir"))
                        if m["role"] != "user" else m["content"])
            if m.get('meta'):
                _render_meta(m['meta'])

    chips = STUDENT_CHIPS if role == "student" else TEACHER_CHIPS
    st.caption("试试这样问：")
    picked = None
    for i, txt in enumerate(chips):
        if i % 2 == 0:
            cols = st.columns(2)
        c = cols[i % 2]
        if c.button(txt, key=f"chip_{role}_{ident}_{i}", width="stretch"):
            picked = txt

    typed = st.chat_input("问我任何关于" + ("你" if role == "student" else "这个班") + "学习情况的问题…")
    question = picked or typed
    if not question:
        return

    hist.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(question)

    placeholder = st.empty()
    with placeholder.container():
        with st.chat_message("assistant", avatar=theme.character_path()):
            st.markdown(theme.typing(), unsafe_allow_html=True)
    answer = labels.humanize(
        _answer(question, role, ident, bundle, key, cache_dir, history=hist[:-1][-4:]),
        bundle.get("output_dir"))
    placeholder.empty()
    meta = st.session_state.get(f'meta_{role}_{ident}', {})
    hist.append({'role': 'assistant', 'content': answer, 'meta': meta})
    with st.chat_message('assistant', avatar=theme.character_path()):
        st.markdown(answer)
        _render_meta(meta)
