from dotenv import load_dotenv
import os
import requests
import json
import re
from docx import Document
import glob
from dashscope import TextEmbedding

ES_HOST = "http://localhost:9200"
INDEX_NAME = "INDEX_NAME"
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
DOCS_FOLDER = os.getenv("DOCS_FOLDER", "/app/data")

client = TextEmbedding()

index_mapping = {
    "mappings": {
        "properties": {
            "content": {"type": "text",
                        "analyzer": "ik_max_word"}, #using ik_max_word as analyzer
            "embedding": {
                "type": "dense_vector",
                "dims": 1024,
                "index": True,
                "similarity": "cosine"
            },
            "filename": {"type": "keyword"},
            "chunk_index": {"type": "integer"}
        }
    }
}


def create_index():
    """Create index with idempotency check"""
    url = f"{ES_HOST}/{INDEX_NAME}"
    response = requests.head(url)
    if response.status_code == 200:
        print(f"索引 '{INDEX_NAME}' 已存在，无需创建")
        return True
    response = requests.put(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(index_mapping)
    )
    if response.status_code in [200, 201]:
        print(f"索引 '{INDEX_NAME}' 创建成功！")# Index created successfully!
        return True
    else:
        print(f"创建索引失败: {response.status_code}, {response.text}")
        return False


def get_embedding(text):
    try:
        response = client.call(
            model='text-embedding-v4',  # use text-embedding-v4 as embedding model
            input=text,
            api_key=os.getenv("DASHSCOPE_API_KEY")
        )

        return response.output['embeddings'][0]['embedding']
    except Exception as e:
        print(f"获取embedding时出错: {e}")
        return None


def index_document(content_text, embedding_vector, filename, chunk_idx):
    document = {
        "content": content_text,
        "embedding": embedding_vector,
        "filename": filename,
        "chunk_index": chunk_idx
    }
    url = f"{ES_HOST}/{INDEX_NAME}/_doc/"
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(document)
    )
    if response.status_code in [200, 201]:
        doc_id = response.json().get('_id', 'unknown')
        print(f"索引成功 | 文件: {filename} | 块 {chunk_idx} | ES ID: {doc_id}")
    else:
        print(f"索引失败 | 文件: {filename} | 块 {chunk_idx} | 状态码: {response.status_code}, 错误: {response.text}")


def split_by_article(text):
    """chunking"""
    pattern = r'(第[一二三四五六七八九十百千万零]+条\s+.*?)(?=第[一二三四五六七八九十百千万零]+条\s+|$)'
    matches = re.findall(pattern, text, re.DOTALL)
    return [match.strip() for match in matches if match.strip()]


def check_index_has_data():
    """Check if the index already contains data"""
    url = f"{ES_HOST}/{INDEX_NAME}/_count"  # ES 计数 API
    try:
        response = requests.get(url)
        response.raise_for_status()
        count = response.json().get("count", 0)
        if count > 0:
            print(f"索引 '{INDEX_NAME}' 中已存在 {count} 条文档数据")
            return True  #data exist
        else:
            print(f"索引 '{INDEX_NAME}' 存在但无文档数据")
            return False  # no data
    except Exception as e:
        print(f"检查索引数据时出错: {e}")
        return False


def read_docx(file_path):
    try:
        doc = Document(file_path)
        return '\n'.join([para.text for para in doc.paragraphs])
    except Exception as e:
        print(f"读取文件失败: {file_path}, 错误: {e}")
        return ""


if __name__ == "__main__":

    if not create_index():
        exit(1)

    if check_index_has_data():
        print("检测到索引中已有内容，无需重复导入，程序退出。")
        exit(0)
    # 2. Read documents mounted inside the container(or you can read from rag/data)
    docx_files = glob.glob(os.path.join(DOCS_FOLDER, "*.docx"))
    docx_files = [f for f in docx_files if not os.path.basename(f).startswith("~$")]

    if not docx_files:
        print(f"在 {DOCS_FOLDER} 中未找到任何 .docx 文件！")
        exit()

    print(f"发现 {len(docx_files)} 个 Word 文件，开始处理...\n")
    total_chunks = 0

    for file_path in docx_files:
        filename = os.path.basename(file_path)
        print(f"正在处理文件: {filename}")

        doc_text = read_docx(file_path)
        if not doc_text.strip():
            print(f"文件为空或读取失败，跳过: {filename}\n")
            continue

        chunks = split_by_article(doc_text)
        print(f"{filename} 共切分出 {len(chunks)} 条法律条文")

        for i, chunk in enumerate(chunks):
            embedding = get_embedding(chunk)
            if embedding:
                index_document(chunk, embedding, filename, i + 1)
                total_chunks += 1
            else:
                print(f"跳过第 {i + 1} 条（embedding生成失败）")

        print(f"{filename} 处理完成\n")

    print(f"所有文件处理完毕！共索引 {total_chunks} 个文本块。")
