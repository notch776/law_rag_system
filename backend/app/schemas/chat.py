from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Citation(BaseModel):
    citation_id: str
    law_name: str = "中华人民共和国公司法"
    article_id: str = ""
    content: str
    filename: str = ""
    score: float = 0.0
    intent_id: Optional[str] = None


class ChatRequest(BaseModel):
    conversation_id: str
    query: str
    mode: str = Field(default="normal", pattern="^(normal|plus)$")
    stream: bool = True


class Message(BaseModel):
    role: str
    content: str
    timestamp: str
    qa_id: Optional[str] = None
    mode: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    conversation_id: str
    heading: str
    updated_at: str
    status: str = "active"


class ConversationDetail(BaseModel):
    conversation_id: str
    qa_id: str = ""
    status: str = "active"
    messages: List[Message] = Field(default_factory=list)


class IntentItem(BaseModel):
    intent_id: str
    intent_name: str
    rewritten_query: str


class IntentAnalysis(BaseModel):
    query_type: str = "knowledge_qa"
    matched_scenario: str = "general"
    risk_level: str = "normal"
    need_human: bool = False
    handoff_reason: str = ""
    direct_answer: bool = False
    direct_answer_text: str = ""
    need_clarification: bool = False
    clarification_question: str = ""
    missing_slots: List[str] = Field(default_factory=list)
    intents: List[IntentItem] = Field(default_factory=list)
    slots: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: str
    qa_id: str
    answer: str
    mode: str = "normal"
    need_human: bool = False
    need_clarification: bool = False
    citations: List[Citation] = Field(default_factory=list)
    intent_analysis: Optional[IntentAnalysis] = None
