from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
import os
import requests
import json
from collections import defaultdict
import re
from cn2an import an2cn,cn2an
from collections import defaultdict
import requests
import json
from dotenv import load_dotenv
import threading
from dashscope import TextEmbedding

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
INDEX_NAME = os.getenv("INDEX_NAME", "new_qiyefa")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

client = TextEmbedding()

class BGEReranker:
    def __init__(self, model_dir="rag/rerank"):
        """
        #you should load the model from /rerank
        """
        required_files = ["pytorch_model.bin", "config.json", "tokenizer_config.json"]
        for file in required_files:
            file_path = os.path.join(model_dir, file)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"模型文件缺失: {file_path}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self.model.eval()

        # using GPU is better
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(self.device)
        self.model.to(self.device)

    def rerank(self, query, candidate_dicts, top_n=3):
        """
        :param query: Query text
        :param candidate_dicts: List of candidate dictionaries (each containing a 'content' field)
        :param top_n: Number of top results to return
        :return: Reranked list of dictionaries
        """

        candidates_text = [doc['content'] for doc in candidate_dicts]
        # Construct (query, text) pairs
        pairs = [(query, text) for text in candidates_text]

        with torch.no_grad():
            inputs = self.tokenizer(
                pairs,
                padding=True,
                truncation=True,
                return_tensors='pt',
                max_length=512
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            scores = self.model(**inputs).logits.squeeze()
            print(scores)

        #
        #         scored_candidates = list(zip(candidate_dicts, scores.tolist()))
        #         scored_candidates.sort(key=lambda x: x[1], reverse=True)

        #
        #         return [item[0] for item in scored_candidates[:top_n]]
        scored_candidates = []
        for doc, score_val in zip(candidate_dicts, scores.tolist()):
            # Create a new dictionary: keep all original fields + add a 'score' field.
            new_doc = doc.copy()
            new_doc['score'] = float(score_val)
            scored_candidates.append(new_doc)

        #  Sort in descending order by score.
        scored_candidates.sort(key=lambda x: x['score'], reverse=True)

        return scored_candidates[:top_n]


reranker = BGEReranker()

def get_embedding(text):
    """Get text embedding"""
    if not text or text.strip() == "":
        print("空文本，无法生成 embedding")
        return None

    try:
        response = client.call(
            model='text-embedding-v4',
            input=text,
            api_key="sk-0edead41dae04bdd8b29b796c31807bb"
        )
        return  response.output['embeddings'][0]['embedding']
    except Exception as e:
        print(f"获取 embedding 时出错: {e}")
        return None

def search_similar(query_text, top_k=10,rerank_top_n=3):
    """Multi-path recall retrieval(vector search, BM25, and rule-based retrieval)"""

    query_embedding=get_embedding(query_text)

    vector_results = search_vector(query_text, query_embedding, top_k=top_k)


    bm25_results = search_bm25(query_text, top_k=top_k)


    rule_results = search_rule(query_text, top_k=top_k)

    #if question triggers rule
    results_list = [vector_results, bm25_results]
    if rule_results:
        results_list.append(rule_results)
    # RRF fusion
    fused_results = rrf_fusion(results_list, top_k=top_k)

    # rerank
    if fused_results:
        reranked_results = reranker.rerank(query_text, fused_results, top_n=rerank_top_n)
        return reranked_results

    return fused_results,query_embedding


def search_vector(query_text, query_embedding, top_k=10):
    """Vector retrieval"""
    # query_embedding = get_embedding(query_text)
    if not query_embedding:
        return []

    search_body = {
        "knn": {
            "field": "embedding",
            "query_vector": query_embedding,
            "k": top_k,
            "num_candidates": 50
        },
        "fields": ["content", "filename"],
        "_source": False
    }

    url = f"{ES_HOST}/{INDEX_NAME}/_search"
    response = requests.get(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(search_body)
    )

    if response.status_code == 200:
        results = response.json()
        threshold = 0.5
        hits = [
            {
                "id": hit["_id"],
                "content": hit["fields"]["content"][0],
                "filename": hit["fields"].get("filename", ["未知文件"])[0],
                "score": hit["_score"]
            }
            for hit in results["hits"]["hits"]
            if hit["_score"] >= threshold
        ]
        print("向量召回")
        print(hits[:top_k])
        return hits[:top_k]
    else:
        print(f"向量检索失败: {response.status_code}, {response.text}")
        return []


def search_bm25(query_text, top_k=10):
    """BM25 """
    search_body = {
        "query": {
            "match": {
                "content": {
                    "query": query_text,
                    "analyzer": "ik_max_word"
                }
            }
        },
        "fields": ["content", "filename"],
        "_source": False,
        "size": top_k
    }

    url = f"{ES_HOST}/{INDEX_NAME}/_search"
    response = requests.get(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(search_body)
    )

    if response.status_code == 200:
        results = response.json()
        hits = [
            {
                "id": hit["_id"],
                "content": hit["fields"]["content"][0],
                "filename": hit["fields"].get("filename", ["未知文件"])[0],
                "score": hit["_score"]
            }
            for hit in results["hits"]["hits"]
        ]
        print("BM25召回")
        print(hits[:top_k])
        return hits[:top_k]
    else:
        print(f"BM25 检索失败: {response.status_code}, {response.text}")
        return []


def search_rule(query_text, top_k=10):
    """Vector retrieval（“第#条”or“第#章”）"""
    # match“第#条”
    section_match = re.search(r"第([\d一二三四五六七八九十百千万零]+)条", query_text)
    if section_match:
        return search_rule_based(query_text, top_k=top_k)

    # match“第#章”
    chapter_match = re.search(r"第([\d一二三四五六七八九十百千万零]+)章", query_text)
    if chapter_match:
        return search_chapter_based(query_text, top_k=top_k)

    # no match
    return []


def search_rule_based(query_text, top_k=10):
    """rule1"""
    # 提取用户问题中的“第#条”数字
    #     section_match = re.search(r"第(\d+)条", query_text)
    #     print(section_match)
    #     if not section_match:
    #         return []

    #     target_section = int(section_match.group(1))
    #     target_section_chinese=an2cn(target_section)

    section_match = re.search(r"第(\d+)条", query_text)
    chinese_match = re.search(r"第([一二三四五六七八九十百千万零]+)条", query_text)

    # Switch between Arabic numerals and Chinese numerals
    if section_match:
        target_section = int(section_match.group(1))
        target_section_chinese = an2cn(target_section)
    elif chinese_match:
        target_section_chinese = chinese_match.group(1)
        target_section = int(cn2an(target_section_chinese))
    else:
        return []

    # Construct a list of neighboring article numbers (i.e., target article +1, -1, +2, -2, ...)
    nearby_sections = []
    for i in range(1, 6):
        nearby_sections.extend([target_section + i, target_section - i])
    nearby_chinese = [an2cn(sec) for sec in nearby_sections]

    search_body = {
        "query": {
            "bool": {
                "should": [
                    {"match": {"content": f"第{target_section_chinese}条"}},
                    *[{"match": {"content": f"第{sec}条"}} for sec in nearby_chinese]
                ],
                "minimum_should_match": 1
            }
        },
        "fields": ["content", "filename"],
        "_source": False,
        "size": top_k
    }

    url = f"{ES_HOST}/{INDEX_NAME}/_search"
    response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(search_body))

    if response.status_code == 200:
        results = response.json()
        hits = [
            {
                "id": hit["_id"],
                "content": hit["fields"]["content"][0],
                "filename": hit["fields"].get("filename", ["未知文件"])[0],
                "score": hit["_score"]
            }
            for hit in results["hits"]["hits"]
        ]
        target_query = f"第{target_section_chinese}条"
        hits.sort(key=lambda x: (0 if target_query in x['content'] else 1, -x['score']))
        print("规则召回（条）")
        print(hits[:top_k])
        return hits[:top_k]
    else:
        print(f"规则召回失败: {response.status_code}, {response.text}")
        return []


