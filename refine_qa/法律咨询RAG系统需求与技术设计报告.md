# 法律咨询 RAG 系统需求与技术设计报告

## 1. 文档说明

### 1.1 编写目的

本文档用于指导重新构建一套面向企业法律咨询场景的 RAG 智能问答系统。设计依据包括：

- 毕业论文《基于检索增强生成的智能问答系统设计与实现》中对系统需求、RAG 链路、Memory 机制、前后端通信和测试评价的描述。
- 当前已有系统的工程实现，包括 FastAPI 后端、Vue3 前端、Elasticsearch 检索、Redis 短期记忆、MongoDB 会话存储、Neo4j 长期记忆、WebSocket 人工客服等模块。
- 当前系统运行与代码检查中暴露出的工程问题，包括依赖缺失、配置分散、模型名硬编码、模块边界不清、记忆实现不完整、人工客服状态管理不稳定等。

### 1.2 建设目标

新系统应在保留当前系统有效技术路线的基础上进行重构，而不是简单修补旧代码。核心目标如下：

- 建立稳定、可维护、可测试的法律咨询 RAG 工程架构。
- 支持公司法领域知识库构建、混合检索、重排序、结构化答案生成和引用溯源。
- 支持多轮会话中的短期、中期、长期记忆，并通过渐进式披露控制上下文注入。
- 支持风险识别、域外拦截、免责声明和人工客服兜底。
- 支持后续扩展到法律文档上传、多模态证据材料检索、RAGAS 评测和远端部署。

### 1.3 术语说明

| 术语 | 说明 |
| --- | --- |
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| LLM | Large Language Model，大语言模型 |
| ES | Elasticsearch，用于全文检索、BM25 检索和向量检索 |
| BM25 | 基于词项统计的稀疏检索算法 |
| RRF | Reciprocal Rank Fusion，倒数排名融合 |
| Reranker | 对召回候选文档进行精排的重排序模型 |
| Memory | 对话记忆模块，包括短期、中期、长期记忆 |
| OOD | Out-of-Domain，域外问题 |

## 2. 当前系统现状与重构必要性

### 2.1 当前技术框架

当前系统已经具备较完整的原型能力：

| 层级 | 当前实现 |
| --- | --- |
| 前端 | Vue3、Vite、Bootstrap，包含聊天界面、历史侧边栏、客服工作台 |
| 后端 | FastAPI，提供 REST API 和 WebSocket |
| 语言模型 | DashScope OpenAI 兼容接口，当前目标模型为 `qwen3.6-max-preview` |
| 向量模型 | `tongyi-embedding-vision-plus-2026-03-06` |
| 向量与文本检索 | Elasticsearch，使用 `dense_vector` 字段、BM25 和规则召回 |
| 短期记忆 | Redis，按 `conversation_id` 保存近期问答 |
| 会话持久化 | MongoDB，保存对话历史和人工客服消息 |
| 长期记忆 | Neo4j，保存“公司法类别”节点和“历史对话”节点 |
| 人工客服 | 基于 WebSocket 的用户端与客服端双向通信 |

### 2.2 当前系统已有功能

当前系统已经实现或部分实现以下功能：

- 新建对话。
- 提交法律咨询问题。
- 展示 AI 回答。
- 展示历史对话列表。
- 加载历史对话。
- 识别转人工意图。
- WebSocket 用户端与客服端通信。
- 公司法文档解析、切分、嵌入和 ES 入库。
- 在线查询时执行向量召回、BM25 召回、规则召回和 RRF 融合。
- 将对话写入 Redis，并异步同步到 Neo4j。

### 2.3 当前系统主要问题

#### 2.3.1 工程结构问题

- 后端 `main.py` 过于庞大，混合了路由、数据库访问、WebSocket 状态管理、业务逻辑和异常处理。
- RAG 逻辑、记忆逻辑、模型调用逻辑之间耦合严重，难以单元测试。
- 配置分散在根目录 `.env`、`backend/.env`、`backend/rag/.env`，存在同名变量不一致风险。
- 模型名、索引名、路径等关键配置存在硬编码或隐式默认值。
- 依赖清单不完整，运行时曾出现 `cn2an`、`fuzzywuzzy`、`motor` 等缺失问题。

#### 2.3.2 RAG 链路问题

- 文档元数据不足，当前 ES 文档主要包含 `content`、`embedding`、`filename`、`chunk_index`，缺少 `law_name`、`article_id`、`chapter`、`clause`、`effective_date`、`source_type` 等字段。
- 规则召回与 BM25、向量召回写在同一个脚本中，缺少统一检索接口和可观测日志。
- Reranker 依赖本地模型目录，但缺少模型资产时会导致启动失败；虽然已临时降级，但新系统应将其设计为可插拔组件。
- 当前 `rag_company_law_qa` 中会重复执行 `search_similar`，造成额外的模型调用和检索开销。

#### 2.3.3 Memory 模块问题

- 论文中设计了短期记忆、中期摘要、长期图记忆和渐进式披露，但当前代码主要实现了 Redis 短期记忆和 Neo4j 长期记忆，中期摘要尚未形成稳定工程模块。
- Redis 短期记忆采用过期时间保存，但没有明确滑动窗口大小、排序规则和注入预算控制。
- Neo4j 长期记忆实现存在参数命名风险，例如查询语句中使用 `company_law_nam`，而运行参数为 `company_law_name`，可能导致长期记忆读取失败。
- 长期记忆写入采用 `threading.Timer` 延迟异步执行，缺少失败重试、日志追踪和任务状态管理。
- 记忆注入缺少统一评分函数和 Token 预算控制，容易造成上下文冗余或遗漏关键历史。

#### 2.3.4 人工客服问题

- 人工客服状态管理依赖内存字典，服务重启后状态丢失。
- 客服端 HTML 中存在前端渲染结构问题，例如等待列表内重复嵌套 `v-for`。
- 用户端和客服端 WebSocket 地址策略不统一，在不同部署方式下容易连接错误。
- 转人工策略主要依赖关键词和模糊匹配，缺少与检索置信度、模型低置信回答、连续失败轮次的联动。

#### 2.3.5 合规与答案质量问题

- 当前 Prompt 只要求模型输出“是否足够”和“回答”，未充分实现论文中要求的法律三段论结构。
- 缺少强制免责声明后处理，不能完全依赖模型自觉输出免责声明。
- 缺少域外问题、违法规避类问题和高风险问题的统一安全护栏。
- 回答缺少结构化引用字段，前端难以实现条文溯源、悬浮查看和证据列表展示。

