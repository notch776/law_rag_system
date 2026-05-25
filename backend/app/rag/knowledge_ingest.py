import json
import re
from pathlib import Path
from typing import Dict, List
import requests
from docx import Document
from app.core.config import settings
from app.services.model_service import ModelService

ARTICLE_RE = re.compile(r"(第[一二三四五六七八九十百千万零]+条\s*.*?)(?=第[一二三四五六七八九十百千万零]+条\s*|$)", re.S)


def read_docx(path: Path) -> str:
    doc = Document(str(path))
    return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def split_articles(text: str) -> List[str]:
    matches = [m.strip() for m in ARTICLE_RE.findall(text) if m.strip()]
    return matches or [text]


def extract_article_id(text: str) -> str:
    m = re.search(r"第[一二三四五六七八九十百千万零]+条", text)
    return m.group(0) if m else ""


def chapter_from_filename(name: str) -> str:
    m = re.search(r"公司法(第[一二三四五六七八九十百千万零]+章)", name)
    return m.group(1) if m else ""


def mapping() -> Dict:
    return {
        "mappings": {
            "properties": {
                "content": {"type": "text"},
                "embedding": {"type": "dense_vector", "dims": 1152, "index": True, "similarity": "cosine"},
                "law_name": {"type": "keyword"},
                "chapter": {"type": "keyword"},
                "article_id": {"type": "keyword"},
                "filename": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "source_type": {"type": "keyword"},
                "authority_level": {"type": "keyword"},
            }
        }
    }


def ensure_index():
    url = f"{settings.es_host.rstrip('/')}/{settings.es_index}"
    if requests.head(url, timeout=5).status_code == 200:
        return
    resp = requests.put(url, headers={"Content-Type": "application/json"}, data=json.dumps(mapping()), timeout=10)
    resp.raise_for_status()


def ingest():
    ensure_index()
    model = ModelService()
    docs_dir = Path(settings.docs_folder)
    for path in docs_dir.glob("*.docx"):
        if path.name.startswith("~$"):
            continue
        text = read_docx(path)
        chapter = chapter_from_filename(path.name)
        for idx, chunk in enumerate(split_articles(text), 1):
            emb = model.embed_text(chunk)
            if not emb:
                continue
            body = {
                "content": chunk,
                "embedding": emb,
                "law_name": "中华人民共和国公司法",
                "chapter": chapter,
                "article_id": extract_article_id(chunk),
                "filename": path.name,
                "chunk_index": idx,
                "source_type": "law_text",
                "authority_level": "unknown",
            }
            requests.post(f"{settings.es_host.rstrip('/')}/{settings.es_index}/_doc", headers={"Content-Type": "application/json"}, data=json.dumps(body, ensure_ascii=False), timeout=10)


if __name__ == "__main__":
    ingest()