def search_chapter_based(query_text, top_k=10):
    """rule2"""

    chapter_match_math = re.search(r"第(\d+)章", query_text)
    chapter_match = re.search(r"第([一二三四五六七八九十百千万零]+)章", query_text)

    if chapter_match:
        target_chapter = chapter_match.group(1)
    elif chapter_match_math:
        target_chapter_math = int(chapter_match_math.group(1))
        target_chapter = an2cn(target_chapter_math)
    else:
        return []

    #match filename
    search_body = {
        "query": {
            "match_phrase": {  # 改用短语匹配
                "filename": f"公司法第{target_chapter}章.docx"
            }
        },
        "fields": ["content", "filename"],
        "_source": False,
        "size": top_k
    }

    url = f"{ES_HOST}/{INDEX_NAME}/_search"
    try:
        response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(search_body))
        response.raise_for_status()

        results = response.json()
        hits = [
            {
                "id": hit["_id"],
                "content": hit["fields"]["content"][0],
                "filename": hit["fields"].get("filename", ["未知文件"])[0],
                "score": hit["_score"]
            }
            for hit in results["hits"]["hits"]
        ]
        print("规则召回（章）")
        print(hits[:top_k])
        return hits[:top_k]
    except Exception as e:
        print(f"章节召回失败: {str(e)}")
        return []


def rrf_fusion(results_list, top_k=10, k=60):
    """Reciprocal Rank Fusion"""
    rrf_scores = defaultdict(float)

    all_docs = {}

    for results in results_list:
        for rank, doc in enumerate(results):
            doc_id = doc["id"]

            all_docs[doc_id] = doc
            # RRF score
            score = 1 / (rank + 1 + k)
            rrf_scores[doc_id] += score

    # Sort by total RRF score in descending order
    sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    # Deduplicate and extract the top `top_k` documents.
    final_results = []
    seen_ids = set()

    for doc_id in sorted_doc_ids:
        if doc_id in seen_ids:
            continue

        final_results.append(all_docs[doc_id])
        seen_ids.add(doc_id)
        if len(final_results) == top_k:
            break
    print(final_results)
    return final_results