## 3. 新系统总体需求

### 3.1 用户角色

按照 UML 用例建模规范，新系统只将人类角色作为系统参与者：

| 角色 | 说明 |
| --- | --- |
| 法律咨询用户 | 发起法律问题、查看回答、追问、查看历史、请求人工 |
| 人工客服/法律顾问 | 接入高风险或复杂会话，查看上下文并回复用户 |
| 系统管理员 | 管理知识库、配置模型、查看评测结果和系统日志 |

### 3.2 功能模块

新系统划分为以下核心模块：

| 模块 | 功能 |
| --- | --- |
| 用户交互模块 | 聊天、历史会话、引用查看、免责声明确认 |
| 智能问答模块 | 意图识别、查询改写、RAG 检索、答案生成 |
| 知识库构建模块 | 文档解析、清洗、结构化切分、嵌入、入库、增量更新 |
| 检索融合模块 | 向量召回、BM25 召回、规则召回、RRF 融合、Rerank |
| Memory 模块 | Redis 短期记忆、周期摘要中期记忆、Neo4j 长期记忆、渐进式披露 |
| 会话管理模块 | MongoDB 持久化、会话隔离、历史恢复 |
| 人机协同模块 | 转人工检测、客服队列、WebSocket 实时通信 |
| 安全合规模块 | 域外拦截、违法意图识别、免责声明、日志审计 |
| 评测与观测模块 | RAGAS 评测、Memory 评测、检索日志、错误追踪 |

## 4. 业务需求设计

### 4.1 智能法律咨询

用户可在前端聊天窗口输入公司法相关问题，系统应完成以下流程：

1. 接收用户自然语言问题。
2. 判断是否为法律领域问题。
3. 判断是否存在违法规避、恶意诱导或高风险内容。
4. 对口语化、过短或多意图问题进行意图解析和查询改写。
5. 调用 RAG 检索链路获取相关法律依据。
6. 结合会话记忆和检索上下文生成结构化法律回答。
7. 返回法律依据、事实认定、结论建议、行动建议、引用来源和免责声明。

### 4.2 查询改写与意图解析

系统需要处理以下输入场景：

| 场景 | 处理策略 |
| --- | --- |
| 用户问题过短 | 扩展为多个法律检索表达 |
| 用户问题口语化 | 转换为法律术语表达 |
| 用户问题包含多个诉求 | 拆分为多个子问题 |
| 用户事实要件缺失 | 生成澄清问题，不直接给最终结论 |
| 用户指定法条编号 | 触发规则召回，优先定位条文 |

意图解析结果建议采用结构化对象：

```json
{
  "domain": "company_law",
  "intent_type": "legal_consultation",
  "risk_level": "normal",
  "need_clarification": false,
  "missing_slots": [],
  "rewritten_queries": ["股东查账权适用条件", "公司法 股东 查阅会计账簿"],
  "entities": {
    "subject": "股东",
    "legal_relation": "公司治理"
  }
}
```

### 4.3 三段论式法律回答

法律回答必须符合“法律依据、事实认定、结论建议”的三段论结构。建议固定输出格式：

```text
【法律依据】
列出可追溯的法律条文，并标注文档引用编号。

【事实认定】
归纳用户已经提供的关键事实，明确哪些事实仍待补充。

【法律分析】
将事实代入法律规范，说明适用或不适用的理由。

【结论与建议】
给出谨慎、非绝对化的处理建议。

【参考来源】
[1] 《中华人民共和国公司法》第X条，来源文件：xxx.docx

【特别声明】
本回答由人工智能系统生成，仅供法律信息参考，不构成正式法律意见。具体案件请咨询具备执业资格的专业律师。
```

### 4.4 知识溯源

系统应在回答中返回可渲染的引用数据，而不是只拼接文本。后端响应建议包含：

```json
{
  "answer": "...",
  "citations": [
    {
      "citation_id": "1",
      "law_name": "中华人民共和国公司法",
      "article_id": "第七十一条",
      "content": "...",
      "filename": "公司法第三章.docx",
      "score": 0.92
    }
  ]
}
```

前端应支持：

- 回答中显示引用编号。
- 点击或悬浮引用编号展示原文片段。
- 在回答末尾展示参考来源列表。
- 当引用来源不足时提示“当前知识库未检索到足够依据”。

### 4.5 多轮对话管理

系统应支持用户在同一会话中连续追问，并正确理解指代、省略和上下文关系。

具体要求：

- 每个会话使用唯一 `conversation_id` 隔离。
- 当前问题只能读取同一会话的历史、缓存和长期记忆。
- 会话历史持久化到 MongoDB。
- 近期若干轮问答缓存到 Redis。
- 关键阶段性事实周期性摘要，形成中期记忆。
- 重要历史问答写入 Neo4j 长期记忆图。

### 4.6 人工客服兜底

系统应在以下情况下触发人工客服建议：

- 用户明确输入“转人工”“人工客服”“找律师”等表达。
- 用户连续多轮表达不满或问题未解决。
- 检索最高置信度低于阈值。
- 模型判断事实要件严重缺失且用户不愿继续补充。
- 问题具有高风险性质，需要专业人员介入。

触发后系统应：

- 停止自动生成高风险结论。
- 将会话状态设置为 `waiting_support`。
- 将用户问题、历史摘要、关键事实、已检索文档打包传递给客服端。
- 前端显示等待提示。
- 客服接入后切换为 WebSocket 实时对话。

### 4.7 合规与安全

系统必须具备以下安全策略：

- 首次使用弹出免责声明和用户协议确认。
- 每次法律分析回答末尾强制附加免责声明。
- 对域外问题进行拒答并引导回法律咨询。
- 对违法规避、教唆犯罪、规避强制执行、逃避社保等问题拒答。
- 禁止输出“必胜”“一定违法”“肯定判几年”等绝对化结论。
- 对高风险请求保留后端审计日志。

## 5. 非功能需求

### 5.1 性能需求

| 指标 | 目标 |
| --- | --- |
| 普通问答首包响应 | 不超过 3 秒，若使用流式输出则首 token 不超过 2 秒 |
| 检索链路耗时 | Top-K 召回与融合不超过 1 秒 |
| 历史会话加载 | 不超过 500 ms |
| WebSocket 消息转发 | 不超过 300 ms |

