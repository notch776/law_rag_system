import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()
ES_HOST = os.getenv("ES_HOST")
INDEX_NAME = os.getenv("INDEX_NAME")

index_mapping = {
    "mappings": {
        "properties": {
            "content": {
                "type": "text"
            },
            "embedding": {
                "type": "dense_vector",
                "dims": 1024,
                "index": True,
                "similarity": "cosine"
            }
        }
    }
}

def create_index():
    url = f"{ES_HOST}/{INDEX_NAME}"
    response = requests.put(url, headers={"Content-Type": "application/json"}, data=json.dumps(index_mapping))
    if response.status_code in [200, 201]:
        print(f"索引 '{INDEX_NAME}' 创建成功！")
    else:
        print(f"创建索引失败: {response.status_code}, {response.text}")

create_index()