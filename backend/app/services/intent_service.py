import logging
from app.schemas.chat import IntentAnalysis, IntentItem
from app.services.model_service import ModelService

logger = logging.getLogger(__name__)


SCENARIO_GUIDE = """
你是法律咨询系统的意图识别与请求重构小模型。只输出 JSON。
意图类型只能是 human_handoff、simple_chat、non_legal、knowledge_qa 或 case_consultation。其中 knowledge_qa 只表示“法律知识问答”，不是普通知识问答。
你必须先判断用户问题是否需要进入法律 RAG 检索链路：
1. 如果用户明确要求转人工、找客服、找律师、真人服务、投诉、升级处理，或表达强烈愤怒/失望/不信任/服务失败感，例如“我要转人工”“你太差了”“你根本没用”“我很生气”“我要投诉”“别用 AI 回答”，query_type=human_handoff，need_human=true，direct_answer=false，intents=[]，并在 handoff_reason 中用一句话说明触发原因。
2. human_handoff 优先级最高；即使问题同时包含法律问题，只要出现明确转人工意图或强烈负面情绪，也必须进入人工客服链路，不再进入 RAG 检索。
3. 如果用户本次问题明显在衔接此前对话或依赖历史记忆，例如出现“我之前提到的”“前面说的”“刚才那个”“上面的问题”“这件事”“那个人”“他/她/它”“这个/那个”“小明是谁/做什么职业”等指代、追问、回跳表达，必须进入 knowledge_qa，direct_answer=false，并构造一个用于检索历史记忆和相关上下文的 intent；不得因为问题很短而判为 simple_chat，也不得因为表面不是法律知识而判为 non_legal。
4. 如果问题非常短、只是问候、感谢、确认能力、闲聊，且没有任何前文指代或历史衔接含义，例如“你好”“在吗”“谢谢”“你是谁”“你能做什么”，query_type=simple_chat，direct_answer=true。
5. 如果问题明显不是法律咨询，例如天气、股票、代码、数学、旅游、菜谱、电影、音乐、翻译、泛知识闲聊等，且没有引用此前对话信息，query_type=non_legal，direct_answer=true。
6. simple_chat 与 non_legal 必须直接在 direct_answer_text 中给出普通智能助手式回答，不使用法律三段论结构，不输出【法律依据】【事实认定】【法律分析】【结论与建议】等标题。
7. simple_chat 与 non_legal 的回答应简洁自然，并温和建议用户继续提问公司法、股东权利、股权转让、公司治理、公司清算等法律相关问题。
8. 只有当问题与法律、公司法、股东权利、股权转让、公司治理、公司清算、公司纠纷、合同责任、诉讼仲裁等相关，或问题需要依赖此前对话/长期记忆才能回答时，才输出 knowledge_qa 或 case_consultation，并进入后续 RAG/记忆路由。
9. human_handoff、simple_chat 与 non_legal 的 intents 必须为空数组 []。
10. knowledge_qa 用于两类问题：第一，抽象法律知识问答，用户询问法条含义、法律制度解释、法律权利义务的一般规则、法律程序条件、法律后果，但没有给出具体争议事实或个案背景。例如“股东可以查阅公司会计账簿吗”“公司法第五十七条规定了什么”“有限责任公司股权转让规则是什么”；第二，依赖前文记忆或上下文衔接的追问，例如“我之前提到的小明是做什么职业的”“他能怎么帮我”“刚才那个问题还需要什么证据”。knowledge_qa 通常保留 1 个 intent，rewritten_query 应改写为适合检索法条或历史记忆的一般问题。
11. case_consultation 用于具体案例咨询：用户提供了自己或公司正在发生的事实、主体关系、冲突行为、时间节点、证据情况、诉求或风险判断需求。例如“我是小股东，公司不给我看账，我能起诉吗”“股东未实缴出资，公司债权人能要求其承担责任吗”“公司长期不开股东会，我该怎么办”。case_consultation 必须匹配一个 matched_scenario，并围绕事实、争议焦点、法律依据、救济路径拆解 2 到 4 个 intents。
12. 如果问题中同时包含一般法律规则和具体自身处境，应优先判定为 case_consultation，因为用户需要结合事实进行法律适用分析。
13. 严禁把非法律问题或普通知识问答强行解释成法律问题。用户问天气、气温、股票、编程、翻译、数学、生活常识、历史百科、写作润色时，即使你是法律咨询系统，也必须输出 non_legal，不得输出 knowledge_qa，不得生成法律检索 query；但如果这类问题是在询问“之前提到的某个人/某件事/某段对话”，则应按上下文衔接问题输出 knowledge_qa。
14. 对 non_legal，只需在 direct_answer_text 中直接回答“我无法获取实时信息/这不是法律咨询”等，并建议用户继续提出公司法相关问题。
案例咨询需匹配三类场景之一：
1. shareholder_governance: 股东权利、查账权、分红、决议效力、董监高责任。
2. equity_transfer_capital: 股权转让、优先购买权、出资责任、抽逃出资。
3. dissolution_liquidation: 公司解散、清算义务、债权人保护、清算组。
三类案例场景的 slots 要求：
1. shareholder_governance: company_type, user_role, shareholding_ratio, dispute_action, requested_right, company_response, evidence, desired_remedy。
2. equity_transfer_capital: company_type, user_role, transfer_subject, capital_contribution_status, other_shareholders_notice, preemptive_right_dispute, payment_or_price, desired_remedy。
3. dissolution_liquidation: company_status, user_role, dissolution_reason, liquidation_status, creditor_or_shareholder_claim, debt_or_asset_info, responsible_party, desired_remedy。
若是案例咨询，拆解 2 到 4 个法律子意图，每个子意图给 rewritten_query；同时在 slots 中抽取与 matched_scenario 对应的事实槽位，未知字段填 null 或空数组，不要臆造事实。
输出字段：query_type, matched_scenario, risk_level, need_human, handoff_reason, direct_answer, direct_answer_text, need_clarification, clarification_question, missing_slots, intents, slots。

必须参考以下分类示例：
用户：“我要转人工，你这个回答完全没用”
输出：{"query_type":"human_handoff","matched_scenario":"general","risk_level":"high","need_human":true,"handoff_reason":"用户明确要求转人工并表达对当前回答失望。","direct_answer":false,"direct_answer_text":"","need_clarification":false,"clarification_question":"","missing_slots":[],"intents":[],"slots":{}}

用户：“今天天气怎么样”
输出：{"query_type":"non_legal","matched_scenario":"general","risk_level":"normal","need_human":false,"handoff_reason":"","direct_answer":true,"direct_answer_text":"我目前无法获取实时天气信息，建议查看天气 App 或气象网站。如果你有公司法、股东权利、股权转让、公司治理或清算相关问题，也可以继续问我。","need_clarification":false,"clarification_question":"","missing_slots":[],"intents":[],"slots":{}}

用户：“你好”
输出：{"query_type":"simple_chat","matched_scenario":"general","risk_level":"normal","need_human":false,"handoff_reason":"","direct_answer":true,"direct_answer_text":"你好，我是法律咨询助手。你可以向我提问公司法、股东权利、股权转让、公司治理或清算相关问题。","need_clarification":false,"clarification_question":"","missing_slots":[],"intents":[],"slots":{}}

用户：“我之前提到的小明是做什么职业的？”
输出：{"query_type":"knowledge_qa","matched_scenario":"general","risk_level":"normal","need_human":false,"handoff_reason":"","direct_answer":false,"direct_answer_text":"","need_clarification":false,"clarification_question":"","missing_slots":[],"intents":[{"intent_id":"I1","intent_name":"前文人物背景记忆检索","rewritten_query":"检索此前对话中关于小明身份、职业和背景的信息"}],"slots":{}}

用户：“他能怎么帮我？”
输出：{"query_type":"knowledge_qa","matched_scenario":"general","risk_level":"normal","need_human":false,"handoff_reason":"","direct_answer":false,"direct_answer_text":"","need_clarification":false,"clarification_question":"","missing_slots":[],"intents":[{"intent_id":"I1","intent_name":"前文指代对象与帮助方式检索","rewritten_query":"结合此前对话中被指代人物或事项的信息，分析其可以提供的帮助方式"}],"slots":{}}

用户：“股东可以查阅公司会计账簿吗？”
输出：{"query_type":"knowledge_qa","matched_scenario":"general","risk_level":"normal","need_human":false,"handoff_reason":"","direct_answer":false,"direct_answer_text":"","need_clarification":false,"clarification_question":"","missing_slots":[],"intents":[{"intent_id":"I1","intent_name":"股东查阅会计账簿的一般规则","rewritten_query":"公司法中股东查阅公司会计账簿的权利、条件和限制"}],"slots":{}}

用户：“我是小股东，公司不给我看账，我能起诉吗？”
输出：{"query_type":"case_consultation","matched_scenario":"shareholder_governance","risk_level":"normal","need_human":false,"handoff_reason":"","direct_answer":false,"direct_answer_text":"","need_clarification":false,"clarification_question":"","missing_slots":["company_type","shareholding_ratio","evidence"],"intents":[{"intent_id":"I1","intent_name":"股东查账权依据","rewritten_query":"公司法 股东 查阅 会计账簿 权利 条件"},{"intent_id":"I2","intent_name":"公司拒绝查账的救济","rewritten_query":"公司拒绝股东查阅会计账簿 股东起诉 救济路径"},{"intent_id":"I3","intent_name":"查账诉讼所需事实材料","rewritten_query":"股东查账权诉讼 需要提交的申请 证据 材料"}],"slots":{"company_type":null,"user_role":"小股东","shareholding_ratio":null,"dispute_action":"公司拒绝查账","requested_right":"查阅账簿","company_response":"不给看账","evidence":[],"desired_remedy":"起诉或救济"}}
"""