### 5.2 可靠性需求

- 模型调用失败时返回可理解的错误提示，不暴露底层异常。
- ES、Redis、MongoDB、Neo4j 任一组件异常时应有降级策略。
- Reranker 不可用时可降级为 RRF 结果。
- 记忆写入失败不应阻断当前回答返回。
- 后端所有关键链路应有结构化日志。

### 5.3 可维护性需求

- 后端按模块拆分，不再将所有逻辑堆叠在 `main.py`。
- 模型名、数据库地址、阈值、窗口大小全部通过配置管理。
- 检索、生成、记忆、会话、客服模块均可单独测试。
- 使用统一异常类型和响应格式。
- 依赖文件完整记录运行所需依赖。

### 5.4 隐私与隔离需求

- 所有用户数据按 `conversation_id` 隔离。
- 客服只能访问已接入会话。
- Redis 短期记忆设置合理 TTL。
- MongoDB 会话记录需支持后续脱敏导出。
- 日志中避免直接打印完整敏感案情，必要时只记录摘要或哈希。

## 6. 技术架构设计

### 6.1 总体架构

新系统采用前后端分离架构，并将后端拆分为清晰的领域模块：

```text
用户浏览器
  |
  | HTTP / WebSocket
  v
Vue3 前端
  |
  v
FastAPI API 层
  |
  +-- 会话服务 ConversationService
  +-- 问答编排服务 QAOrchestrator
  +-- 检索服务 RetrievalService
  +-- 生成服务 GenerationService
  +-- 记忆服务 MemoryService
  +-- 人工客服服务 SupportService
  +-- 安全合规服务 GuardrailService
  |
  +-- Elasticsearch
  +-- MongoDB
  +-- Redis
  +-- Neo4j
  +-- DashScope LLM / Embedding API
```

### 6.2 推荐目录结构

```text
backend/
  app/
    main.py
    core/
      config.py
      logging.py
      exceptions.py
    api/
      routes_chat.py
      routes_conversation.py
      routes_support.py
      routes_admin.py
      websocket.py
    schemas/
      chat.py
      conversation.py
      citation.py
      memory.py
    services/
      qa_orchestrator.py
      retrieval_service.py
      generation_service.py
      memory_service.py
      support_service.py
      guardrail_service.py
      knowledge_ingest_service.py
    repositories/
      mongo_repo.py
      redis_repo.py
      es_repo.py
      neo4j_repo.py
    rag/
      chunker.py
      embedder.py
      retrievers.py
      fusion.py
      reranker.py
      prompts.py
    tests/
      test_retrieval.py
      test_memory.py
      test_chat_api.py
frontend/
  src/
    api/
    components/
    views/
    stores/
```

### 6.3 配置管理

新系统应只保留一个主要配置入口，例如 `backend/.env`，并通过 `pydantic-settings` 读取。

核心配置项：

```env
APP_ENV=local
API_HOST=0.0.0.0
API_PORT=8000

DASHSCOPE_API_KEY=xxx
LLM_MODEL=qwen3.6-max-preview
EMBEDDING_MODEL=tongyi-embedding-vision-plus-2026-03-06

ES_HOST=http://localhost:9200
ES_INDEX=legal_corpus

MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=rag_system

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change_me

SHORT_MEMORY_WINDOW=5
SHORT_MEMORY_TTL_SECONDS=3600
SUMMARY_INTERVAL=6
LONG_MEMORY_CATEGORY_LIMIT=5
LONG_MEMORY_CATEGORY_THRESHOLD=0.6
LONG_MEMORY_HISTORY_THRESHOLD=0.5
LONG_MEMORY_DOC_THRESHOLD=0.8
```

## 7. 数据库设计

### 7.1 Elasticsearch 索引设计

建议索引名：`legal_corpus`

字段设计：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `content` | `text` | 原始文本块 |
| `embedding` | `dense_vector` | 1152 维向量 |
| `law_name` | `keyword` | 法律名称 |
| `chapter` | `keyword` | 章节 |
| `article_id` | `keyword` | 条文编号 |
| `clause_id` | `keyword` | 款编号，可选 |
| `item_id` | `keyword` | 项编号，可选 |
| `filename` | `keyword` | 来源文件 |
| `chunk_index` | `integer` | 切片序号 |
| `source_type` | `keyword` | 法律、司法解释、问答材料等 |
| `effective_date` | `date` | 生效日期 |
| `expired_date` | `date` | 失效日期 |
| `created_at` | `date` | 入库时间 |

设计原则：

- 必须保持“条—款—项”结构完整性。
- 同一条文过长时再进行二级递归切分。
- 子切片必须保留父级 `article_id`，方便溯源和组装。
- 离线入库和在线查询必须使用同一 embedding 模型。

### 7.2 MongoDB 会话设计

集合：`conversations`

```json
{
  "conversation_id": "1",
  "user_id": "anonymous_or_user_id",
  "title": "股东查账权咨询",
  "status": "active",
  "messages": [
    {
      "qa_id": "1.1",
      "role": "user",
      "content": "我是小股东，可以查公司账吗？",
      "timestamp": "2026-05-23T10:00:00+08:00"
    },
    {
      "qa_id": "1.1",
      "role": "assistant",
      "content": "...",
      "citations": [],
      "timestamp": "2026-05-23T10:00:05+08:00"
    }
  ],
  "support_messages": [],
  "created_at": "2026-05-23T10:00:00+08:00",
  "updated_at": "2026-05-23T10:00:05+08:00"
}
```

### 7.3 Redis 短期记忆设计

键名：

```text
memory:short:{conversation_id}
```

数据结构建议使用 List，按时间追加：

```json
{
  "qa_id": "1.3",
  "question": "...",
  "answer": "...",
  "citations": [],
  "retrieved_docs": [],
  "created_at": "..."
}
```

写入策略：

- 每轮问答后写入 Redis。
- 只保留最近 `SHORT_MEMORY_WINDOW` 轮。
- 设置 TTL，默认 3600 秒或根据业务调整。

### 7.4 中期摘要设计

MongoDB 集合：`conversation_summaries`

