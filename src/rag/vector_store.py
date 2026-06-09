from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from rag.parser import parse_policy_markdown


class ChromaPolicyStore:
    """Student scaffold for the real Chroma-backed policy index."""

    def __init__(
        self,
        persist_directory: Path,
        embedding_model: Any,
        collection_name: str = "policy_chunks",
    ) -> None:
        self.persist_directory = persist_directory
        self.embedding_model = embedding_model
        
        # Initialize Chroma client
        self.client = chromadb.PersistentClient(
            path=str(persist_directory),
            settings=ChromaSettings(allow_reset=True)
        )
        
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def ensure_index(self, markdown_path: Path) -> None:
        if self.collection.count() == 0:
            print(f"Index empty. Building from {markdown_path}...")
            self.rebuild(markdown_path)
        else:
            print(f"Index exists with {self.collection.count()} documents.")

    def rebuild(self, markdown_path: Path) -> None:
        if not markdown_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {markdown_path}")
            
        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()
            
        chunks = parse_policy_markdown(markdown_text)
        
        # Clear existing
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.create_collection(
            name=self.collection.name,
            metadata={"hnsw:space": "cosine"}
        )
        
        if not chunks:
            return
            
        documents = [c["rendered_text"] for c in chunks]
        metadatas = [{
            "section_h2": c["section_h2"],
            "section_h3": c["section_h3"],
            "citation": c["citation"]
        } for c in chunks]
        ids = [str(uuid.uuid4()) for _ in chunks]
        
        # Use embedding model to get embeddings
        embeddings = self.embedding_model.embed_documents(documents)
        
        # Add to collection in batches if necessary
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            end = i + batch_size
            self.collection.add(
                ids=ids[i:end],
                documents=documents[i:end],
                metadatas=metadatas[i:end],
                embeddings=embeddings[i:end]
            )
        print(f"Rebuild completed. {len(documents)} chunks indexed.")

    def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        query_embedding = self.embedding_model.embed_query(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        hits = []
        if results["ids"]:
            for i in range(len(results["ids"][0])):
                hits.append({
                    "content": results["documents"][0][i],
                    "citation": results["metadatas"][0][i]["citation"],
                    "distance": results["distances"][0][i]
                })
        return hits