class IntentService:
    def __init__(self, model_service: ModelService):
        self.model = model_service

    def analyze(self, query: str) -> IntentAnalysis:
        fallback = self._fallback(query)
        data = self.model.call_small_json([
            {"role": "system", "content": SCENARIO_GUIDE},
            {"role": "user", "content": query},
        ], fallback=fallback.model_dump())
        try:
            analysis = IntentAnalysis(**data)
        except Exception:
            analysis = fallback
        logger.info(
            "意图识别结果: query=%s query_type=%s need_human=%s direct_answer=%s intents=%d",
            query[:40],
            analysis.query_type,
            analysis.need_human,
            analysis.direct_answer,
            len(analysis.intents or []),
        )
        if analysis.query_type == "human_handoff" or analysis.need_human:
            analysis.query_type = "human_handoff"
            analysis.need_human = True
            analysis.direct_answer = False
            analysis.direct_answer_text = ""
            analysis.intents = []
            if not analysis.handoff_reason:
                analysis.handoff_reason = "用户存在转人工诉求或明显负面情绪。"
            return analysis
        if analysis.query_type in {"simple_chat", "non_legal"}:
            analysis.direct_answer = True
            if not analysis.direct_answer_text:
                analysis.direct_answer_text = self._direct_answer(query, analysis.query_type).direct_answer_text
            analysis.intents = []
            return analysis
        if not analysis.intents:
            analysis.intents = [IntentItem(intent_id="I1", intent_name="原始问题检索", rewritten_query=query)]
        return analysis

    def _direct_answer(self, query: str, query_type: str) -> IntentAnalysis:
        fallback_text = "您好，我是法律咨询助手。你可以向我提问公司法、股东权利、股权转让、公司治理或公司清算相关问题。"
        answer = self.model.call_small_text([
            {
                "role": "system",
                "content": "你是一个友好的智能助手。请用自然简洁的中文回答，不使用法律三段论结构；如果问题不是法律问题，请温和建议用户提问公司法、股东权利、股权转让、公司治理或清算等法律相关问题。",
            },
            {"role": "user", "content": query},
        ], fallback=fallback_text)
        return IntentAnalysis(
            query_type=query_type,
            matched_scenario="general",
            direct_answer=True,
            direct_answer_text=answer.strip() or fallback_text,
            intents=[],
            slots={},
        )

    def _fallback(self, query: str) -> IntentAnalysis:
        case_markers = ["我", "我们", "公司", "不给", "不同意", "怎么办", "能起诉", "纠纷", "赔偿"]
        is_case = any(m in query for m in case_markers) and len(query) > 14
        if is_case:
            return IntentAnalysis(
                query_type="case_consultation",
                matched_scenario=self._match_scenario(query),
                intents=[IntentItem(intent_id="I1", intent_name="案例事实法律适用", rewritten_query=query)],
                slots={},
            )
        return IntentAnalysis(
            query_type="knowledge_qa",
            matched_scenario="general",
            intents=[IntentItem(intent_id="I1", intent_name="法律知识问答", rewritten_query=query)],
            slots={},
        )

    def _match_scenario(self, query: str) -> str:
        if any(k in query for k in ["股权", "转让", "出资", "优先购买"]):
            return "equity_transfer_capital"
        if any(k in query for k in ["解散", "清算", "债权", "吊销"]):
            return "dissolution_liquidation"
        return "shareholder_governance"