```json
{
  "conversation_id": "1",
  "summary_id": "summary-1",
  "from_qa_id": "1.1",
  "to_qa_id": "1.6",
  "summary": "用户是公司小股东，关注查账权和利润分配问题...",
  "atomic_facts": [
    "用户身份为公司小股东",
    "用户关注公司财务账簿查阅问题"
  ],
  "created_at": "..."
}
```

触发策略：

- 每 `SUMMARY_INTERVAL` 轮生成一次周期摘要。
- 摘要应保留身份、时间、主体、争议焦点、证据情况、已给建议。
- 摘要生成异步执行，不阻断当前回答。

### 7.5 Neo4j 长期记忆设计

长期记忆必须采用图结构：

```text
G_t = (V_t, E_t)
```

节点类型：

| 节点 | 字段 |
| --- | --- |
| Category | `id`、`name`、`u_j`、`conv_id`、`count`、`created_at`、`updated_at` |
| History | `qa_id`、`q`、`a`、`D`、`v_i`、`created_at` |

关系：

```text
(Category)-[:CONTAINS]->(History)
```

写入流程：

1. 对当前问题向量化，得到 `v_i`。
2. 与当前会话已有 Category 语义中心 `u_j` 匹配。
3. 若最大相似度低于阈值且类别数量未超过上限，创建新 Category。
4. 创建 History 节点并连接到 Category。
5. 使用均值聚合更新 Category 语义中心：

```text
u_new = (n * u_j + v_new) / (n + 1)
```

读取流程：

1. 当前问题向量与 Category 粗匹配。
2. 在最佳 Category 下与 History 节点细匹配。
3. 差异化返回：

```text
similarity > tau_h: 返回 (q, a)
similarity > tau_d: 返回 (q, a, D)
```

## 8. RAG 技术设计

### 8.1 知识库构建流程

```text
法律文档
  -> 文档解析
  -> 文本清洗
  -> 法律结构识别
  -> 条文级切分
  -> 长条文递归细分
  -> 元数据绑定
  -> Embedding 向量化
  -> Elasticsearch 入库
  -> 入库校验
```

### 8.2 文本清洗

清洗规则：

- 删除页眉、页脚、页码、目录残留。
- 统一空格、换行、全角半角标点。
- 保留法律结构符号，例如“第X条”“第一款”“（一）”。
- 记录来源文件、章节、条文编号。

### 8.3 混合切片

主切片策略：

- 优先按“第X条”切分。
- 保证单个 Chunk 包含完整法律规范。
- 对过长条文按段落、句号、分号、逗号逐级递归拆分。
- 子切片保留父条文编号和上下文重叠。

### 8.4 多路召回

召回通道：

| 通道 | 作用 |
| --- | --- |
| 向量召回 | 解决口语表达与法律术语之间的语义差异 |
| BM25 召回 | 强化法律术语、关键词、专名匹配 |
| 规则召回 | 精准处理“第X条”“第X章”等结构化查询 |

### 8.5 RRF 融合

不同召回通道分数尺度不同，因此统一采用 RRF 基于排名融合：

```text
score(d) = Σ 1 / (k + rank_i(d))
```

默认 `k=60`。

### 8.6 Reranker 精排

建议设计为可插拔组件：

- 若本地 `BGE-rerank-large` 可用，则执行 Cross-Encoder 精排。
- 若模型文件不存在或依赖缺失，则自动降级为 RRF 排序结果。
- Reranker 只处理融合后的候选集，不参与全量召回。

### 8.7 答案生成

生成模型：

```text
qwen3.6-max-preview
```

提示词输入包含：

- 系统角色。
- 安全边界。
- 输出格式约束。
- 用户当前问题。
- 改写后的查询。
- 检索到的法律上下文。
- 短期记忆。
- 中期摘要。
- 必要时注入的长期记忆。

## 9. Memory 技术设计

### 9.1 分层记忆结构

| 层级 | 存储 | 作用 |
| --- | --- | --- |
| 短期记忆 | Redis | 最近若干轮原文问答，处理追问和指代 |
| 中期记忆 | MongoDB | 周期摘要，保存阶段性案情和争议焦点 |
| 长期记忆 | Neo4j | 主题聚类、相似历史回忆、跨阶段补全 |

### 9.2 渐进式披露

系统不应默认注入全部记忆，而应按成本从低到高逐级尝试：

1. 注入当前问题和检索上下文。
2. 注入短期 Redis 记忆。
3. 若事实仍不足，注入中期摘要。
4. 若仍不足，查询 Neo4j 长期记忆。
5. 若仍不足，触发澄清问题或人工客服。

### 9.3 记忆评分

统一评分函数：

```text
Score(m, q) = α * sim(m, q) + β * recency(m) + γ * importance(m) + δ * type_weight(m)
```

其中：

- `sim` 表示语义相似度。
- `recency` 表示时间新近性。
- `importance` 表示法律事实重要性。
- `type_weight` 表示记忆类型权重。

### 9.4 Token 预算控制

生成前应先计算上下文预算：

```text
memory_budget = max_context_length - system_prompt - current_query - retrieved_context - output_reserved
```

记忆模块只能在 `memory_budget` 内注入内容，避免长历史挤占法律依据。

## 10. 后端 API 设计

### 10.1 会话接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/conversations` | 新建会话 |
| `GET` | `/api/conversations` | 获取会话列表 |
| `GET` | `/api/conversations/{conversation_id}` | 获取会话详情 |
| `DELETE` | `/api/conversations/{conversation_id}` | 删除会话，可选 |

### 10.2 问答接口

```http
POST /api/chat
```

请求：

```json
{
  "conversation_id": "1",
  "query": "股东可以查公司账吗？",
  "stream": false
}
```

响应：

```json
{
  "conversation_id": "1",
  "qa_id": "1.1",
  "answer": "...",
  "need_human": false,
  "need_clarification": false,
  "citations": [],
  "retrieval_trace": {
    "dense": [],
    "bm25": [],
    "rule": [],
    "fused": [],
    "reranked": []
  }
}
```

### 10.3 人工客服接口

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| WebSocket | `/ws/user/{conversation_id}` | 用户端实时连接 |
| WebSocket | `/ws/support/{support_id}` | 客服端实时连接 |
| GET | `/support/{support_id}` | 客服工作台页面 |

### 10.4 管理接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/admin/knowledge/import` | 导入知识库 |
| `GET` | `/api/admin/knowledge/status` | 查看索引状态 |
| `POST` | `/api/admin/evaluate/rag` | 执行 RAG 评测 |
| `GET` | `/api/admin/logs/retrieval` | 查看检索日志 |

