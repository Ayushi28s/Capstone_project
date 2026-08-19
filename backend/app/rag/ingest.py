"""
Ingests the policy document library into ChromaDB. This is what the
Knowledge Agent retrieves against for cited product/policy answers.

Run standalone:
    python -m app.rag.ingest
"""
import glob
import os
import uuid

import chromadb
from chromadb.utils import embedding_functions
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings


def _load_policy_documents() -> list[Document]:
    docs = []
    for path in sorted(glob.glob(os.path.join(settings.POLICY_DOCS_DIR, "*.md"))):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        docs.append(Document(page_content=text, metadata={"source": os.path.basename(path)}))
    return docs


def build_policy_index(reset: bool = False) -> int:
    """Chunk and embed every policy document into the Chroma collection.
    Returns the number of chunks written."""
    os.makedirs(settings.CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=settings.CHROMA_DIR)

    if reset:
        try:
            client.delete_collection(settings.POLICY_COLLECTION)
        except Exception:
            pass

    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.EMBEDDING_MODEL
    )
    collection = client.get_or_create_collection(
        name=settings.POLICY_COLLECTION,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    )

    documents = _load_policy_documents()
    if not documents:
        raise FileNotFoundError(
            f"No policy markdown files found in {settings.POLICY_DOCS_DIR}. "
            "Add at least one .md policy document before ingesting."
        )

    ids, texts, metadatas = [], [], []
    for doc in documents:
        chunks = splitter.split_text(doc.page_content)
        for i, chunk in enumerate(chunks):
            ids.append(str(uuid.uuid4()))
            texts.append(chunk)
            metadatas.append({"source": doc.metadata["source"], "chunk_index": i})

    collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
    return len(ids)


if __name__ == "__main__":
    n = build_policy_index(reset=True)
    print(f"Indexed {n} policy chunks into collection '{settings.POLICY_COLLECTION}'.")
