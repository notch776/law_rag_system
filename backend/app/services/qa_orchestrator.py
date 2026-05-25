import json
import logging
from time import perf_counter
from typing import AsyncGenerator, List
from app.core.config import settings
from app.repositories.mongo_repo import MongoRepository
from app.schemas.chat import CaseSlotState, ChatRequest, ChatResponse, Citation, IntentAnalysis, IntentItem
from app.services.conversation_service import ConversationService
from app.services.guardrail_service import GuardrailService
from app.services.intent_service import IntentService
from app.services.memory_service import MemoryService
from app.services.model_service import ModelService
from app.services.retrieval_service import RetrievalService

DISCLAIMER = "\n\n【特别声明】本回答由人工智能系统生成，仅供法律信息参考，不构成正式法律意见。具体案件请咨询具备执业资格的专业律师。"
logger = logging.getLogger(__name__)


class QAOrchestrator:
    def __init__(self, mongo: MongoRepository, conversation: ConversationService, model: ModelService, intent: IntentService, retrieval: RetrievalService, memory: MemoryService, guardrail: GuardrailService):
        self.mongo = mongo
        self.conversation = conversation
        self.model = model
        self.intent = intent
        self.retrieval = retrieval
        self.memory = memory
        self.guardrail = guardrail

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        trace_start = perf_counter()
        last_stage = trace_start
        trace_id = f"{request.conversation_id}:{int(trace_start * 1000)}"

        def mark(stage: str, **extra):
            nonlocal last_stage
            now = perf_counter()
            delta_ms = (now - last_stage) * 1000
            total_ms = (now - trace_start) * 1000
            last_stage = now
            details = " ".join(f"{key}={value}" for key, value in extra.items())
            logger.info("QA_TIMING trace=%s stage=%s delta_ms=%.1f total_ms=%.1f %s", trace_id, stage, delta_ms, total_ms, details)

        logger.info(
            "QA_TIMING trace=%s stage=request_received conversation_id=%s mode=%s query_len=%d",
            trace_id,
            request.conversation_id,
            request.mode,
            len(request.query),
        )
        qa_id = await self.mongo.next_qa_id(request.conversation_id)
        await self.conversation.append_user(request.conversation_id, qa_id, request.query, request.mode)
        mark("persist_user_message", qa_id=qa_id)
        yield self._event("meta", {"conversation_id": request.conversation_id, "qa_id": qa_id, "mode": request.mode})

        conversation_doc = await self.mongo.get_conversation(request.conversation_id)
        if (conversation_doc or {}).get("status") == "support":
            mark("support_mode_short_circuit")
            support_payload = {
                "conversation_id": request.conversation_id,
                "qa_id": qa_id,
                "status": "waiting",
                "reason": "当前会话已处于人工客服模式。",
                "user_ws": f"/ws/user/{request.conversation_id}",
                "support_ws": f"/ws/support/{request.conversation_id}/support-demo",
            }
            yield self._event("handoff", support_payload)
            answer = "当前会话已转入人工客服模式，请通过实时客服通道继续沟通。"
            for token in self._chunk(answer):
                yield self._event("token", {"content": token})
            mark("request_done", status="support_mode")
            yield self._event("done", {**support_payload, "status": "need_human"})
            return

        rejected, reason = self.guardrail.reject_reason(request.query)
        mark("guardrail_check", rejected=rejected)
        if rejected:
            answer = reason + DISCLAIMER
            for token in self._chunk(answer):
                yield self._event("token", {"content": token})
            await self.conversation.append_assistant(request.conversation_id, qa_id, answer, request.mode, [])
            mark("persist_assistant_message", answer_chars=len(answer))
            mark("request_done", status="rejected")
            yield self._event("done", {"status": "ok"})
            return

        normal_mode = request.mode == "normal"
        case_slot_state = await self.mongo.get_case_slot_state(request.conversation_id)
        if normal_mode:
            analysis = IntentAnalysis(
                query_type="knowledge_qa",
                matched_scenario="general",
                intents=[IntentItem(intent_id="I1", intent_name="默认法律知识问答", rewritten_query=request.query)],
                slots={},
                case_slot_state=case_slot_state,
            )
            mark("normal_default_route", query_type=analysis.query_type, intents=len(analysis.intents))
        else:
            yield self._progress("intent", "意图识别中")
            analysis = self.intent.analyze(request.query, case_slot_state=case_slot_state)
            case_slot_state = await self.mongo.update_case_slot_state(request.conversation_id, analysis.case_slot_state.model_dump())
            analysis.case_slot_state = CaseSlotState(**case_slot_state)
            mark("intent_analysis", query_type=analysis.query_type, intents=len(analysis.intents))
        yield self._event("intent", analysis.model_dump())
        if not normal_mode and (analysis.need_human or analysis.query_type == "human_handoff"):
            mark("human_handoff_check", need_human=True, reason=analysis.handoff_reason or "model_route")
            answer = "已为您进入人工客服通道。请继续在当前输入框描述问题，在线客服接入后会通过实时对话回复您。"
            await self.conversation.mark_support(request.conversation_id)
            mark("mark_support_status")
            support_payload = {
                "conversation_id": request.conversation_id,
                "qa_id": qa_id,
                "status": "waiting",
                "reason": analysis.handoff_reason,
                "user_ws": f"/ws/user/{request.conversation_id}",
                "support_ws": f"/ws/support/{request.conversation_id}/support-demo",
            }
            yield self._event("handoff", support_payload)
            for token in self._chunk(answer):
                yield self._event("token", {"content": token})
            await self.conversation.append_assistant(request.conversation_id, qa_id, answer, request.mode, [])
            mark("persist_assistant_message", answer_chars=len(answer))
            mark("request_done", status="need_human")
            yield self._event("done", {**support_payload, "status": "need_human"})
            return
        mark("human_handoff_check", need_human=False)
        if not normal_mode and analysis.direct_answer:
            answer = analysis.direct_answer_text.strip() or "您好，我是法律咨询助手。你可以向我提问公司法、股东权利、股权转让、公司治理或清算相关问题。"
            mark("direct_small_model_answer", answer_chars=len(answer), query_type=analysis.query_type)
            for token in self._chunk(answer):
                yield self._event("token", {"content": token})
            await self.conversation.append_assistant(request.conversation_id, qa_id, answer, request.mode, [])
            mark("persist_assistant_message", answer_chars=len(answer))
            self.memory.write_short(request.conversation_id, qa_id, request.query, answer, [])
            mark("write_short_memory")
            if analysis.query_type == "simple_chat":
                direct_query_vector = self.model.embed_text(request.query)
                mark("simple_chat_embedding", has_vector=bool(direct_query_vector))
                self.memory.write_long(
                    request.conversation_id,
                    qa_id,
                    request.query,
                    answer,
                    [],
                    direct_query_vector,
                    original_vector=direct_query_vector,
                    intent_vectors=[],
                    intent_queries=[],
                    intent_names=[],
                    scenario=analysis.matched_scenario,
                )
                mark("write_long_memory", reason="simple_chat_direct_answer")
            mark("request_done", status="direct_answer")
            yield self._event("done", {"status": "ok"})
            return

        yield self._progress("retrieval", "检索相关条款中")
        if normal_mode:
            retrieval_result = self.retrieval.retrieve_for_query(request.query, top_n=3)
        else:
            plus_top_n = 3 if analysis.query_type == "knowledge_qa" else settings.docs_per_intent
            retrieval_result = self.retrieval.retrieve_for_analysis(analysis, top_n=plus_top_n)
        citations = retrieval_result.citations
        mark("retrieval_and_rerank", citations=len(citations))
        yield self._event("citations", {"citations": [c.model_dump() for c in citations]})
        query_vector = retrieval_result.query_vector
        if query_vector:
            mark("query_embedding_reuse", has_vector=True)
        else:
            query_vector = self.model.embed_text(request.query)
            mark("query_embedding_fallback", has_vector=bool(query_vector))
        yield self._progress("memory", "记忆提取与注入中")
        memory_vector = query_vector
        original_query_vector = None
        if not normal_mode:
            original_query_vector = self.model.embed_text(request.query)
            memory_vector = self.memory.build_memory_vector(original_query_vector, retrieval_result.intent_vectors)
            mark(
                "long_memory_vector_blend",
                has_original=bool(original_query_vector),
                intent_vectors=len(retrieval_result.intent_vectors),
                has_memory_vector=bool(memory_vector),
            )
        if normal_mode:
            memory_context = await self.memory.build_short_context(request.conversation_id, limit=3)
        else:
            memory_context = await self.memory.build_context(
                request.conversation_id,
                memory_vector,
                long_limit=2,
                long_answer_chars=200,
                include_long_docs=False,
            )
        mark("memory_context", chars=len(memory_context or ""))
        follow_up = self._is_follow_up(request.query, memory_context)
        messages = self._build_generation_messages(request.query, analysis.model_dump(), citations, memory_context, request.mode, follow_up=follow_up)
        mark("prompt_build", prompt_chars=sum(len(message.get("content", "")) for message in messages))
        generation_model = settings.small_llm_model if normal_mode else None
        generation_max_tokens = 900 if normal_mode else 1200
        mark("generation_config", model=generation_model or "default_plus_model", max_tokens=generation_max_tokens, follow_up=follow_up)
        yield self._progress("generation", "生成回答中")
        answer_parts: List[str] = []
        if not normal_mode:
            draft_messages = self._build_draft_messages(request.query, analysis.model_dump(), citations, memory_context, follow_up=follow_up)
            draft_start = perf_counter()
            draft_first_token = False
            yield self._progress("draft_generation", "生成简短初答中")
            for token in self.model.stream_main(draft_messages, model=settings.small_llm_model, max_tokens=350, temperature=0.2):
                if not draft_first_token:
                    draft_first_token = True
                    mark("draft_first_token", first_token_ms=f"{(perf_counter() - draft_start) * 1000:.1f}")
                answer_parts.append(token)
                yield self._event("token", {"content": token})
            mark("draft_generation_complete", answer_chars=sum(len(part) for part in answer_parts))
            separator = "\n\n---\n\n【补充严谨分析】\n"
            answer_parts.append(separator)
            yield self._event("token", {"content": separator})
            yield self._progress("generation", "答案生成中")
        generation_start = perf_counter()
        first_token_sent = False
        for token in self.model.stream_main(messages, model=generation_model, max_tokens=generation_max_tokens):
            if not first_token_sent:
                first_token_sent = True
                mark("first_token", first_token_ms=f"{(perf_counter() - generation_start) * 1000:.1f}")
            answer_parts.append(token)
            yield self._event("token", {"content": token})
        mark("generation_complete", answer_chars=sum(len(part) for part in answer_parts))
        answer = "".join(answer_parts).strip()
        if "【特别声明】" not in answer:
            answer += DISCLAIMER
            yield self._event("token", {"content": DISCLAIMER})
            mark("append_disclaimer")
        await self.conversation.append_assistant(request.conversation_id, qa_id, answer, request.mode, citations)
        mark("persist_assistant_message", answer_chars=len(answer))
        self.memory.write_short(request.conversation_id, qa_id, request.query, answer, citations)
        mark("write_short_memory")
        fallback_intent_queries = [intent.rewritten_query for intent in analysis.intents if intent.rewritten_query]
        fallback_intent_names = [intent.intent_name for intent in analysis.intents if intent.intent_name]
        self.memory.write_long(
            request.conversation_id,
            qa_id,
            request.query,
            answer,
            citations,
            memory_vector,
            original_vector=original_query_vector or query_vector,
            intent_vectors=retrieval_result.intent_vectors,
            intent_queries=retrieval_result.intent_queries or fallback_intent_queries,
            intent_names=retrieval_result.intent_names or fallback_intent_names,
            scenario=analysis.matched_scenario,
        )
        mark("write_long_memory", mode=request.mode)
        await self.memory.maybe_mid_summary(request.conversation_id)
        mark("maybe_mid_summary", mode=request.mode)
        mark("request_done", status="ok")
        yield self._event("done", {"status": "ok"})

    async def non_stream_chat(self, request: ChatRequest) -> ChatResponse:
        answer = []
        citations = []
        qa_id = ""
        async for event in self.stream_chat(request):
            if event.startswith("event: meta"):
                data = json.loads(event.split("data: ", 1)[1])
                qa_id = data["qa_id"]
            elif event.startswith("event: token"):
                data = json.loads(event.split("data: ", 1)[1])
                answer.append(data.get("content", ""))
            elif event.startswith("event: citations"):
                data = json.loads(event.split("data: ", 1)[1])
                citations = [Citation(**c) for c in data.get("citations", [])]
        return ChatResponse(conversation_id=request.conversation_id, qa_id=qa_id, answer="".join(answer), mode=request.mode, citations=citations)

    def _build_generation_messages(self, query, analysis, citations, memory_context, mode="plus", follow_up=False):
        context = "\n\n".join([f"[{c.citation_id}]《{c.law_name}》{c.article_id} 来源:{c.filename}\n{c.content}" for c in citations]) or "未检索到可靠法律条文。"
        prompt_analysis = self._trim_prompt_analysis(analysis)
        if mode == "normal":
            system = """你是企业公司法咨询助手。请严格基于检索资料回答，不得伪造法条。
Normal 模式要求回答简洁，结构只使用：
【依据】、【简要结论】、【操作建议】。
不要使用【事实认定】【法律分析】【参考来源】等完整五段式结构。若资料不足，直接说明需要补充的关键信息。"""
            user = f"""【用户问题】
{query}

【短期记忆】
{memory_context or '无'}

【检索到的法律依据】
{context}
"""
            return [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if follow_up:
            system = """你是企业公司法咨询助手。必须严格基于检索资料和会话记忆回答，不得伪造法条。
事实优先级规则：当前【意图识别与槽位】中的 case_slot_state/slots 是用户最新确认或手动修正的案件事实，优先级高于【会话记忆】。如果槽位与记忆冲突，必须以槽位为准；例如记忆中持股比例为 12%，但当前槽位为 15%，回答必须按 15% 分析，不得沿用旧记忆。
当前问题是追问或多轮承接问题：如果上一轮已经做过完整结构化分析，本轮不要机械重复五段式；请直接、自然地回答用户当前追问。
回答应优先解决当前问题，必要时用简短小标题组织；若出现新的法律争点或重要事实，再补充法律依据和建议。"""
        else:
            system = """你是企业公司法咨询助手。必须严格基于检索资料和会话记忆回答，不得伪造法条。
事实优先级规则：当前【意图识别与槽位】中的 case_slot_state/slots 是用户最新确认或手动修正的案件事实，优先级高于【会话记忆】。如果槽位与记忆冲突，必须以槽位为准；例如记忆中持股比例为 12%，但当前槽位为 15%，回答必须按 15% 分析，不得沿用旧记忆。
首次或复杂问题时回答采用：
【法律依据】、【事实认定】、【法律分析】、【结论与建议】、【参考来源】。
避免绝对化承诺；如果事实不足，先指出缺失事实并给出需要补充的问题。"""
        user = f"""【用户问题】
{query}

【意图识别与槽位】
{json.dumps(prompt_analysis, ensure_ascii=False)}

【会话记忆】
{memory_context or '无'}

【检索到的法律依据】
{context}
"""
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _build_draft_messages(self, query, analysis, citations, memory_context, follow_up=False):
        context = "\n".join([f"[{c.citation_id}]《{c.law_name}》{c.article_id}: {c.content[:180]}" for c in citations[:3]]) or "未检索到可靠法律条文。"
        prompt_analysis = self._trim_prompt_analysis(analysis)
        instruction = "这是追问问题，请结合会话记忆直接回答当前问题。" if follow_up else "请先给出一个可读的简短初答。"
        system = """你是企业公司法咨询助手。请用 qwen3.6-flash 快速生成简短初答，降低用户等待。
事实优先级规则：当前【意图识别与槽位】中的 case_slot_state/slots 是用户最新确认或手动修正的案件事实，优先级高于【压缩记忆】。如果槽位与记忆冲突，必须以槽位为准；例如记忆中持股比例为 12%，但当前槽位为 15%，初答必须按 15% 给出判断。
要求：只给核心判断、关键依据和下一步建议；不要展开长篇论证；不得伪造法条；控制在 200-350 字。"""
        user = f"""【任务】
{instruction}

【用户问题】
{query}

【意图识别与槽位】
{json.dumps(prompt_analysis, ensure_ascii=False)}

【压缩记忆】
{memory_context or '无'}

【主要依据】
{context}
"""
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _is_follow_up(self, query: str, memory_context: str) -> bool:
        markers = [
            "之前", "前面", "刚才", "上面", "上一", "继续", "还有", "那", "这个", "那个",
            "这件事", "这类", "这种", "他", "她", "它", "小明", "补充", "再说", "进一步",
        ]
        return bool(memory_context) and any(marker in query for marker in markers)

    def _trim_prompt_analysis(self, analysis):
        prompt_analysis = dict(analysis or {})
        case_slot_state = (prompt_analysis.get("case_slot_state") or {}).copy()
        if not case_slot_state:
            return prompt_analysis
        trimmed_slot_state = {"active_scenario": case_slot_state.get("active_scenario", "general")}
        for scenario in ["shareholder_governance", "equity_transfer_capital", "dissolution_liquidation"]:
            slot_values = case_slot_state.get(scenario) or {}
            if self._has_any_slot_value(slot_values):
                trimmed_slot_state[scenario] = slot_values
        if len(trimmed_slot_state) == 1 and trimmed_slot_state.get("active_scenario") == "general":
            prompt_analysis["case_slot_state"] = {}
        else:
            prompt_analysis["case_slot_state"] = trimmed_slot_state
        return prompt_analysis

    def _has_any_slot_value(self, slot_values):
        return any(value not in (None, "", [], {}) for value in (slot_values or {}).values())

    def _event(self, name, data):
        return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _progress(self, stage, message):
        return self._event("progress", {"stage": stage, "message": message})

    def _chunk(self, text, size=16):
        for i in range(0, len(text), size):
            yield text[i:i+size]