## 11. 前端设计

### 11.1 用户端页面

核心组件：

- `ChatView`：聊天主区域。
- `Sidebar`：历史会话列表。
- `ChatBubble`：消息气泡。
- `CitationPanel`：引用来源面板。
- `DisclaimerModal`：首次使用免责声明。
- `SupportStatusBar`：人工客服状态提示。

### 11.2 交互要求

- 新建会话后自动进入空白聊天页。
- 发送问题后立即展示用户消息和加载状态。
- 支持回答 Markdown 渲染。
- 支持引用编号点击查看原文。
- 支持回答失败时展示友好错误。
- 支持人工客服接入、断开、重连状态提示。

### 11.3 客服端页面

客服端应支持：

- 查看等待接入会话。
- 查看用户问题、历史摘要和 AI 已检索资料。
- 接入会话。
- 实时发送消息。
- 结束会话。

## 12. 评测设计

### 12.1 RAG 评测

使用 RAGAS 或自定义评测脚本评估：

| 指标 | 说明 |
| --- | --- |
| Faithfulness | 回答是否忠实于检索上下文 |
| AnswerRelevancy | 回答是否围绕问题 |
| ContextPrecision | 召回上下文是否相关 |
| ContextRecall | 标准依据是否被召回 |
| AnswerCorrectness | 回答是否与标准答案一致 |

论文中的目标参考：

- Faithfulness：目标接近或超过 0.90。
- ContextRecall：常见场景达到 80% 以上。
- Top1 精准度：通过规则召回和 Rerank 显著优于基础 RAG。

### 12.2 Memory 评测

指标：

| 指标 | 说明 |
| --- | --- |
| MemoryRecall | 是否召回所需历史记忆 |
| MemoryPrecision | 注入记忆是否相关 |
| ContextContinuity | 回答是否继承上下文 |

论文中的完整 Memory 方案目标参考：

- MemoryRecall：约 0.84。
- MemoryPrecision：约 0.67。
- ContextContinuity：约 0.84。

### 12.3 前后端功能测试

测试项：

- 新建会话。
- 提交普通法律问题。
- 获取历史会话列表。
- 加载指定会话。
- 多会话隔离。
- 转人工触发。
- 客服接入与消息转发。
- ES 不可用降级。
- Reranker 不可用降级。
- 模型 API 失败降级。

## 13. 重构实施计划

### 13.1 第一阶段：基础工程重构

目标：

- 建立新的后端目录结构。
- 统一配置管理。
- 完成数据库连接封装。
- 完成基础会话 API。
- 完成前端基础聊天页。

交付物：

- 可启动的 FastAPI 服务。
- 可启动的 Vue3 前端。
- MongoDB 会话读写。

### 13.2 第二阶段：知识库与检索链路

目标：

- 重写文档解析、清洗、切片、入库流程。
- 设计完整 ES mapping。
- 实现向量召回、BM25、规则召回和 RRF。
- 接入可选 Reranker。

交付物：

- 知识库构建脚本。
- 检索服务。
- 检索调试接口。

### 13.3 第三阶段：答案生成与溯源

目标：

- 接入 `qwen3.6-max-preview`。
- 固化三段论 Prompt。
- 实现引用数据结构。
- 实现强制免责声明。

交付物：

- 结构化问答接口。
- 前端引用展示。

### 13.4 第四阶段：Memory 模块

目标：

- 实现 Redis 短期记忆滑动窗口。
- 实现周期摘要中期记忆。
- 修正并重构 Neo4j 长期记忆。
- 实现渐进式披露注入。

交付物：

- MemoryService。
- Memory 评测样例。

### 13.5 第五阶段：人工客服与安全护栏

目标：

- 重构 WebSocket 状态管理。
- 实现客服队列持久化或可恢复机制。
- 接入风险分类和域外拦截。
- 完成日志审计。

交付物：

- 用户端人工客服流程。
- 客服工作台。
- 安全策略模块。

### 13.6 第六阶段：测试与部署

目标：

- 建立单元测试和接口测试。
- 建立 RAGAS 评测脚本。
- 建立本地部署和 Docker Compose 部署方案。
- 输出系统使用说明。

交付物：

- 测试报告。
- 部署文档。
- 演示数据。

## 14. 推荐技术栈

| 类别 | 技术 |
| --- | --- |
| 前端 | Vue3、Vite、Bootstrap 或 TailwindCSS |
| 后端 | Python 3.11+、FastAPI、Pydantic v2、Uvicorn |
| LLM | DashScope OpenAI compatible API，`qwen3.6-max-preview` |
| Embedding | `tongyi-embedding-vision-plus-2026-03-06` |
| 检索 | Elasticsearch 8.x |
| 缓存 | Redis |
| 会话存储 | MongoDB |
| 长期记忆 | Neo4j |
| Rerank | BGE-rerank-large，可选本地部署 |
| 测试 | pytest、httpx、RAGAS |
| 部署 | 本地服务 + Docker Compose 可选 |

## 15. 关键设计原则

- 法律文本切片必须保持“条—款—项”结构完整性。
- 离线入库和在线查询必须使用同一向量模型。
- 检索链路必须可观测，返回每个召回通道的候选结果。
- Reranker、Neo4j、Redis 均应可降级，不应阻断基础问答。
- 回答必须具备法律依据、事实认定、法律分析、结论建议和免责声明。
- 记忆注入必须遵循渐进式披露，不允许无差别拼接全部历史。
- 所有数据访问必须以 `conversation_id` 做会话隔离。
- 人工客服是高风险法律咨询的兜底路径，不应与普通 AI 问答状态混淆。

## 16. 当前系统可复用资产

| 资产 | 是否复用 | 说明 |
| --- | --- | --- |
| Vue3 前端项目 | 部分复用 | 可复用聊天框、侧边栏样式，需重构状态管理 |
| FastAPI 技术选型 | 复用 | 但需重构模块结构 |
| ES 文档数据 | 可复用 | 但建议按新 mapping 重新入库 |
| 公司法 docx 数据 | 复用 | 作为知识库原始数据 |
| 混合召回思路 | 复用 | 需封装为独立 RetrievalService |
| Redis 短期记忆思路 | 复用 | 需改为 List + 滑动窗口 |
| Neo4j 长期记忆思路 | 复用 | 需修正字段、关系和查询逻辑 |
| WebSocket 人工客服思路 | 复用 | 需重写队列和连接状态 |
| Docker Compose 文件 | 部分复用 | 新系统应支持本地启动和容器启动两种模式 |

