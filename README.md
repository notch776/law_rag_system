# law_rag_system
## Intro
This project is a corporate law RAG (Retrieval-Augmented Generation) Q&A system. It employs Alibaba Cloud General Text Embedding Model v1 for vector representation and Qwen-Max (Tongyi Qianwen-Max) for text generation. Building upon traditional RAG architecture, the system integrates Elasticsearch as a vector database to accelerate vector retrieval speed, utilizes Redis for short-term history storage leveraging its in-memory characteristics to expedite response generation, and implements Neo4j for long-term dialogue history storage through tree-structured data organization to optimize query efficiency and ensure historical context relevance. By designing multiple thresholds in the RAG workflow and controlling context injection, the system achieves balanced optimization among token consumption, generation latency, and response accuracy, delivering superior conversational experience. Additionally, MongoDB is deployed for Q&A pair storage with field-level design to enable logical isolation across different dialogues.I also introduce WebSocket-based human agent transfer detection and real-time customer service module. The RAG retrieval workflow has been enhanced with a multi-path retrieval recall strategy encompassing vector recall, BM25 recall and rule-based recall triggered by question patterns (RRF for fusion).A re-ranking strategy has been implemented using the BGE-reranker-large model to further improve retrieval precision while optimizing context length control.

## Software Architecture
The system is primarily developed in Python and supports Docker-based containerized deployment (requires modification of connection URIs in code and Dockerfile configurations). 
### The project integrates a hybrid database architecture comprising:
Structured Database: MySQL
Vector Database: Elasticsearch (configured with IK-max-word tokenizer for Chinese text analysis)
NoSQL Databases: Redis (in-memory caching), MongoDB (document storage), Neo4j (graph database)
### Database management and monitoring tools include:
Navicat (MySQL/MongoDB administration)
Elasticsearch Client (es-client)
Tiny RDM (Redis management)
### System Architecture:
Backend Framework: FastAPI 
Frontend Framework: Vue3 
### Communication Protocols:
Smart Q&A: HTTP/REST API
Human Agent Transfer: WebSocket protocol
### Key Technical Components:
Vector Search Optimization:
Elasticsearch configured with IK-max-word analyzer for fine-grained Chinese tokenization
BGE-reranker-large model for post-retrieval re-ranking of candidate passages
System Integration:
Hybrid database synchronization strategies
Real-time WebSocket handoff mechanism between AI and human agents
Context-aware session management across Redis (short-term) and Neo4j (long-term)
Model Operations:
DashScope API integration for Qwen-Max LLM
Local deployment of BGE-reranker-large re-ranking model and fine tuning using Q-D pairs dataset
Embedding generation via Alibaba Cloud Text Embedding Model v4

## User Manual
This is a corporate law domain-specific multi-turn conversation RAG system. Users can initiate new dialogues to inquire about corporate law matters, with responses generated based on authoritative legal data. Follow-up questions are supported within dialogues, though new dialogues are recommended for unrelated topics. Historical dialogues can be resumed through the left-side conversation panel using question/ timestamp metadata. The system maintains contextual continuity while optimizing token economy through intelligent context management.
<img width="2475" height="1372" alt="image" src="https://github.com/user-attachments/assets/880ddb9e-1142-4e23-a902-dd01095bbb7e" />
<img width="2481" height="1371" alt="image" src="https://github.com/user-attachments/assets/0bc803bd-8c38-4817-9b46-428e0d25214c" />
<img width="3826" height="2032" alt="image" src="https://github.com/user-attachments/assets/65ef9056-ea31-4f5c-bfbb-5e855d77df90" />
<img width="2188" height="1399" alt="image" src="https://github.com/user-attachments/assets/b0a29c79-0963-4f43-a933-b5abc21ed8c0" />
<img width="2238" height="1530" alt="image" src="https://github.com/user-attachments/assets/7fa65266-51b6-4326-8696-48a680593ec2" />

## Algorithm Process Overview
<img width="1628" height="1084" alt="image" src="https://github.com/user-attachments/assets/591141b5-9eca-4c8e-bf1d-eec91a541de8" />
<img width="1482" height="839" alt="image" src="https://github.com/user-attachments/assets/e18dc766-68cb-4d29-8f36-24797e07ace8" />

## Test Case
Question: Under Article 232 of the Company Law, which scenarios listed in Article 229 require the company to undergo liquidation?
Retrieved Documents:
Vector-based Retrieval:
232 (#) 233 239 242 234 237 231 249 236
BM25 Retrieval:
232 (#) 233 229 (#) 222 239 242 221 210 223 129
Rule-based Retrieval:
232 (#) 229 (#) 233 221 223 227 228 226 222 225
Reciprocal Rank Fusion:
232 (#) 233 229 (#) 239 221 242 222 223 234 227
Reranked:
Article 232: “If a company is dissolved pursuant to subparagraphs (1), (2), (4), or (5) of the first paragraph of Article 229 of this Law, it shall undergo liquidation. The directors are the liquidation obligors of the company and shall form a liquidation group within fifteen days from the date the cause for dissolution arises.
The liquidation group shall consist of directors, unless otherwise stipulated in the company’s articles of association or unless the shareholders’ meeting resolves to appoint other persons.
If a liquidation obligor fails to perform its liquidation duties in a timely manner and thereby causes losses to the company or its creditors, it shall bear liability for compensation.”
Article 233:“If a company that is required to undergo liquidation under the first paragraph of the preceding article fails to establish a liquidation group within the prescribed time limit or fails to carry out liquidation after establishing such a group, any interested party may apply to the people’s court for the appointment of relevant persons to form a liquidation group. The people’s court shall accept such an application and promptly organize a liquidation group to carry out liquidation.
Where a company is dissolved pursuant to subparagraph (4) of the first paragraph of Article 229 of this Law, the department that made the decision to revoke its business license, order its closure, or revoke its registration, or the company registration authority, may apply to the people’s court for the appointment of relevant persons to form a liquidation group.”
Article 229:“A company shall be dissolved under any of the following circumstances:
(1) The term of business stipulated in the company’s articles of association expires or other dissolution events stipulated in the articles occur;
(2) The shareholders’ meeting resolves to dissolve the company;
(3) The company needs to be dissolved due to merger or division;
(4) The company is legally revoked of its business license, ordered to close, or revoked;
(5) The people’s court dissolves the company pursuant to Article 231 of this Law.
Upon occurrence of any of the above dissolution events, the company shall publicize the event via the National Enterprise Credit Information Publicity System within ten days.”

Traditional RAG systems often struggle with user queries that require reasoning across multiple documents, especially when the query itself lacks explicit key terms. In this example, answering the question correctly requires retrieving Article 232 to identify which subparagraphs of Article 229 trigger a liquidation obligation, and also retrieving Article 229 to understand what those subparagraphs actually specify. This tests the system’s ability to handle multi-document retrieval and queries with sparse semantic cues.
As shown, the vector-based retrieval successfully matched Article 232 but failed to retrieve Article 229 among its top ten results—demonstrating incompleteness. In contrast, BM25 retrieval, which relies on term frequency and inverse document frequency after tokenization, successfully retrieved both critical articles. Additionally, the query triggered the rule-based retrieval pathway, which also captured both key articles and ranked them more accurately. By applying Reciprocal Rank Fusion (RRF) to merge results from these three retrieval strategies, the top ten returned documents fully covered the necessary articles. Finally, a reranking step—based on semantic interaction between the query and candidate documents—further improved precision. This allowed the system to select only the top three most relevant documents for final output, achieving a balance between context control and retrieval accuracy.
