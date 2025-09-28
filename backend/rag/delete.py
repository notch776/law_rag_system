import requests
import os
from dotenv import load_dotenv

load_dotenv()
ES_HOST = os.getenv("ES_HOST")
INDEX_NAME = os.getenv("INDEX_NAME")

response = requests.post(
    f"{ES_HOST}/{INDEX_NAME}/_delete_by_query",
    headers={"Content-Type": "application/json"},
    json={"query": {"match_all": {}}}
)

print(response.json())