## 17. 风险与应对

| 风险 | 应对 |
| --- | --- |
| DashScope API 不稳定或欠费 | 启动时增加模型连通性检查，支持友好错误提示 |
| 本地 Reranker 模型缺失 | 自动降级为 RRF 融合结果 |
| ES 索引维度不一致 | 入库前校验 embedding 维度和 mapping |
| 多数据库启动复杂 | 提供一键启动脚本和健康检查 |
| 记忆污染不同会话 | 所有查询强制带 `conversation_id` |
| 法律回答越界 | Guardrail + Prompt + 后处理三层约束 |
| 引用错误 | 回答必须基于结构化 citations 渲染，不允许模型伪造引用 |

## 18. 结论

新法律咨询 RAG 系统应以“稳定工程架构 + 高质量法律检索 + 可控答案生成 + 分层记忆 + 人工兜底”为核心重构方向。当前系统已经验证了技术路线的可行性，但代码组织、配置管理、记忆实现、合规控制和前后端状态管理仍不足以支撑稳定毕业设计演示和后续扩展。

建议后续实现时优先完成基础工程重构与检索链路重写，再逐步接入 Memory、人工客服和评测模块。这样既能快速获得一个可运行的最小闭环，又能保证论文中描述的多路召回、重排、分层记忆和渐进式披露机制最终能够以清晰、可维护的方式落地。

## 19. 补充修订要求

本节根据后续补充需求对前述设计进行约束性修订。后续实现时，本节优先级高于前文中存在不一致的设计项。

### 19.1 长期记忆方案保持 Neo4j 动态历史数据库

长期记忆不更换为其他存储方案，仍沿用当前系统已经验证过的基于 Neo4j 的动态历史数据库方案。

核心约束如下：

- 长期记忆仍使用图结构 `G_t = (V_t, E_t)`。
- 节点仍分为主题类别节点 `Category` 与历史对话节点 `History`。
- 类别节点用于表示当前会话内形成的语义主题簇。
- 历史对话节点保存单轮问答、检索文档与问题向量。
- 新历史写入仍遵循“向量化、类别匹配、节点创建/挂载、类别中心更新”四步。
- 类别中心仍使用均值聚合动态更新。
- 检索仍采用“类别粗匹配 + 历史节点细匹配”的两级匹配策略。
- 差异化返回策略保持不变：低阈值返回 `(q, a)`，高阈值返回 `(q, a, D)`。

实现时仅修正当前代码中的工程问题，不改变该方案的基本机制：

- 修正 Neo4j 查询参数命名不一致问题。
- 将中文字段名迁移为内部稳定字段名，同时可保留展示层中文名。
- 将异步写入从 `threading.Timer` 改为后台任务队列或 FastAPI `BackgroundTasks`。
- 增加写入失败日志和重试机制。
- 严格以 `conversation_id` 作为长期记忆隔离边界。

### 19.2 Rerank 模型使用 qwen3-rerank

新系统的 Reranker 使用阿里云百炼 `qwen3-rerank` 云端重排序服务，复用当前 DashScope API Key，不再强依赖本地下载 `bge-rerank-large`。

模型策略如下：

| 项目 | 设计 |
| --- | --- |
| 模型名称 | `qwen3-rerank` |
| 来源 | 阿里云百炼 / DashScope |
| 使用方式 | 通过 DashScope Rerank API 调用 |
| 微调 | 不涉及 |
| 失败降级 | API 调用失败、欠费、限流或网络异常时降级为 RRF 排序 |

建议模型目录：

```text
不需要本地模型目录
```

建议配置项：

```env
RERANK_MODEL_NAME=qwen3-rerank
RERANK_ENDPOINT=https://dashscope.aliyuncs.com/compatible-api/v1/reranks
RERANK_ENABLED=true
RERANK_TOP_N=3
RERANK_DEVICE=auto
```

实现要求：

- 系统启动时不应强制要求 Reranker 可用。
- DashScope Rerank 调用失败时必须打印清晰日志，并自动走 RRF 结果。
- Reranker 只处理 RRF 融合后的候选文档，不参与全量召回。
- 由于当前阶段采用云端重排序服务，报告中的本地模型下载、困难负样本挖掘与微调训练流程不纳入第一阶段实现范围。

### 19.3 增加小模型 qwen3.6-flash

新系统除主生成模型 `qwen3.6-max-preview` 外，增加小模型 `qwen3.6-flash`。二者使用同一个 DashScope API Key。

模型职责划分如下：

| 模型 | 职责 |
| --- | --- |
| `qwen3.6-max-preview` | 最终法律回答生成、复杂法理分析、必要时的高质量总结 |
| `qwen3.6-flash` | 意图识别、请求重构、多意图拆解、槽位提取、中期摘要生成 |

建议配置项：

```env
LLM_MODEL=qwen3.6-max-preview
SMALL_LLM_MODEL=qwen3.6-flash
DASHSCOPE_API_KEY=xxx
```

工程设计中应将模型调用封装为统一服务：

```text
ModelService
  - call_main_model(): 使用 qwen3.6-max-preview
  - call_small_model(): 使用 qwen3.6-flash
```

这样可以避免在业务代码中散落模型名称和 API 调用逻辑。

### 19.4 意图识别与请求重构

新系统在进入 RAG 检索前增加“意图识别与请求重构”模块。该模块由 `qwen3.6-flash` 执行。

意图类型分为两类：

| 类型 | 说明 | 后续链路 |
| --- | --- | --- |
| 知识问答 | 用户询问法条含义、制度解释、程序规则等 | 正常走当前 RAG 链路 |
| 案例咨询 | 用户描述具体事实、纠纷、主体关系和诉求 | 进行多意图拆解、槽位提取、构建多个 query 后进入 RAG |

#### 19.4.1 知识问答

知识问答场景示例：

- “公司法第 232 条规定了什么？”
- “股东查账权的条件是什么？”
- “公司解散后必须清算吗？”

处理方式：

- 可进行轻量查询改写。
- 不强制进行槽位提取。
- 默认构建 1 到 3 个检索 query。
- 检索链路保持“向量召回 + BM25 + 规则召回 + RRF + Rerank”。

