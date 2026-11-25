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

STUDENT_GREET = "已汇总 **{n} 条**有效作答。可以按题目、错因或学习主题查询。"
TEACHER_GREET = "**{cls} 班**共有 **{n} 名学生、{m} 条作答记录**。可以查询班级表现和讲评建议。"


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

    provider = {"本地模型": "ollama", "云端 API": "api"}.get(
        st.session_state.get("provider_choice"), llm.PROVIDER,
    )
    meta = {'trace': trace, 'evidence': evidence[:6], 'source': 'template',
            'cached': False, 'provider': provider}
    practice = _practice_answer(question, ident, bundle) if role == 'student' and not denied else None
    if practice:
        meta['reason'] = 'practice'
        meta['trace'].append({'agent': '分步练习模块', 'action': '维护当前题目与步骤', 'detail': '只使用项目题干和评分点，不自动判分、不写回BKT'})
        if provider == 'ollama':
            if key or llm.pick_model():
                practice, guidance_meta = llm.guide_local_practice(question, practice)
                meta.update(guidance_meta)
            else:
                meta['reason'] = 'unavailable'
        st.session_state[f'meta_{role}_{ident}'] = meta
        return practice
    try:
        if key or (provider == 'ollama' and llm.pick_model()):
            answer, model_meta = llm.answer_question(
                question, facts, key, cache_dir, role=role, history=history,
                return_meta=True, provider=provider,
            )
            meta.update(model_meta)
        else:
            answer = llm.offline_answer(question, facts, history)
            meta['reason'] = 'unavailable'
    except Exception:
        answer = llm.offline_answer(question, facts, history)
        meta['reason'] = 'call_failed'
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


def _render_meta(meta: dict, role: str = "student") -> None:
    """展示本轮来源、协同路径与读取的作答记录（学生、教师都保留，便于复核）。"""
    if not meta:
        return
    backend = {"api": "云端模型", "ollama": "本地模型"}.get(meta.get("provider"), "模型")
    if meta.get("source") == "model":
        if meta.get("mode") == "practice_guidance":
            label = f"{backend}选择练习呈现方式 · 题库评分步骤"
        else:
            label = f"{backend}改写" + ("（缓存）" if meta.get("cached") else "")
    else:
        reason = {
            "structured_question": "此类问题直接按证据回答",
            "practice": "分步练习按题库评分步骤回答",
            "unavailable": f"{backend}尚未就绪",
            "call_failed": f"{backend}调用失败",
            "unusable_output": f"{backend}返回内容不可用",
            "fact_check": f"{backend}的改写未通过事实校验",
            "unchanged": f"{backend}返回内容与原稿相同",
        }.get(meta.get("reason"), "未使用模型改写")
        label = f"规则回答（{reason}）"
    st.caption('本轮来源：' + label)
    AB.render_trace_cards(meta.get('trace', []), evidence=meta.get('evidence'),
                          title='本轮协同路径', expanded=True)
    if meta.get('fallback'):
        st.warning('表达层调用异常，已降级：' + meta['fallback'])


def render(bundle: dict, role: str, ident: str, key: str | None, cache_dir: str) -> None:
    hist = history(role, ident)
    n = sum(1 for r in bundle['records'] if r.get('class_id') == ident)
    st.info('可以查询已评分的作答记录、练习建议和讲评建议。')

    # 教师端：可以把问题限定到某个学生（吸收原「智能体」页的选学生能力）
    scope = "全班"
    if role == "teacher":
        students = A.list_students(bundle)
        scope = st.selectbox("提问对象", ["全班"] + students, key=f"chat_scope_{ident}",
                             help="选某个学生时，回答只针对该生的作答记录")
        if scope != "全班":
            st.caption(f"当前只回答 {scope} 的个人学情；改回「全班」可问班级讲评。")

    if not hist:
        if role == "student":
            v = A.student_view(bundle, ident)
            hist.append({"role": "assistant", "content": STUDENT_GREET.format(n=v["evidence_total"])})
            hist.append({"role": "assistant", "content":
                         f"9 个指标中，**{v['coverage']['decided']} 个**已有足够作答记录，"
                         f"{len(v['insufficient'])} 个暂无法判定。"})
        else:
            row = A.class_view(bundle, ident)["class_theme"].get(ident, {})
            hist.append({"role": "assistant",
                         "content": TEACHER_GREET.format(cls=ident, n=row.get("students", 0), m=n)})

    for m in hist:
        with st.chat_message(m["role"], avatar="🧑‍🎓" if m["role"] == "user" else theme.character_path()):
            if m.get("content"):
                st.markdown(labels.humanize(m["content"], bundle.get("output_dir"))
                            if m["role"] != "user" else m["content"])
            if m.get("agent"):
                for r in (m["agent"].get("results") or []):
                    AB.render_result(r)
                AB.render_trace(m["agent"], expanded=False)
            if m.get('meta'):
                _render_meta(m['meta'], role)

    chips = STUDENT_CHIPS if role == "student" else TEACHER_CHIPS
    st.caption("常用问题")
    picked = None
    for i, txt in enumerate(chips):
        if i % 2 == 0:
            cols = st.columns(2)
        c = cols[i % 2]
        if c.button(txt, key=f"chip_{role}_{ident}_{i}", width="stretch"):
            picked = txt

    typed = st.chat_input("输入个人学情问题" if role == "student" else "输入班级学情问题")
    question = picked or typed
    if not question:
        return

    hist.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(question)

    # 教师端指定了学生：走多智能体（诊断 / 建议 / 证据），结果直接渲染在气泡里
    if role == "teacher" and scope != "全班":
        with st.spinner(f"正在读取 {scope} 的作答记录…"):
            result = AB.ask(f"{scope} {question}", bundle.get("output_dir"))
        with st.chat_message('assistant', avatar=theme.character_path()):
            if result.get("error"):
                st.error(f"智能体执行出错：{result['error']}")
            else:
                for r in (result.get("results") or []):
                    AB.render_result(r)
                AB.render_trace(result, expanded=False)
        hist.append({'role': 'assistant', 'content': f'已按 {scope} 的作答记录回答。',
                     'agent': result})
        return

    # 用 st.spinner 代替 st.empty()+st.chat_message 的“打字动画”：
    # 后者会触发 Streamlit 前端的 removeChild 报错（占位符里嵌 chat_message + 自定义 HTML）。
    with st.spinner("正在生成回答…"):
        answer = labels.humanize(
            _answer(question, role, ident, bundle, key, cache_dir, history=hist[:-1][-4:]),
            bundle.get("output_dir"))
    meta = st.session_state.get(f'meta_{role}_{ident}', {})
    hist.append({'role': 'assistant', 'content': answer, 'meta': meta})
    with st.chat_message('assistant', avatar=theme.character_path()):
        st.markdown(answer)
        _render_meta(meta, role)