#### 19.4.2 案例咨询

案例咨询场景示例：

- “我是小股东，公司一直不给我看账，我能起诉吗？”
- “公司解散了但董事一直不清算，债权人怎么办？”
- “股东想把股权转出去，其他股东不同意怎么办？”

案例咨询必须执行以下步骤：

1. 意图净化：消除口语化、歧义表达和无关情绪。
2. 多意图拆解：将一个复杂咨询拆分为多个法律子问题。
3. 场景匹配：匹配到最接近的一类公司法案例场景。
4. 槽位提取：按该场景对应槽位抽取结构化事实。
5. 请求重写：为每个子意图构建独立检索 query。
6. 多 query 检索：每个 query 独立进入 RAG 检索。
7. 文档数量对齐：最终返回文档数与意图数量成比例。

文档数量规则：

```text
final_doc_count = intent_count * docs_per_intent
```

例如：

- 多意图拆解得到 3 个意图。
- 每个意图召回并精排后保留 3 篇文档。
- 最终传入生成模型的文档数应为 9 篇。

#### 19.4.3 三类公司法案例场景与槽位

第一类：股东权利与公司治理纠纷。

适用问题：

- 股东查账权。
- 股东会决议效力。
- 小股东知情权。
- 利润分配争议。
- 董监高损害股东权益。

槽位设计：

| 槽位 | 说明 |
| --- | --- |
| `consultant_identity` | 咨询人身份，如股东、小股东、隐名股东、董事 |
| `company_type` | 公司类型，如有限责任公司、股份有限公司 |
| `shareholding_status` | 持股情况，如持股比例、是否登记股东 |
| `dispute_action` | 争议行为，如拒绝查账、拒绝分红、决议程序异常 |
| `requested_right` | 用户主张的权利，如查账、撤销决议、要求赔偿 |
| `evidence_materials` | 证据材料，如股东名册、出资记录、会议通知 |
| `time_info` | 时间信息，如决议作出时间、申请查账时间 |
| `opposing_party` | 相对方，如公司、控股股东、董事 |

第二类：股权转让与出资责任纠纷。

适用问题：

- 股权转让。
- 其他股东优先购买权。
- 瑕疵出资。
- 未届期出资转让。
- 抽逃出资。

槽位设计：

| 槽位 | 说明 |
| --- | --- |
| `transferor_identity` | 转让方身份 |
| `transferee_identity` | 受让方身份 |
| `target_equity_ratio` | 拟转让股权比例 |
| `internal_or_external_transfer` | 内部转让或对外转让 |
| `notification_status` | 是否通知其他股东 |
| `other_shareholders_response` | 其他股东是否同意或主张优先购买权 |
| `capital_contribution_status` | 出资是否实缴、是否瑕疵出资 |
| `contract_status` | 是否签订股权转让协议 |
| `registration_status` | 是否办理工商变更登记 |

第三类：公司解散、清算与债权人保护纠纷。

适用问题：

- 公司解散。
- 清算义务。
- 清算组成立。
- 董事未及时清算责任。
- 债权人申请法院指定清算组。

槽位设计：

| 槽位 | 说明 |
| --- | --- |
| `dissolution_reason` | 解散原因，如期限届满、股东会决议、吊销执照、法院判决 |
| `company_status` | 公司当前状态，如存续、停业、被吊销、已注销 |
| `liquidation_status` | 是否成立清算组，是否开展清算 |
| `obligor_identity` | 清算义务人，如董事、控股股东 |
| `creditor_identity` | 债权人身份 |
| `debt_status` | 债权债务情况 |
| `delay_or_damage` | 是否因怠于清算造成损失 |
| `court_action` | 是否已申请法院介入 |
| `evidence_materials` | 证据，如营业执照状态、债权凭证、催告记录 |

#### 19.4.4 意图识别输出结构

`qwen3.6-flash` 应输出严格 JSON，便于后端解析：

```json
{
  "query_type": "case_consultation",
  "matched_scenario": "company_dissolution_liquidation",
  "risk_level": "normal",
  "need_clarification": false,
  "missing_slots": [],
  "intents": [
    {
      "intent_id": "I1",
      "intent_name": "判断公司是否需要清算",
      "rewritten_query": "公司因吊销营业执照解散后是否必须进行清算"
    },
    {
      "intent_id": "I2",
      "intent_name": "判断董事是否承担清算义务",
      "rewritten_query": "公司解散后董事未及时成立清算组是否承担赔偿责任"
    },
    {
      "intent_id": "I3",
      "intent_name": "判断债权人救济途径",
      "rewritten_query": "债权人能否申请人民法院指定清算组进行清算"
    }
  ],
  "slots": {
    "dissolution_reason": "营业执照被吊销",
    "company_status": "已被吊销但未清算",
    "liquidation_status": "未成立清算组",
    "creditor_identity": "债权人",
    "evidence_materials": ["债权凭证", "公司吊销记录"]
  }
}
```

#### 19.4.5 多 query 检索流程

案例咨询检索流程：

```text
用户原始问题
  -> qwen3.6-flash 意图识别
  -> 判断为案例咨询
  -> 多意图拆解
  -> 场景槽位提取
  -> 为每个意图生成 rewritten_query
  -> 每个 rewritten_query 独立执行 RAG 检索
  -> 每个意图保留 docs_per_intent 篇文档
  -> 合并为 final_context_docs
  -> qwen3.6-max-preview 生成最终结构化法律回答
```

每个意图内仍执行完整检索链路：

```text
rewritten_query
  -> 向量召回
  -> BM25 召回
  -> 规则召回
  -> RRF 融合
  -> qwen3-rerank 精排
  -> top docs_per_intent
```

### 19.5 中期摘要记忆使用 qwen3.6-flash

中期摘要记忆由 `qwen3.6-flash` 执行，以降低成本和延迟。

触发策略：

- 每隔固定轮次触发周期摘要，例如每 6 轮生成一次。
- 或当短期记忆 Token 长度超过阈值时触发。
- 摘要任务异步执行，不阻断当前回答。

摘要内容必须覆盖：

- 咨询人身份。
- 公司类型和主体关系。
- 关键事实。
- 已确认槽位。
- 缺失槽位。
- 争议焦点。
- 已引用法律依据。
- 已给出建议。
- 后续待跟进问题。

建议摘要结构：

```json
{
  "conversation_id": "1",
  "summary_range": {
    "from_qa_id": "1.1",
    "to_qa_id": "1.6"
  },
  "case_facts": [],
  "confirmed_slots": {},
  "missing_slots": [],
  "legal_issues": [],
  "cited_articles": [],
  "given_advice": [],
  "next_questions": []
}
```

中期摘要保存位置仍建议为 MongoDB，作为会话级阶段性记忆；在后续生成时由 MemoryService 根据渐进式披露策略选择注入。

### 19.6 根据当前法律源数据适配 ES 元数据

当前法律源数据位于：

```text
$PROJECT_ROOT/backend/rag/data
```

实际文件为按章节划分的公司法 `.docx`：

```text
公司法第一章.docx
公司法第二章.docx
...
公司法第十四章.docx
```

当前数据本身不包含明确的时效性、权威度、发布机关、生效日期、失效日期等字段。因此新系统设计不应强行依赖这些字段。

第一阶段 ES mapping 应适配当前数据实际情况：

| 字段 | 是否必需 | 说明 |
| --- | --- | --- |
| `content` | 必需 | 条文或子切片正文 |
| `embedding` | 必需 | 向量 |
| `law_name` | 必需 | 固定为“中华人民共和国公司法”或从文件推断 |
| `chapter` | 必需 | 从文件名提取，如“第一章” |
| `article_id` | 必需 | 从正文正则提取，如“第二百三十二条” |
| `filename` | 必需 | 来源文件名 |
| `chunk_index` | 必需 | 文件内切片序号 |
| `clause_id` | 可选 | 若能从条文内部识别款项则填写 |
| `item_id` | 可选 | 若能识别列举项则填写 |
| `source_type` | 可选 | 默认 `law_text` |
| `authority_level` | 暂不必需 | 当前数据无法可靠提供，可默认 `unknown` |
| `effective_date` | 暂不必需 | 当前数据无法可靠提供，可为空 |
| `expired_date` | 暂不必需 | 当前数据无法可靠提供，可为空 |

修订后的第一阶段 ES mapping 应避免把 `effective_date`、`expired_date`、`authority_level` 作为强依赖检索条件。后续如果补充权威来源数据，再升级为强元数据过滤。

### 19.7 网页输出改为流式输出

新系统前端回答输出改为流式输出，提升用户体验。

推荐方案：

- 普通问答接口支持 SSE 或 StreamingResponse。
- 前端在聊天气泡中逐 token 或逐片段追加内容。
- 流式结束后，再统一渲染 citations、免责声明和操作按钮。

推荐接口：

```http
POST /api/chat/stream
```

响应事件：

```text
event: meta
data: {"conversation_id":"1","qa_id":"1.1","mode":"normal"}

event: token
data: {"content":"根据"}

event: token
data: {"content":"《中华人民共和国公司法》"}

event: citations
data: {"citations":[...]}

event: done
data: {"status":"ok"}
```

前端要求：

- 发送后立即展示用户消息。
- 创建一个空 assistant 气泡。
- 每收到一个 `token` 事件追加到该气泡。
- 收到 `citations` 后渲染引用列表。
- 收到 `done` 后结束 loading 状态。
- 失败时保留已输出内容，并展示错误提示。

如果后续选择 WebSocket 流式输出，也必须与人工客服 WebSocket 通道区分，避免状态混乱。第一阶段更建议使用 SSE，因为它更适合服务端单向推送模型输出。

### 19.8 增加 Normal 与 Plus 模式

当前系统只有一种 `normal` 模式。新系统需要在用户输入框上方增加模式选择按钮：

```text
[Normal] [Plus]
```

第一阶段行为：

- 默认选中 `Normal`。
- 用户可切换为 `Plus`。
- `Plus` 当前仍走与 `Normal` 完全相同的后端链路。
- 请求中必须携带 `mode` 字段，为后续单独构建 Plus 链路预留。

前端请求示例：

```json
{
  "conversation_id": "1",
  "query": "股东可以查账吗？",
  "mode": "plus",
  "stream": true
}
```

后端枚举：

```text
ChatMode = normal | plus
```

后端编排逻辑：

```text
if mode == "normal":
    run_normal_chain()
elif mode == "plus":
    run_normal_chain()  # 第一阶段暂时复用
```

设计要求：

- 会话消息中保存当轮 `mode`。
- 前端历史消息可展示该轮使用的模式。
- Plus 模式不得在第一阶段引入额外不可控逻辑。
- 后续可在 Plus 模式中扩展更强检索、更长上下文、更复杂 Agent 推理或多轮澄清链路。

### 19.9 修订后的核心链路

综合补充需求后，新系统核心问答链路调整为：

```text
用户输入 + mode
  -> qwen3.6-flash 意图识别与请求重构
  -> 判断 query_type
     -> 知识问答：构建少量 rewritten_queries
     -> 案例咨询：多意图拆解 + 场景槽位提取 + 多 query 构建
  -> 每个 query 执行混合 RAG 检索
     -> 向量召回
     -> BM25 召回
     -> 规则召回
     -> RRF 融合
     -> qwen3-rerank 精排
  -> MemoryService 渐进式注入
     -> Redis 短期记忆
     -> qwen3.6-flash 中期摘要
     -> Neo4j 长期记忆
  -> qwen3.6-max-preview 流式生成法律回答
  -> 前端流式渲染
  -> 保存 MongoDB 会话
  -> 写入 Redis 短期记忆
  -> 异步更新中期摘要和 Neo4j 长期记忆
```

### 19.10 修订后的阶段优先级

后续实现建议按以下优先级推进：

1. 统一配置，加入 `LLM_MODEL`、`SMALL_LLM_MODEL`、`CHAT_MODE`、`RERANK_MODEL_PATH`。
2. 实现 `qwen3.6-flash` 意图识别与请求重构。
3. 改造检索服务，支持多 query、多意图、多文档数量对齐。
4. 接入 DashScope `qwen3-rerank`，失败自动降级。
5. 将前端输出改为流式。
6. 增加 Normal/Plus 模式按钮，并将 `mode` 传入后端。
7. 实现基于 `qwen3.6-flash` 的中期摘要。
8. 保持并重构 Neo4j 动态历史数据库长期记忆。
9. 根据当前 `backend/rag/data` 的章节 docx 数据重建 ES mapping 和入库流程。
